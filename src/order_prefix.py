"""
prefix-free (差分形) TSPTW QUBO 定式化 —— src/order_cumulative.py の O(N^4) 構築を O(N^3) に。

変数は order_cumulative.py と同じ x と w の 2 種類だけ。新しい変数は 1 つも足していない。

    x[i][u] = 1  <=>  i 番目に顧客 u を訪れる            (バイナリ, N*N 個)
    w[i]          =   i 番目のサービス開始時刻            (整数,     N-1 個)

==========================================================================
1. order_cumulative.py が O(N^4) になる理由
==========================================================================
order_cumulative.py は時刻を「式」として持っていた。

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
order_cumulative.py の w は「待ち時間」だったが、ここでは

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
                                                        (order_cumulative.py に無かった)

body の単項式数:

    (P)  Θ(N^2) × (N-1) 本  = Θ(N^3)   <- ここが支配項
    (T2) Θ(N)   × (N-1) 本  = Θ(N^2)
    (T3) Θ(N)   × (N-1) 本  = Θ(N^2)
    (D)  Θ(N)   × 1 本      = Θ(N)
    目的 (総移動時間)        = Θ(N^3)   (leg[i] を (P) と共有するので追加ゼロ)

合計 Θ(N^3)。order_cumulative.py より N の 1 乗ぶん軽い。leg[i] は 1 度だけ作って
(P) と目的関数で共有するので、実測の定数倍も小さくなる。

(P) を等式ではなく不等式にしているのがポイント。order_cumulative.py の w が
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

(c) **時間展開型 (src/time_makespan.py)**
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
4. 使い方 (オプションは全定式化で共通。詳細は README.md)
==========================================================================
    python src/order_prefix.py 10                    # 10 秒探索
    python src/order_prefix.py --build-only          # 構築時間だけ測る
    python src/order_prefix.py 10 --obj makespan     # 目的関数を帰着時刻にする
    python src/order_prefix.py 10 -i instances/Dumas/n60w100.001.txt
"""
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
# ↑ src/ を探索パスに入れる。python src/x.py でも python -m src.x でも動く。

import pyqbpp as qbpp

from tsptwlib import (build_legs, customer_time_bounds, dmax_order, fix_map,
                      load_instance, max_leg, min_leg, onehot_constraints,
                      parse_args, penalty_weights, prefix_domains,
                      print_energy, print_order_detail, print_summary,
                      recover_order_tour, save_plot, simulate, solve,
                      start_vars, time_window_sums, travel_range)

PREFIX = "tsptw_order_prefix"           # 図のファイル名の先頭

# "travel"   : 総移動時間 (order_cumulative.py と同じ, 既定)。leg を (P) と共有する
# "makespan" : depot 帰着時刻。目的関数は Θ(N) 語だけになる (3 節 (d))
OBJ_CHOICES = ("travel", "makespan")


def main(opt):
    inst = load_instance(opt.instance)
    N, L = inst.N, inst.L
    print(inst.summary())

    # ---- 前処理 -----------------------------------------------------------
    # 本版は枝刈り (allowed) を持たない。定義域を絞るだけで、x は N*N 全部作る。
    # 枝刈りまで入れたのが order_wait.py / order_start*.py。
    a0 = inst.E[0]                              # depot 出発時刻 (Dumas では 0)
    lo, hi = customer_time_bounds(inst)
    unreachable = [u for u in range(1, N) if lo[u] > hi[u]]
    if unreachable:
        print(f"WARNING: 時間枠だけで到達不能な顧客があります: {unreachable}")

    cmin = min_leg(inst)
    travel_lb, travel_ub = travel_range(inst)
    dom = prefix_domains(inst, lo, hi, a0, cmin)

    widths = [dom[i][1] - dom[i][0] for i in range(1, N)]
    print(f"N={N}  x vars = {N * N}  w vars = {N - 1} (整数)")
    print(f"w domain width = max {max(widths, default=0)} / "
          f"avg {sum(widths) / max(1, len(widths)):.1f}   "
          f"order_cumulative.py は全位置 (0, 100) 固定")

    t_build = time.perf_counter()

    # ---- 変数 -------------------------------------------------------------
    x = qbpp.var("x", shape=(N, N))
    # w[i]: 位置 i のサービス開始時刻 = 累積和の値そのもの。
    # order_cumulative.py は w[0] を作りながら一度も使っていなかった。ここでは
    # 位置 0 は depot 出発時刻という定数なので、変数は i = 1..N-1 だけ (個数は同じ)。
    w = start_vars(inst, dom, name="w")

    # ---- leg[i]: 位置 i-1 -> i の移動時間 (x の 2 次式, Θ(N^2) 語) --------
    # 1 度だけ作って (P) と目的関数で共有する。累積はしない。
    legs, return_leg = build_legs(inst, x)      # allowed なし = 枝刈りしない

    # ---- (R) (C) one-hot 制約 ---------------------------------------------
    row_constraint, col_constraint = onehot_constraints(inst, x)

    # ---- 時間制約 (すべて 1 段ぶんの差分。累積和は現れない) ---------------
    time_constraint = qbpp.expr()
    for i in range(1, N):
        # (P) 到着 (= w[i-1] + leg[i]) 以降にサービス開始。左辺が待ち時間。
        time_constraint += qbpp.cons(w[i] - w[i - 1] - legs[i],
                                     between=(0, None))
        # (T2) (T3) 時間枠。w[i] が絶対時刻なので Θ(N) 語で書ける。
        e_sum, l_sum = time_window_sums(inst, x, i)
        time_constraint += qbpp.cons(w[i] - e_sum, between=(0, None))
        time_constraint += qbpp.cons(w[i] - l_sum, between=(None, 0))
    # (D) depot 帰着期限。order_cumulative.py はこれが無く、期限超過ツアーが
    #     「実行可能」として出てきていた。
    time_constraint += qbpp.cons(w[N - 1] + return_leg - L[0],
                                 between=(None, 0))

    # ---- 目的関数 ---------------------------------------------------------
    if opt.obj == "makespan":
        objective = w[N - 1] + return_leg           # Θ(N) 語
    else:
        objective = qbpp.expr()                     # 総移動時間, Θ(N^3) 語
        for i in range(1, N):
            objective += legs[i]
        objective += return_leg

    # ---- ペナルティ係数 (階層化) -----------------------------------------
    # 枝刈りがないので、leg の上界は位置ごとではなく一括の max leg を使う。
    dmax = dmax_order(inst, dom, leg_max=max_leg(inst))
    time_p = (travel_ub - travel_lb + 1) if opt.obj == "travel" else (L[0] + 1)
    TIME_P, ONEHOT_P, info = penalty_weights(
        time_p=time_p, dmax=dmax,
        onehot_ratio=opt.onehot_ratio,
        travel=(travel_lb, travel_ub),
    )
    print(info)
    print(f"objective   = {opt.obj}")

    f = (objective
         + ONEHOT_P * (row_constraint + col_constraint)
         + TIME_P * time_constraint)

    # ---- 位置 0 は depot に固定して探索 ----------------------------------
    ml = fix_map(inst, x)                       # allowed なし = depot だけ固定
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
    sched = simulate(inst, tour, a0)
    print_order_detail(inst, picked, sched, val, a=w, quiet=opt.quiet)
    print_summary(inst, tour, sched, sol)
    save_plot(inst, tour, sched, PREFIX, opt)


if __name__ == "__main__":
    main(parse_args(obj_choices=OBJ_CHOICES, supports=("onehot_ratio",)))
