"""
prefix-free (差分形) TSPTW QUBO 定式化 —— src/tsptw.py の O(N^4) 構築を O(N^3) に。

変数は tsptw.py と同じ x と w の 2 種類だけ。新しい変数は 1 つも足していない。

    x[i][u] = 1  <=>  i 番目に顧客 u を訪れる            (バイナリ, N*N 個)
    w[i]          =   i 番目のサービス開始時刻            (整数,     N-1 個)

==========================================================================
1. tsptw.py が O(N^4) になる理由
==========================================================================
tsptw.py は時刻を「式」として持っていた。

    t[i]  = t[i-1] + Σ_{u≠v} x[i-1][u]·x[i][v]·c[u][v]     (累積移動時間)
    tw[i] = t[i] + Σ_{1<=j<i} w[j]                         (到着時刻)
    サービス開始 = tw[i] + w[i]

t[i] が t[i-1] を **丸ごと含む** ので単項式数は |t[i]| = Θ(i·N^2)。

  * 構築コスト: t の列を作るだけで Σ_i |t[i]| = Σ_i i·N^2 = Θ(N^4)。
    しかも 1 段ごとに qbpp.copy(t[i-1]) で Θ(i·N^2) 語をコピーしている。
  * モデルサイズ: qbpp.cons(body, between=...) は body の多項式を
    **展開したまま記録する** (_core.py の qbpp_cons_between)。
    位置 i の時間制約 2 本はそれぞれ tw[i]+w[i] を body に持つので、
    宣言制約の総 body サイズも Σ_i 2·Θ(i·N^2) = Θ(N^4)。
    N を 2 倍にすると 16 倍。N=40 あたりで構築そのものが支配的になる。

「累積和を式で書く」のが唯一の原因なので、そこだけを差し替える。

==========================================================================
2. 本版の表現: 累積和を「変数の値」にする
==========================================================================
prefix sum を式として持ち回るのをやめ、**その値を w に持たせる**。
tsptw.py の w は「待ち時間」だったが、ここでは

    w[i] = 位置 i のサービス開始時刻  ( = tw[i] + w_old[i] の値 )

と読み替える。w の個数も型 (整数変数) も変わらない。待ち時間は

    wait[i] = w[i] - w[i-1] - leg[i]        (leg[i] は位置 i に入る移動時間)

で復元できるので、情報は 1 つも失われない。制約は 1 段ぶんの差分だけで書ける。

    (R)  Σ_u x[i][u] == 1                              各順序にちょうど 1 顧客
    (C)  Σ_i x[i][u] == 1                              各顧客をちょうど 1 回
    (P)  w[i] - w[i-1] - leg[i] >= 0                    到着してからサービス開始
                                                        (左辺がそのまま待ち時間)
    (T2) w[i] - Σ_u x[i][u]·E[u] >= 0                   時間枠 (早い側)
    (T3) w[i] - Σ_u x[i][u]·L[u] <= 0                   時間枠 (遅い側)
    (D)  w[N-1] + Σ_u x[N-1][u]·c[u][0] - L[0] <= 0     depot 帰着期限
                                                        (tsptw.py に無かった)

body の単項式数:

    (P)  Θ(N^2) × (N-1) 本  = Θ(N^3)   <- ここが支配項
    (T2) Θ(N)   × (N-1) 本  = Θ(N^2)
    (T3) Θ(N)   × (N-1) 本  = Θ(N^2)
    (D)  Θ(N)   × 1 本      = Θ(N)
    目的 (総移動時間)        = Θ(N^3)   (leg[i] を (P) と共有するので追加ゼロ)

合計 Θ(N^3)。tsptw.py より N の 1 乗ぶん軽い。leg[i] は 1 度だけ作って
(P) と目的関数で共有するので、実測の定数倍も小さくなる。

(P) を等式ではなく不等式にしているのがポイント。tsptw.py の w が
「スラック変数」の役割を担っていたぶんを、不等式制約が吸収している。
だから待ち時間用の変数を別に持つ必要がない。

==========================================================================
3. 検討して採らなかった案
==========================================================================
(a) **累積和を平衡二分木 / prefix doubling で共有する**
    t[i] を分割統治で作れば部分和は O(N^2 log N) 個で共有できる。
    しかし qbpp.cons() は制約ごとに body を展開して記録するため、
    N 本の時間制約それぞれが自分用に Θ(i·N^2) 語を持つことになり
    総量は Θ(N^4) のまま。共有部分式を持てるバックエンドでないと効かない。

(b) **w を待ち時間のまま残し、隣接差分だけを制約にする**
    w[i] - w[i-1] 型の局所制約だけでは「絶対時刻が [E,L] に入る」を
    表現できない (全体を平行移動した解を排除できない)。モデルとして誤り。
    絶対時刻を参照する制約が要る = 位置ごとに絶対時刻の入れ物が要る、
    というのが本質で、それを w に兼務させたのが 2 節。

(c) **時間展開型 (src/time_tsptw.py)**
    時刻を添字にすれば時間枠は変数の定義域になり累積和が消える。
    ただし変数数が O(N·T) になり、x と w だけという今回の縛りから外れる。

(d) **目的関数を makespan にする**
    総移動時間 Θ(N^3) をやめて w[N-1] + 帰着 leg にすると目的関数は Θ(N) 語。
    ただし (P) が Θ(N^3) 残るので全体の漸近は変わらない。
    OBJ_MODE=makespan で選べるようにしてある。

(e) **到達不能アークの枝刈り**
    E[u]+c[u][v] > L[v] なるアークは leg から落とせるが、代わりに
    「使ってはいけない」ペナルティ項が必要で単項式が移動するだけ。
    漸近的な得はない (時間枠が狭いインスタンスでは定数倍の得はある)。

==========================================================================
4. 使い方
==========================================================================
    .venv/bin/python -m src.pre_tsptw 10          # 10 秒探索
    TSPTW_BUILD_ONLY=1 .venv/bin/python -m src.pre_tsptw    # 構築時間だけ測る
    TSPTW_OBJ=makespan .venv/bin/python -m src.pre_tsptw 10
    TSPTW_INSTANCE=instances/Dumas/n60w100.001.txt .venv/bin/python -m src.pre_tsptw 10
"""
import os
import sys
import time
from datetime import datetime

import pyqbpp as qbpp

try:                                        # python -m src.pre_tsptw
    from src.dist_matrix import N, c, L, E
    from src.plot_tsptw import plot_tour, recover_coordinates
except ImportError:                         # python src/pre_tsptw.py
    from dist_matrix import N, c, L, E
    from plot_tsptw import plot_tour, recover_coordinates

DEFAULT_TIME = 5.0
COEFF_MAX = 2 ** 31 - 1         # 係数は int32 保持。超えると黙って桁溢れする

PLOT = os.environ.get("TSPTW_PLOT", "1") != "0"
PLOT_MAX_N = 60                 # recover_coordinates() は N が大きいと重い

# "travel"   : 総移動時間 (tsptw.py と同じ, 既定)。leg を (P) と共有する
# "makespan" : depot 帰着時刻。目的関数は Θ(N) 語だけになる (3 節 (d))
OBJ_MODE = os.environ.get("TSPTW_OBJ", "travel")

BUILD_ONLY = os.environ.get("TSPTW_BUILD_ONLY", "0") != "0"


def as_expr(e):
    """qbpp の array 要素を Expr にする。

    nanobind バックエンドの array.__getitem__ は Expr ではなく参照 _ExprRef を
    返し、qbpp.cons() が受け取れない。read() で実体化する。
    """
    read = getattr(e, "read", None)
    return read() if read is not None else e


# --------------------------------------------------------------------------
# 1. w[i] の定義域 (累積和の値を入れるので「時刻」の範囲になる)
# --------------------------------------------------------------------------
def customer_bounds():
    """顧客 u のサービス開始時刻の下限 lo / 上限 hi。

    lo[u] : depot から直行しても c[0][u] はかかる     -> max(E[u], c[0][u])
    hi[u] : ここから L[0] までに depot へ帰れること   -> min(L[u], L[0]-c[u][0])
    """
    lo = [E[0]] * N
    hi = [L[0]] * N
    for u in range(1, N):
        lo[u] = max(E[u], c[0][u])
        hi[u] = min(L[u], L[0] - c[u][0])
    return lo, hi


def min_leg():
    """u != v の最小移動時間。0 でも健全 (定義域が緩むだけ)。"""
    legs = [c[u][v] for u in range(N) for v in range(N) if u != v]
    return min(legs) if legs else 0


def travel_range():
    """総移動時間の下界 / 上界 (各行の最小 / 最大 leg の総和)。"""
    lb = sum(min(c[u][v] for v in range(N) if v != u) for u in range(N))
    ub = sum(max(c[u][v] for v in range(N) if v != u) for u in range(N))
    return lb, ub


def w_domains(lo, hi, a0, cmin):
    """位置 i (1..N-1) の w[i] の定義域 [wlo, whi]。

    サービス開始時刻はツアーに沿って cmin 以上ずつ増えるので、両端から
    cmin を積み上げて絞る。tsptw.py の between=(0, 100) 固定を置き換える。
    """
    first_lo = max(min(lo[1:]), a0 + cmin)
    last_hi = max(hi[1:])
    dom = [(a0, a0)]
    for i in range(1, N):
        wlo = first_lo + (i - 1) * cmin
        whi = last_hi - (N - 1 - i) * cmin
        dom.append((wlo, max(wlo, whi)))
    return dom


# --------------------------------------------------------------------------
# 2. ペナルティ係数 (階層化: 制約族どうしに優先順位を付ける)
# --------------------------------------------------------------------------
def max_time_violation(dom):
    """時間制約 1 本あたりの違反量の上界 dmax。

    one-hot が満たされている領域での、定義域から出る最悪値。

      (P)  -(w[i]-w[i-1]-leg[i]) <= whi[i-1] + max leg - wlo[i]
      (T2) E[u] - w[i]           <= max E - wlo[i]
      (T3) w[i] - L[u]           <= whi[i] - min L
      (D)  w[N-1]+c[u][0]-L[0]   <= whi[N-1] + max c[u][0] - L[0]
    """
    leg_max = max((c[u][v] for u in range(N) for v in range(N) if u != v),
                  default=0)
    e_max = max(E[1:], default=0)
    l_min = min(L[1:], default=0)
    dmax = 1
    for i in range(1, N):
        wlo, whi = dom[i]
        dmax = max(dmax, dom[i - 1][1] + leg_max - wlo)
        dmax = max(dmax, e_max - wlo)
        dmax = max(dmax, whi - l_min)
    dmax = max(dmax, dom[N - 1][1] + max(c[u][0] for u in range(1, N)) - L[0])
    return max(dmax, 1)


def penalty_weights(dom, travel_lb, travel_ub):
    """(TIME_P, ONEHOT_P, 内訳) を返す。

    TIME_P   : 目的関数の変域 + 1。時間制約を 1 単位破って移動時間を稼ぐ
               取引が必ず損になる最小値。
    ONEHOT_P : TIME_P * dmax^2 + 1。one-hot 違反 1 回がどんな時間制約違反より
               高くつくようにする。tsptw.py の 50000 / 10 固定を置き換える。
    """
    time_p = (travel_ub - travel_lb + 1) if OBJ_MODE == "travel" else (L[0] + 1)
    dmax = max_time_violation(dom)
    onehot_p = time_p * dmax * dmax + 1
    note = f"TIME_P*dmax^2+1 (dmax={dmax})"
    if onehot_p > COEFF_MAX:
        onehot_p = COEFF_MAX
        note += f"  WARNING: int32 で clamp (比 {COEFF_MAX // time_p})"
    return time_p, onehot_p, note


# --------------------------------------------------------------------------
# 3. 解の検証 (QUBO のエネルギーとは独立にツアーを直接シミュレートする)
# --------------------------------------------------------------------------
def simulate(tour, a0):
    """最早開始スケジュールで到着 / 待ち / 開始時刻を計算する。

    未訪問頂点の arrival は L[v]+1 にして、plot_tour 側で違反 (赤) にする。
    """
    arrival = [L[v] + 1 for v in range(N)]
    wait = [0] * N
    start = [None] * N
    travel = 0
    now, prev = a0, 0
    for u in tour[1:-1]:
        arrive = now + c[prev][u]
        begin = max(arrive, E[u])
        arrival[u], wait[u], start[u] = arrive, begin - arrive, begin
        travel += c[prev][u]
        now, prev = begin, u
    travel += c[prev][0]
    ret = now + c[prev][0]
    arrival[0] = ret                # depot は帰着時刻を表示する
    return arrival, wait, start, travel, ret


# --------------------------------------------------------------------------
# 4. メイン
# --------------------------------------------------------------------------
def main(time_limit=DEFAULT_TIME):
    a0 = E[0]                                   # depot 出発時刻 (Dumas では 0)
    lo, hi = customer_bounds()
    unreachable = [u for u in range(1, N) if lo[u] > hi[u]]
    if unreachable:
        print(f"WARNING: 時間枠だけで到達不能な顧客があります: {unreachable}")

    cmin = min_leg()
    travel_lb, travel_ub = travel_range()
    dom = w_domains(lo, hi, a0, cmin)
    time_p, onehot_p, note = penalty_weights(dom, travel_lb, travel_ub)

    widths = [dom[i][1] - dom[i][0] for i in range(1, N)]
    print(f"N={N}  x vars = {N * N}  w vars = {N - 1} (整数)")
    print(f"w domain width = max {max(widths, default=0)} / "
          f"avg {sum(widths) / max(1, len(widths)):.1f}   "
          f"tsptw.py は全位置 (0, 100) 固定")
    print(f"OBJ_MODE = {OBJ_MODE}   TIME_P = {time_p}  "
          f"ONEHOT_P = {onehot_p}  <- {note}")

    t_build = time.perf_counter()

    # ---- 変数 -------------------------------------------------------------
    x = qbpp.var("x", shape=(N, N))

    # w[i]: 位置 i のサービス開始時刻 = 累積和の値そのもの。
    # tsptw.py は w[0] を作りながら一度も使っていなかった。ここでは位置 0 は
    # depot 出発時刻という定数なので、変数は i = 1..N-1 だけ (個数は同じ)。
    w = [qbpp.expr() + a0]
    for i in range(1, N):
        wlo, whi = dom[i]
        if wlo >= whi:
            w.append(qbpp.expr() + wlo)                     # 定数に潰す
        else:
            w.append(qbpp.var(f"w[{i}]", between=(wlo, whi)))

    # ---- leg[i]: 位置 i-1 -> i の移動時間 (x の 2 次式, Θ(N^2) 語) --------
    # 1 度だけ作って (P) と目的関数で共有する。tsptw.py のように累積しない。
    legs = [None] * N
    for i in range(1, N):
        leg = qbpp.expr()
        for u in range(N):
            for v in range(N):
                if u != v and c[u][v]:
                    leg += x[i - 1][u] * x[i][v] * c[u][v]
        legs[i] = leg

    return_leg = qbpp.expr()
    for u in range(1, N):
        if c[u][0]:
            return_leg += x[N - 1][u] * c[u][0]

    # ---- (R) (C) one-hot 制約 ---------------------------------------------
    # 宣言制約なのでペナルティ多項式もスラック変数も作られない。
    row_sums = qbpp.vector_sum(x, axis=1)       # 位置 i -> Σ_u x[i][u]
    col_sums = qbpp.vector_sum(x, axis=0)       # 顧客 u -> Σ_i x[i][u]
    row_constraint = qbpp.expr()
    col_constraint = qbpp.expr()
    for k in range(N):
        row_constraint += qbpp.cons(as_expr(row_sums[k]), equal=1)
        col_constraint += qbpp.cons(as_expr(col_sums[k]), equal=1)

    # ---- 時間制約 (すべて 1 段ぶんの差分。累積和は現れない) ---------------
    time_constraint = qbpp.expr()
    for i in range(1, N):
        # (P) 到着 (= w[i-1] + leg[i]) 以降にサービス開始。左辺が待ち時間。
        time_constraint += qbpp.cons(w[i] - w[i - 1] - legs[i],
                                     between=(0, None))
        # (T2) (T3) 時間枠。w[i] が絶対時刻なので Θ(N) 語で書ける。
        sum_E = qbpp.expr()
        sum_L = qbpp.expr()
        for u in range(1, N):
            if E[u]:
                sum_E += x[i][u] * E[u]
            if L[u]:
                sum_L += x[i][u] * L[u]
        time_constraint += qbpp.cons(w[i] - sum_E, between=(0, None))
        time_constraint += qbpp.cons(w[i] - sum_L, between=(None, 0))
    # (D) depot 帰着期限。tsptw.py はこれが無く、期限超過ツアーが
    #     「実行可能」として出てきていた。
    time_constraint += qbpp.cons(w[N - 1] + return_leg - L[0],
                                 between=(None, 0))

    # ---- 目的関数 ---------------------------------------------------------
    if OBJ_MODE == "makespan":
        objective = w[N - 1] + return_leg           # Θ(N) 語
    else:
        objective = qbpp.expr()                     # 総移動時間, Θ(N^3) 語
        for i in range(1, N):
            objective += legs[i]
        objective += return_leg

    f = (objective
         + onehot_p * (row_constraint + col_constraint)
         + time_p * time_constraint)

    # ---- 位置 0 は depot に固定 -------------------------------------------
    ml = {x[0][0]: 1}
    ml.update({x[0][u]: 0 for u in range(1, N)})
    ml.update({x[i][0]: 0 for i in range(1, N)})
    g = qbpp.replace(f, ml)

    f = qbpp.simplify_as_binary(f)
    g = qbpp.simplify_as_binary(g)

    build_sec = time.perf_counter() - t_build
    print(f"build       = {build_sec:.3f} sec  "
          f"(tsptw.py は Θ(N^4), 本版は Θ(N^3))")

    if BUILD_ONLY:
        return

    # ---- 探索 -------------------------------------------------------------
    solver = qbpp.ABS3Solver(g)
    print(f"solve now...({time_limit} sec)")
    sol = solver.search(time_limit=time_limit)
    full_sol = qbpp.Sol(f).set(sol, ml)

    print(f"\n----------result({time_limit} sec)----------")
    print("energy          =", full_sol(f))
    print("objective       =", full_sol(objective))
    print("violated cons   =", f.cons(full_sol))
    print("row_constraint  =", full_sol(row_constraint))
    print("col_constraint  =", full_sol(col_constraint))
    print("time_constraint =", full_sol(time_constraint))

    # ---- ツアーの取り出し -------------------------------------------------
    tour = [0]
    missing = []
    for i in range(1, N):
        picked = [u for u in range(1, N) if full_sol(x[i][u]) == 1]
        if len(picked) == 1:
            tour.append(picked[0])
        else:
            missing.append((i, len(picked)))
    tour.append(0)
    if missing:
        print("one-hot VIOLATION at (position, count):", missing)

    visited = sorted(tour[1:-1])
    if visited != list(range(1, N)):
        print(f"tour VIOLATION: 訪問顧客が {len(visited)} 個 (期待 {N - 1})")

    arrival, wait, start, travel, ret = simulate(tour, a0)

    print("\n---- 最早開始スケジュールで再検証 ----")
    bad = 0
    for i, u in enumerate(tour[1:-1], start=1):
        s = start[u]
        flag = ""
        if not (E[u] <= s <= L[u]):
            flag, bad = "  VIOLATION!", bad + 1
        print(f"pos{i:3d}: u={u:3d}  arrive={arrival[u]:4d} "
              f"wait={wait[u]:4d} start={s:4d}  [{E[u]:4d}, {L[u]:4d}] "
              f"w={full_sol(w[i]):4d}{flag}")
    if ret > L[0]:
        bad += 1
        print(f"depot 帰着 {ret} > L[0]={L[0]}  VIOLATION!")

    print("\ntour        =", tour)
    print("travel time =", travel)
    print("return      =", ret, f"(L[0]={L[0]})")
    print("time-window violations =", bad)
    print("var_count   =", sol.info["var_count"])
    print("term_count  =", sol.info["term_count"])

    # ---- 描画 -------------------------------------------------------------
    if PLOT and N <= PLOT_MAX_N:
        filename = "tsptw_pre_" + datetime.now().strftime("%m%d%H%M")
        nodes = recover_coordinates(c)
        plot_tour(nodes, tour, E, wait, arrival, L, c, filename)
        print("saved       =", f"results/{filename}.png")
    elif PLOT:
        print(f"skip plot   = N={N} > PLOT_MAX_N={PLOT_MAX_N}")


if __name__ == "__main__":
    main(float(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_TIME)
