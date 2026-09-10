"""
順序型 (order-based) TSPTW QUBO 定式化 —— src/order_tsptw.py の改訂版。

変数
    x[i][u] = 1  <=>  i 番目に顧客 u を訪れる          (i, u = 0..N-1, 0 は depot)
    a[i]    = i 番目の顧客のサービス開始時刻            (整数変数, binary encoded)

制約
    (R) 各順序 i にちょうど 1 顧客        Σ_u x[i][u] == 1
    (C) 各顧客 u はちょうど 1 回           Σ_i x[i][u] == 1
    (T1) 時刻の単調性 + 移動時間           a[i] - a[i-1] - leg[i] >= 0
         leg[i] = Σ_{u,v} x[i-1][u] x[i][v] c[u][v]   (2 次)
    (T2) 時間枠 (早い側)                   a[i] - Σ_u x[i][u] E[u] >= 0
    (T3) 時間枠 (遅い側)                   a[i] - Σ_u x[i][u] L[u] <= 0
    (T4) depot 帰着期限                    a[N-1] + Σ_u x[N-1][u] c[u][0] - L[0] <= 0

目的
    総移動時間 = Σ_i leg[i] + Σ_u x[N-1][u] c[u][0]

--------------------------------------------------------------------------
order_tsptw.py からの主な修正点 / 改善点
--------------------------------------------------------------------------
1. 【致命的】式サイズが O(N^4) だったのを O(N^3) に。
   旧版は累積移動時間 t[i] を前方累積 (t[i] = t[i-1] + Σ x x c) で「展開した
   多項式」として保持し、その t[i] を N 本すべての時間枠制約に埋め込んでいた。
   t[i] は約 i*N^2 項なので、制約全体で Σ_i i*N^2 = O(N^4) 項になる。
   N=200 (src/dist_matrix.py の既定インスタンス) では 10^8 項オーダーで、
   モデル構築自体が終わらない。
   本版は順序ごとに整数変数 a[i] を置き、漸化式を「局所的な不等式」
   a[i] >= a[i-1] + leg[i] として課す。各制約は O(N^2) 項、合計 O(N^3)。

2. 【致命的】待ち時間変数の上限 100 がマジックナンバーだった。
   旧: w = qbpp.var("w", shape=N, between=(0, 100))
   時間枠が広いインスタンス (w40/w60/w100 系) では 100 を超える待ちが必要な
   ことがあり、実行可能解をモデルから除外していた。
   本版は待ち時間を明示変数にせず、a[i] のスラック (a[i] >= 到着時刻) として
   暗黙に表す。上限はインスタンスから導出した a[i] の定義域だけになる。

3. 【バグ】w[0] は生成されるが一度も使われず、ビットを無駄にしていた
   (tw[i] は j=1..i-1 の和、service_start は tw[i]+w[i] で i>=1)。
   a[] は順序 1..N-1 にだけ置くので無駄がない。

4. 【バグ】ペナルティ係数 TIME_P = 10 が目的関数のスケールに対して小さすぎた。
   宣言制約のエネルギー寄与は weight * violation^2 で、最小違反量は 1。
   つまり違反 1 のコストが 10 しかなく、移動時間を 10 以上削れるなら
   時間枠を破った方が得になる。ROW_P/COL_P = 50000 も同じくインスタンス
   非依存の当て値。
   本版は総移動時間の上界 travel_ub を計算し、全ペナルティを
   travel_ub + 1 に統一する (時間展開版 src/time_tsptw.py と同じ考え方)。

5. 【バグ】時間枠制約の Σ_u x[i][u] E[u] / L[u] が u=1..N-1 のみで、u=0 が
   抜けていた。x[i][0] を 0 に固定した g では偶然一致するが、固定前の f では
   別物になり、full_sol(f) や full_sol(time_constraint) の値が実際に解いた
   モデルと食い違う。本版は「許可された顧客集合」を明示して両者を一致させる。

6. 【バグ】depot への帰着期限 L[0] が全く課されていなかった。(T4) を追加。
   また depot 出発時刻を 0 決め打ちではなく E[0] とした。

7. 【改善】one-hot 制約を qbpp.cons(..., equal=1) の宣言制約に変更。
   旧: qbpp.sum(qbpp.vector_sum(x, axis=1) == 1) は (Σx - 1)^2 を N 本ぶん
   展開するので O(N^3) 項のペナルティ多項式を作る。さらに全体を 1 個の
   qbpp.cons() で包んでいたため f.cons(sol) が「1 制約」としか数えず、
   違反本数が分からなかった。
   宣言制約なら多項式を作らず (本体 + 上下限の記録のみ)、違反本数も行/列
   ごとに数えられる。

8. 【改善】定義域の枝刈りを追加。
   lo[u] = max(E[u], c[0][u]), hi[u] = min(L[u], L[0] - c[u][0]) と
   cmin = min_{u≠v} c[u][v] から順序 i の時刻範囲 [lo_pos[i], hi_pos[i]] を
   作り、時刻区間が交わらない (i, u) の x[i][u] を 0 に固定する。
   さらに「u より前に来られる顧客数 / 後に来られる顧客数」による順序の
   上下限も使う。これらは全て健全 (実行可能解を落とさない) で O(N^2)。
   固定は既存の ml/qbpp.replace の仕組みに乗せるだけなので、full_sol による
   復元もそのまま動く。

9. 【バグ】ツアー復元と描画のインデックスがずれていた。
   旧: tour は「x[i][u]==1 が見つかった順序」だけを append するので、訪問の
   ない順序があると長さが N-1 未満になり、続く
   `for i, u in enumerate(tour[:-1]): arrival_times[u] = full_sol(tw[i])`
   で順序 i と tw[i] の対応が崩れる。未訪問頂点も arrival=0 のまま
   「違反なし」として描かれていた。
   本版は順序ごとの選択結果をそのまま保持し、未訪問は L[v]+1 で初期化する。

10.【改善】QUBO のエネルギーとは独立に、復元したツアーを実際にシミュレート
   して移動時間と時間枠違反を検証する。ペナルティの重みづけを誤っても
   結果の良し悪しを見誤らない。

11.【改善】import と実行形態の整理。
    旧版は archive/tsptw_prev/tsptw_plot_no_e.py (5 引数版 plot_tour) を
    参照していて、src/plot_tsptw.py の 8 引数版とシグネチャが違う。
    本版は src/plot_tsptw.py を使い、`python -m src.new_tsptw` でも
    `python src/new_tsptw.py` でも動くように import をフォールバック。
    さらに全処理を main() に入れ (import しただけで解き始めない)、
    制限時間を引数で渡せるようにした。

備考 / 残る改善余地
    - a[i] を整数変数にしたことで、旧版の w[] と同程度のビット数は依然必要。
      定義域の幅は枝刈りで縮むが、時間枠の広いインスタンスでは大きくなる。
    - (T2)(T3) は one-hot が壊れた解では「Σ x E = Σ x L = 0」となり
      a[i] >= lo_pos[i] > 0 と衝突するので、空の順序に余分なペナルティが
      かかる。実行可能領域は変わらないが、違反本数の表示は水増しされる。
    - solver.hint() に貪欲解を渡す初期解投入は未実装。
"""
import os
import sys
from datetime import datetime

import pyqbpp as qbpp

try:                                        # python -m src.new_tsptw
    from src.dist_matrix import N, c, L, E
    from src.plot_tsptw import plot_tour, recover_coordinates
except ImportError:                         # python src/new_tsptw.py
    from dist_matrix import N, c, L, E
    from plot_tsptw import plot_tour, recover_coordinates

DEFAULT_TIME = 5.0
PLOT = os.environ.get("TSPTW_PLOT", "1") != "0"
PLOT_MAX_N = 60        # recover_coordinates() は N が大きいと非常に重い


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
# 1. インスタンスから定義域と枝刈りを作る
# --------------------------------------------------------------------------
def time_bounds():
    """顧客ごとのサービス開始時刻の下限 lo / 上限 hi。

    lo[u] : depot から直行しても c[0][u] はかかるので max(E[u], c[0][u])
    hi[u] : ここから depot に L[0] までに帰れる必要があるので
            min(L[u], L[0] - c[u][0])
    """
    lo = [0] * N
    hi = [0] * N
    lo[0] = E[0]
    hi[0] = L[0]
    for u in range(1, N):
        lo[u] = max(E[u], c[0][u])
        hi[u] = min(L[u], L[0] - c[u][0])
    return lo, hi


def min_leg():
    """u != v の最小移動時間。0 でも健全 (枝刈りが弱くなるだけ)。"""
    best = None
    for u in range(N):
        for v in range(N):
            if u != v and (best is None or c[u][v] < best):
                best = c[u][v]
    return 0 if best is None else best


def position_bounds(lo, hi, cmin, a0):
    """順序 i (1..N-1) のサービス開始時刻の下限 / 上限。

    a[i] >= a[i-1] + cmin, a[i] <= a[i+1] - cmin が成り立つので、
    両端から cmin ずつ積み上げる。
    """
    lo_pos = [0] * N
    hi_pos = [0] * N
    lo_pos[0] = a0
    hi_pos[0] = a0
    first_lo = max(min(lo[u] for u in range(1, N)), a0 + cmin)
    last_hi = max(hi[u] for u in range(1, N))
    for i in range(1, N):
        lo_pos[i] = first_lo + (i - 1) * cmin
        hi_pos[i] = last_hi - (N - 1 - i) * cmin
    return lo_pos, hi_pos


def order_bounds(lo, hi):
    """顧客 u が取り得る順序の下限 / 上限。

    サービス開始時刻はツアーに沿って単調非減少 (c >= 0) なので、
      u の前に来る顧客 v は lo[v] <= hi[u]
      u の後に来る顧客 v は hi[v] >= lo[u]
    を満たす。それぞれの個数が u の前後に必要な人数以上でなければならない。
    """
    first = [1] * N
    last = [N - 1] * N
    for u in range(1, N):
        preds = sum(1 for v in range(1, N) if v != u and lo[v] <= hi[u])
        succs = sum(1 for v in range(1, N) if v != u and hi[v] >= lo[u])
        first[u] = max(1, (N - 1) - succs)
        last[u] = min(N - 1, preds + 1)
    return first, last


def allowed_customers(lo, hi, lo_pos, hi_pos, first, last):
    """順序 i に置ける顧客の集合。allowed[0] は depot のみ。"""
    allowed = [[] for _ in range(N)]
    allowed[0] = [0]
    for i in range(1, N):
        for u in range(1, N):
            if not (first[u] <= i <= last[u]):
                continue
            if max(lo[u], lo_pos[i]) > min(hi[u], hi_pos[i]):
                continue
            allowed[i].append(u)
    return allowed


# --------------------------------------------------------------------------
# 2. 解の検証 (QUBO のエネルギーとは独立にツアーを直接シミュレートする)
# --------------------------------------------------------------------------
def simulate(tour, a0):
    """最早開始スケジュールで到着 / 待ち / 開始時刻を計算する。

    未訪問頂点の arrival は L[v]+1 にしておき、plot_tour 側で違反 (赤) として
    描かれるようにする。
    """
    arrival = [L[v] + 1 for v in range(N)]
    wait = [0] * N
    start = [None] * N
    travel = 0
    now, prev = a0, 0
    for u in tour[1:-1]:
        arrive = now + c[prev][u]
        begin = max(arrive, E[u])
        arrival[u] = arrive
        wait[u] = begin - arrive
        start[u] = begin
        travel += c[prev][u]
        now, prev = begin, u
    travel += c[prev][0]
    ret = now + c[prev][0]
    arrival[0] = ret                # depot は帰着時刻を表示する
    return arrival, wait, start, travel, ret


# --------------------------------------------------------------------------
# 3. メイン
# --------------------------------------------------------------------------
def main(time_limit=DEFAULT_TIME):
    lo, hi = time_bounds()
    infeasible = [u for u in range(1, N) if lo[u] > hi[u]]
    if infeasible:
        print(f"WARNING: 時間枠だけで到達不能な顧客があります: {infeasible}")

    a0 = E[0]                       # depot 出発時刻 (Dumas では 0)
    cmin = min_leg()
    lo_pos, hi_pos = position_bounds(lo, hi, cmin, a0)
    first, last = order_bounds(lo, hi)
    allowed = allowed_customers(lo, hi, lo_pos, hi_pos, first, last)

    empty_pos = [i for i in range(1, N) if not allowed[i]]
    unplaceable = [u for u in range(1, N)
                   if not any(u in allowed[i] for i in range(1, N))]
    if empty_pos or unplaceable:
        print(f"WARNING: 枝刈りで空になった順序={empty_pos} "
              f"置けない顧客={unplaceable}")

    kept = sum(len(allowed[i]) for i in range(N))
    print(f"N={N}  x vars = {N * N} -> {kept} "
          f"(枝刈りで {N * N - kept} 個を 0 に固定)")

    # ---- 変数 -------------------------------------------------------------
    x = qbpp.var("x", shape=(N, N))

    # a[i]: 順序 i のサービス開始時刻。定義域は許可顧客と順序の両方で絞る。
    # a[0] は depot 出発時刻なので定数。
    a = [a0]
    for i in range(1, N):
        if allowed[i]:
            a_lo = max(lo_pos[i], min(lo[u] for u in allowed[i]))
            a_hi = min(hi_pos[i], max(hi[u] for u in allowed[i]))
        else:
            a_lo, a_hi = lo_pos[i], hi_pos[i]
        if a_lo >= a_hi:
            a.append(qbpp.expr() + a_lo)            # 定数に潰す
        else:
            a.append(qbpp.var(f"a[{i}]", between=(a_lo, a_hi)))

    # ---- leg[i]: 順序 i に入るための移動時間 (2 次) -----------------------
    # 0 に固定される x の組は最初から作らない (g では消え、f では full_sol が
    # 同じ値を入れるので両者は一致する)。
    legs = [None] * N
    for i in range(1, N):
        leg = qbpp.expr()
        for u in allowed[i - 1]:
            for v in allowed[i]:
                if u != v and c[u][v]:
                    leg += x[i - 1][u] * x[i][v] * c[u][v]
        legs[i] = leg

    return_leg = qbpp.expr()
    for u in allowed[N - 1]:
        if c[u][0]:
            return_leg += x[N - 1][u] * c[u][0]

    # ---- one-hot 制約 (宣言制約: ペナルティ多項式を作らない) --------------
    row_sums = qbpp.vector_sum(x, axis=1)   # 順序 i -> Σ_u x[i][u]
    col_sums = qbpp.vector_sum(x, axis=0)   # 顧客 u -> Σ_i x[i][u]
    row_constraint = qbpp.expr()
    col_constraint = qbpp.expr()
    for i in range(N):
        row_constraint += qbpp.cons(as_expr(row_sums[i]), equal=1)
        col_constraint += qbpp.cons(as_expr(col_sums[i]), equal=1)

    # ---- 時間制約 ---------------------------------------------------------
    time_constraint = qbpp.expr()
    for i in range(1, N):
        # (T1) 到着してからサービス開始。差は待ち時間 (>= 0) になる。
        time_constraint += qbpp.cons(a[i] - a[i - 1] - legs[i],
                                     between=(0, None))
        e_sum = qbpp.expr()
        l_sum = qbpp.expr()
        for u in allowed[i]:
            e_sum += x[i][u] * E[u]
            l_sum += x[i][u] * L[u]
        # (T2) E[u] <= a[i]
        time_constraint += qbpp.cons(a[i] - e_sum, between=(0, None))
        # (T3) a[i] <= L[u]
        time_constraint += qbpp.cons(a[i] - l_sum, between=(None, 0))
    # (T4) depot 帰着期限
    time_constraint += qbpp.cons(a[N - 1] + return_leg - L[0],
                                 between=(None, 0))

    # ---- 目的関数: 総移動時間 --------------------------------------------
    objective = qbpp.expr()
    for i in range(1, N):
        objective += legs[i]
    objective += return_leg

    # ---- ペナルティ係数をインスタンスから決める --------------------------
    # 宣言制約のエネルギー寄与は weight * violation^2 で violation >= 1。
    # 目的関数の上界より大きい重みなら、違反して移動時間を稼ぐ得はなくなる。
    travel_ub = sum(max(c[u][v] for v in range(N) if v != u)
                    for u in range(N))
    penalty = travel_ub + 1
    ROW_P = COL_P = TIME_P = penalty
    print(f"travel_ub = {travel_ub}  penalty = {penalty}")

    f = (objective
         + ROW_P * row_constraint
         + COL_P * col_constraint
         + TIME_P * time_constraint)

    # ---- 固定 (depot + 枝刈り) -------------------------------------------
    ml = {}
    for i in range(N):
        keep = set(allowed[i])
        for u in range(N):
            if u not in keep:
                ml[x[i][u]] = 0
    ml[x[0][0]] = 1

    g = qbpp.replace(f, ml)
    f = qbpp.simplify_as_binary(f)
    g = qbpp.simplify_as_binary(g)

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

    # ---- ツアー復元 (順序 -> 顧客の対応をそのまま保持する) ---------------
    picked = [[u for u in allowed[i] if full_sol(x[i][u]) == 1]
              for i in range(N)]
    tour = [0]
    for i in range(1, N):
        if len(picked[i]) == 1:
            tour.append(picked[i][0])
    tour.append(0)

    arrival, wait, start, travel, ret = simulate(tour, a0)

    for i in range(1, N):
        if len(picked[i]) != 1:
            print(f"order{i:3d}: {picked[i]} VIOLATION! (one-hot)")
            continue
        u = picked[i][0]
        begin = start[u]
        flag = "" if begin is not None and begin <= L[u] else " VIOLATION!"
        print(f"order{i:3d}: u={u:3d} "
              f"solver_start={full_sol(a[i]):5d} "
              f"arrive={arrival[u]:5d} wait={wait[u]:5d} "
              f"start={begin if begin is not None else '-':>5} "
              f"[{E[u]:5d}, {L[u]:5d}]{flag}")

    visited = [u for u in tour[1:-1]]
    dup = len(visited) != len(set(visited))
    print("tour        =", tour)
    print(f"visited     = {len(set(visited))}/{N - 1}"
          f"{'  (重複あり)' if dup else ''}")
    print("travel time =", travel)
    print(f"return      = {ret} (limit {L[0]})"
          f"{'  VIOLATION!' if ret > L[0] else ''}")
    tw_violations = sum(1 for u in visited
                        if start[u] is None or start[u] > L[u])
    print("tw violations =", tw_violations)
    print("var_count   =", sol.info["var_count"])
    print("term_count  =", sol.info["term_count"])

    # ---- 描画 -------------------------------------------------------------
    if PLOT and N <= PLOT_MAX_N:
        filename = "tsptw_order_" + datetime.now().strftime("%m%d%H%M")
        nodes = recover_coordinates(c)
        plot_tour(nodes, tour, E, wait, arrival, L, c, filename)
        print("saved       =", f"results/{filename}.png")
    elif PLOT:
        print(f"skip plot   = N={N} > PLOT_MAX_N={PLOT_MAX_N} "
              "(recover_coordinates が重いため)")


if __name__ == "__main__":
    main(float(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_TIME)
