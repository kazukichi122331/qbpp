"""QUBO 式を組むときの共通部品と、ソルバの呼び出し。

順序型 4 本 (order_cumulative / order_prefix / order_wait / order_start*) で
同じだった「one-hot 制約の張り方」「leg の作り方」「固定辞書」「ペナルティ係数の
決め方」「探索と復元」をここにまとめている。
"""
import time

import pyqbpp as qbpp

# 係数は int32 で保持される。これを超えると黙って桁溢れする。
COEFF_MAX = 2 ** 31 - 1


# --------------------------------------------------------------------------
# 0. バックエンド差の吸収
# --------------------------------------------------------------------------
def as_expr(e):
    """qbpp の array 要素を Expr に変換する。

    nanobind バックエンド (pyqbpp_nb) の array.__getitem__ は Expr ではなく
    配列要素への参照 _ExprRef を返し、qbpp.cons() / qbpp.copy() は
    これを受け取れない (TypeError)。read() で実体化する。
    ctypes バックエンドは最初から Expr を返すのでそのまま通す。
    """
    read = getattr(e, "read", None)
    return read() if read is not None else e


# --------------------------------------------------------------------------
# 1. 変数
# --------------------------------------------------------------------------
def start_vars(inst, dom, *, name="a"):
    """位置ごとのサービス開始時刻の整数変数 a[i] を作る。

    dom[i] = (lo, hi)。幅 0 の位置は変数を作らず定数式に潰す。
    a[0] は depot 出発時刻なので必ず定数。
    """
    a = [qbpp.expr() + dom[0][0]]
    for i in range(1, inst.N):
        lo, hi = dom[i]
        if lo >= hi:
            a.append(qbpp.expr() + lo)                  # 定数に潰す
        else:
            a.append(qbpp.var(f"{name}[{i}]", between=(lo, hi)))
    return a


def wait_vars(inst, w_hi, *, name="w"):
    """位置ごとの待ち時間の整数変数 w[i] を作る。上界 0 の位置は定数 0。

    order_cumulative.py は w[0] を作りながら一度も使っていなかったので、
    ここでは i = 1..N-1 だけ作る (変数の総数は同じ)。
    """
    w = [qbpp.expr()]
    for i in range(1, inst.N):
        if w_hi[i] <= 0:
            w.append(qbpp.expr())
        else:
            w.append(qbpp.var(f"{name}[{i}]", between=(0, w_hi[i])))
    return w


# --------------------------------------------------------------------------
# 2. 制約と式
# --------------------------------------------------------------------------
def onehot_constraints(inst, x):
    """行 (各位置に 1 顧客) と列 (各顧客を 1 回) の one-hot を宣言制約で返す。

    qbpp.cons(body, equal=1) は本体と上下限を記録するだけでペナルティ多項式を
    作らないので、(Σx-1)^2 を展開する書き方より項数が桁違いに少ない。
    1 本ずつ宣言するので f.cons(sol) が違反本数を数えられる。
    """
    row_sums = qbpp.vector_sum(x, axis=1)       # 位置 i -> Σ_u x[i][u]
    col_sums = qbpp.vector_sum(x, axis=0)       # 顧客 u -> Σ_i x[i][u]
    row_constraint = qbpp.expr()
    col_constraint = qbpp.expr()
    for k in range(inst.N):
        row_constraint += qbpp.cons(as_expr(row_sums[k]), equal=1)
        col_constraint += qbpp.cons(as_expr(col_sums[k]), equal=1)
    return row_constraint, col_constraint


def build_legs(inst, x, allowed=None):
    """leg[i] (位置 i-1 -> i の移動時間, x の 2 次式) と depot 帰着 leg を返す。

    allowed を渡すと、0 に固定される x の組を最初から作らない。
    allowed=None なら全 (u, v) を作る (枝刈りを持たない定式化用)。
    """
    c, N = inst.c, inst.N
    if allowed is None:
        src = dst = [list(range(N))] * N
        ret_from = range(1, N)
    else:
        src = dst = allowed
        ret_from = allowed[N - 1]

    legs = [None] * N
    for i in range(1, N):
        leg = qbpp.expr()
        for u in src[i - 1]:
            for v in dst[i]:
                if u != v and c[u][v]:
                    leg += x[i - 1][u] * x[i][v] * c[u][v]
        legs[i] = leg

    return_leg = qbpp.expr()
    for u in ret_from:
        if c[u][0]:
            return_leg += x[N - 1][u] * c[u][0]

    return legs, return_leg


def time_window_sums(inst, x, i, allowed=None):
    """位置 i の Σ_u x[i][u] E[u] と Σ_u x[i][u] L[u]。

    時間枠制約 E[u] <= a[i] <= L[u] を「選ばれた顧客の E / L」として書くための和。
    """
    E, L, N = inst.E, inst.L, inst.N
    targets = range(1, N) if allowed is None else allowed[i]
    e_sum = qbpp.expr()
    l_sum = qbpp.expr()
    for u in targets:
        if E[u]:
            e_sum += x[i][u] * E[u]
        if L[u]:
            l_sum += x[i][u] * L[u]
    return e_sum, l_sum


def fix_map(inst, x, allowed=None):
    """値が決まっている x を集めた辞書 (qbpp.replace に渡す)。

    allowed あり : 位置 i に置けない顧客をすべて 0、x[0][0] = 1
    allowed なし : depot の固定だけ (x[0][0]=1, x[0][u]=0, x[i][0]=0)
    """
    N = inst.N
    ml = {}
    if allowed is None:
        ml[x[0][0]] = 1
        ml.update({x[0][u]: 0 for u in range(1, N)})
        ml.update({x[i][0]: 0 for i in range(1, N)})
        return ml

    for i in range(N):
        keep = set(allowed[i])
        for u in range(N):
            if u not in keep:
                ml[x[i][u]] = 0
    ml[x[0][0]] = 1
    return ml


# --------------------------------------------------------------------------
# 3. ペナルティ係数
# --------------------------------------------------------------------------
def dmax_order(inst, dom, *, allowed=None, w_hi=None, leg_max=None):
    """時間制約 1 本あたりの違反量の上界 dmax。

    行 one-hot が満たされている領域 (= 探索が実際に動く範囲) での上界を、
    定義域から直接計算する。

      (T1) a[i-1] + leg[i] - a[i]  <= a_hi[i-1] + max leg - a_lo[i]
      (T2) E[u] - a[i]             <= max_{u in allowed[i]} E[u] - a_lo[i]
      (T3) a[i] - L[u]             <= a_hi[i] - min_{u in allowed[i]} L[u]
      (T4) a[N-1] + c[u][0] - L[0] <= a_hi[N-1] + max_u c[u][0] - L[0]

    w_hi を渡すと (T1) の代わりに、待ち時間変数を含む等式制約の両側を評価する。

      (W) |a[i] - a[i-1] - leg[i] - w[i]|
          <= max( a_hi[i] - a_lo[i-1] - min leg,
                  a_hi[i-1] + max leg + w_hi[i] - a_lo[i] )

    allowed=None なら「全顧客がどの位置にも置ける」として計算する
    (枝刈りを持たない定式化用)。leg_max を渡すと位置ごとの max leg の代わりに
    その一括上界を使う。
    """
    from .bounds import all_allowed, leg_bounds     # 循環 import を避ける

    c, E, L, N = inst.c, inst.E, inst.L, inst.N
    if allowed is None:
        allowed = all_allowed(inst)

    dmax = 1
    for i in range(1, N):
        if allowed[i - 1] and allowed[i]:
            leg_lo, leg_hi = leg_bounds(inst, allowed, i)
            if leg_max is not None:
                leg_hi = leg_max
            if w_hi is None:
                dmax = max(dmax, dom[i - 1][1] + leg_hi - dom[i][0])
            else:
                dmax = max(dmax, dom[i][1] - dom[i - 1][0] - leg_lo)
                dmax = max(dmax,
                           dom[i - 1][1] + leg_hi + w_hi[i] - dom[i][0])
        if allowed[i]:
            dmax = max(dmax, max(E[u] for u in allowed[i]) - dom[i][0])
            dmax = max(dmax, dom[i][1] - min(L[u] for u in allowed[i]))
    if allowed[N - 1]:
        dmax = max(dmax,
                   dom[N - 1][1] + max(c[u][0] for u in allowed[N - 1]) - L[0])
    return max(dmax, 1)


def penalty_weights(*, time_p, dmax, onehot_ratio=0, travel=None):
    """(TIME_P, ONEHOT_P, 表示用の文字列) を返す。

    TIME_P   : 目的関数の変域 + 1。時間制約を 1 単位破って移動時間を稼ぐ
               取引が必ず損になる最小値。
    ONEHOT_P : TIME_P * dmax^2 + 1。one-hot 違反 1 回が、どんな時間制約違反
               よりも高くつくようにする (制約族の優先順位付け)。
               宣言制約のエネルギー寄与が weight * (違反量)^2 で、時間制約の
               違反量は「時刻」単位なので、一律の重みでは one-hot を破る方が
               安くなってしまう。これが order_start.py の敗因。
    onehot_ratio > 0 なら ONEHOT_P = ratio * TIME_P で上書きする。
    """
    if onehot_ratio > 0:
        onehot_p = onehot_ratio * time_p
        how = f"ONEHOT_RATIO={onehot_ratio} (指定値)"
    else:
        onehot_p = time_p * dmax * dmax + 1
        how = f"TIME_P*dmax^2+1 (dmax={dmax})"

    clamped = ""
    if onehot_p > COEFF_MAX:
        onehot_p = COEFF_MAX
        clamped = (f"  WARNING: 係数上限 int32 で clamp した "
                   f"(比 ONEHOT_P/TIME_P = {COEFF_MAX // time_p})")

    head = f"travel = [{travel[0]}, {travel[1]}]  " if travel else ""
    info = (f"{head}TIME_P = {time_p}  ONEHOT_P = {onehot_p}  "
            f"<- {how}{clamped}")
    return time_p, onehot_p, info


# --------------------------------------------------------------------------
# 4. 探索
# --------------------------------------------------------------------------
def solve(f, ml, opt, *, build_sec=0.0):
    """f を QUBO に落として探索する。

    ml (固定辞書) があれば g = replace(f, ml) を解き、値は f 側に戻す。
    ml が空なら f をそのまま解く。

    返り値は (simplify 後の f, sol, val)。val は式に値を入れる呼び出し可能
    オブジェクト (ml あり: qbpp.Sol, なし: sol 自身)。
    --build-only のときは (f, None, None) を返すので、呼び出し側は
    sol is None で早期 return する。
    """
    t0 = time.perf_counter()
    if ml:
        g = qbpp.replace(f, ml)
        f = qbpp.simplify_as_binary(f)
        g = qbpp.simplify_as_binary(g)
    else:
        f = qbpp.simplify_as_binary(f)
        g = f
    build_sec += time.perf_counter() - t0
    print(f"build       = {build_sec:.3f} sec (式の構築 + simplify)")

    if opt.build_only:
        return f, None, None

    solver = qbpp.ABS3Solver(g)
    search_kw = {"time_limit": opt.time_limit}
    if opt.seed is not None:
        search_kw["seed"] = int(opt.seed)
    if opt.auto_swap:
        # ABS3 が宣言制約から one-hot を検出し、one-hot を保つ 2 ビット同時
        # 反転 (SwapMutation) を使う。階層化ペナルティと併用すると
        # 上積みがなく、実測では解の質が落ちた (order_start_tiered の docstring)。
        search_kw["auto_swap"] = 1

    print(f"solve now...({opt.time_limit} sec)")
    sol = solver.search(**search_kw)
    val = qbpp.Sol(f).set(sol, ml) if ml else sol
    return f, sol, val
