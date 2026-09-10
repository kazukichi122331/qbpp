"""順序型・累積式 TSPTW QUBO 定式化 —— この系統のいちばん最初の版。

    x[i][u] = 1  <=>  i 番目に顧客 u を訪れる            (バイナリ, N*N 個)
    w[i]          =   i 番目での待ち時間                 (整数, 0..100 固定)

時刻を変数に持たず、**累積式**として書くのが特徴。

    t[i]  = t[i-1] + Σ_{u≠v} x[i-1][u]·x[i][v]·c[u][v]   (i 番目までの移動時間)
    tw[i] = t[i] + Σ_{1<=j<i} w[j]                       (i 番目への到着時刻)
    サービス開始 = tw[i] + w[i]

制約は
    (R) 各位置に 1 顧客     Σ_u x[i][u] == 1     ← (Σx-1)^2 を展開する形
    (C) 各顧客を 1 回       Σ_i x[i][u] == 1     ← 同じ
    (T) 時間枠              E[u] <= tw[i]+w[i] <= L[u]
目的は総移動時間 t[N-1] + 帰着 leg。

==========================================================================
この版の弱点 (後続の版がそれぞれ直している)
==========================================================================
1. t[i] が t[i-1] を丸ごと含むので単項式数は |t[i]| = Θ(i·N^2)。
   構築コストもモデルサイズも Θ(N^4) になり、N=40 あたりで頭打ちになる。
   -> 差分形にして Θ(N^3) にしたのが order_prefix.py。

2. 待ち時間の上限 100 がマジックナンバー。時間枠が広いインスタンス
   (w40/w60/w100 系) では 100 を超える待ちが必要で、実行可能解を
   モデルから除外してしまう。
   -> インスタンスから上界を導出したのが order_wait.py。
   -> 待ちを明示変数にせず a[i] のスラックで表したのが order_start.py。

3. ペナルティ係数 ROW_P/COL_P = 5000, TIME_P = 1000 がインスタンス非依存の
   当て値。目的関数のスケールとの関係が保証されない。
   -> 目的関数の変域から決めたのが order_start.py、
      さらに制約族に優先順位を付けたのが order_start_tiered.py。

4. depot への帰着期限 L[0] を課していないので、期限超過のツアーが
   「実行可能」として出てくる。-> 後続版はすべて (T4)/(D) を持つ。

5. one-hot をペナルティ多項式 (Σx-1)^2 の展開で持つので O(N^3) 項になり、
   さらに全体を 1 個の qbpp.cons() で包んでいるため f.cons(sol) が
   「1 制約」としか数えず、違反本数が分からない。
   -> 後続版は qbpp.cons(body, equal=1) の宣言制約を 1 本ずつ張る。

比較のための基準として残してあるので、定式化そのものは当時のまま。
共通化したのは実行方法・インスタンス読み込み・解の検証・描画だけ。
"""
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
# ↑ src/ を探索パスに入れる。python src/x.py でも python -m src.x でも動く。

import pyqbpp as qbpp

from tsptwlib import (fix_map, load_instance, parse_args, print_energy,
                      print_order_detail, print_summary, recover_order_tour,
                      save_plot, simulate, solve, time_window_sums)

PREFIX = "tsptw_order_cumulative"       # 図のファイル名の先頭

# 当時の当て値をそのまま残している (弱点 3)
ROW_P = 5000
COL_P = 5000
TIME_P = 1000
WAIT_MAX = 100                          # 待ち時間変数の上限 (弱点 2)


def main(opt):
    inst = load_instance(opt.instance)
    N, c, L = inst.N, inst.c, inst.L
    print(inst.summary())
    print(f"N={N}  x vars = {N * N}  w vars = {N} (整数, 上限 {WAIT_MAX} 固定)")

    t_build = time.perf_counter()

    # ---- 変数 -------------------------------------------------------------
    x = qbpp.var("x", shape=(N, N))
    w = qbpp.var("w", shape=N, between=(0, WAIT_MAX))

    # ---- 累積移動時間 t[i] (ここが Θ(N^4) の原因) ------------------------
    t = [qbpp.expr()]
    for i in range(1, N):
        next_t = qbpp.copy(t[i - 1])
        for u in range(N):
            for v in range(N):
                if u != v:
                    next_t += x[i - 1][u] * x[i][v] * c[u][v]
        t.append(next_t)

    # ---- 到着時刻 tw[i] = 累積移動時間 + それまでの待ち時間 --------------
    tw = [qbpp.expr()]
    for i in range(1, N):
        tw.append(t[i] + sum(w[j] for j in range(1, i)))

    # ---- one-hot 制約 (ペナルティ多項式を展開する形。弱点 5) -------------
    row_constraint = qbpp.sum(qbpp.vector_sum(x, axis=1) == 1)
    col_constraint = qbpp.sum(qbpp.vector_sum(x, axis=0) == 1)

    # ---- 時間枠制約 -------------------------------------------------------
    time_constraint = qbpp.expr()
    for i in range(1, N):
        service_start = tw[i] + w[i]
        e_sum, l_sum = time_window_sums(inst, x, i)
        time_constraint += qbpp.cons(service_start - l_sum, between=(None, 0))
        time_constraint += qbpp.cons(service_start - e_sum, between=(0, None))

    # ---- 目的関数: 総移動時間 --------------------------------------------
    objective = t[N - 1] + qbpp.sum(x[N - 1][u] * c[u][0]
                                    for u in range(1, N))

    f = (objective
         + ROW_P * qbpp.cons(row_constraint)
         + COL_P * qbpp.cons(col_constraint)
         + TIME_P * time_constraint)
    print(f"ROW_P = {ROW_P}  COL_P = {COL_P}  TIME_P = {TIME_P} (固定値)")

    # ---- 位置 0 は depot に固定して探索 ----------------------------------
    ml = fix_map(inst, x)
    f, sol, val = solve(f, ml, opt, build_sec=time.perf_counter() - t_build)
    if sol is None:                             # --build-only
        return

    print_energy(f, val, opt,
                 objective=objective,
                 row_constraint=row_constraint,
                 col_constraint=col_constraint,
                 time_constraint=time_constraint)

    # ---- 復元と検証 -------------------------------------------------------
    tour, picked = recover_order_tour(inst, x, val)
    sched = simulate(inst, tour, inst.E[0])
    # このモデルの「サービス開始時刻」は tw[i] + w[i]
    solver_start = [qbpp.expr()] + [tw[i] + w[i] for i in range(1, N)]
    print_order_detail(inst, picked, sched, val,
                       a=solver_start, w=w, quiet=opt.quiet)
    print_summary(inst, tour, sched, sol)
    save_plot(inst, tour, sched, PREFIX, opt)


if __name__ == "__main__":
    main(parse_args())
