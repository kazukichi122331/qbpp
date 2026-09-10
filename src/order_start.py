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
   N=200 (src/tsptwlib/instance.py の既定インスタンス) では 10^8 項オーダーで、
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
   travel_ub + 1 に統一する (時間展開版 src/time_makespan.py と同じ考え方)。

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
    参照していて、src/tsptwlib/plot.py の 8 引数版とシグネチャが違う。
    本版は src/tsptwlib/plot.py を使い、`python -m src.order_start` でも
    `python src/order_start.py` でも動くように import をフォールバック。
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
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
# ↑ src/ を探索パスに入れる。python src/x.py でも python -m src.x でも動く。

import pyqbpp as qbpp

from tsptwlib import (build_legs, fix_map, load_instance, onehot_constraints,
                      parse_args, prepare_order, print_energy,
                      print_order_detail, print_summary, recover_order_tour,
                      report_pruning, save_plot, simulate, solve, start_vars,
                      time_window_sums)

PREFIX = "tsptw_order_start"            # 図のファイル名の先頭


def main(opt):
    inst = load_instance(opt.instance)
    N, L = inst.N, inst.L
    print(inst.summary())

    # ---- 前処理: 定義域と枝刈り -------------------------------------------
    b = prepare_order(inst)
    report_pruning(inst, b)

    t_build = time.perf_counter()

    # ---- 変数 -------------------------------------------------------------
    x = qbpp.var("x", shape=(N, N))
    a = start_vars(inst, b.dom)         # a[i] = 位置 i のサービス開始時刻

    # ---- leg[i]: 位置 i に入るための移動時間 (2 次) -----------------------
    legs, return_leg = build_legs(inst, x, b.allowed)

    # ---- one-hot 制約 (宣言制約: ペナルティ多項式を作らない) --------------
    row_constraint, col_constraint = onehot_constraints(inst, x)

    # ---- 時間制約 ---------------------------------------------------------
    time_constraint = qbpp.expr()
    for i in range(1, N):
        # (T1) 到着してからサービス開始。差は待ち時間 (>= 0) になる。
        time_constraint += qbpp.cons(a[i] - a[i - 1] - legs[i],
                                     between=(0, None))
        e_sum, l_sum = time_window_sums(inst, x, i, b.allowed)
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
    # ただし全制約に一律なので、違反量が「時刻」単位の時間制約が
    # one-hot より安くなる。その弱点を直したのが order_start_tiered.py。
    penalty = b.travel_ub + 1
    ROW_P = COL_P = TIME_P = penalty
    print(f"travel_ub = {b.travel_ub}  penalty = {penalty}")

    f = (objective
         + ROW_P * row_constraint
         + COL_P * col_constraint
         + TIME_P * time_constraint)

    # ---- 固定 (depot + 枝刈り) と探索 ------------------------------------
    ml = fix_map(inst, x, b.allowed)
    f, sol, val = solve(f, ml, opt, build_sec=time.perf_counter() - t_build)
    if sol is None:                     # --build-only
        return

    print_energy(f, val, opt,
                 objective=objective,
                 row_constraint=row_constraint,
                 col_constraint=col_constraint,
                 time_constraint=time_constraint)

    # ---- 復元と検証 -------------------------------------------------------
    tour, picked = recover_order_tour(inst, x, val, b.allowed)
    sched = simulate(inst, tour, b.a0)
    print_order_detail(inst, picked, sched, val, a=a, quiet=opt.quiet)
    print_summary(inst, tour, sched, sol)
    save_plot(inst, tour, sched, PREFIX, opt)


if __name__ == "__main__":
    main(parse_args())
