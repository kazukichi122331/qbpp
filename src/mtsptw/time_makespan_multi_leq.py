"""時間展開型 mTSPTW QUBO (min-max) — 「ret_v <= Z」を不等式制約でそのまま書く版。

    x[t][i][v] = 1 <=> 車両 v が頂点 i のサービスを時刻 t に開始する

頂点は 0 = 出発デポ、1..N = 顧客、N+1 = 帰着デポ（N は顧客数）。
0 は時刻 0 の出発に固定なので変数を持たない。

src/mtsptw/time_makespan_multi.py (--obj max) との関係
-----------------------------------------------
変数 x と制約 A, B は time_makespan_multi.py と同じ。違うのは最大値 Z の書き方だけ。

  time_makespan_multi.py   Z を one-hot z[T] で持ち、「Z >= ret_v」を禁止ペア
                               Σ_T Σ_{t > T} z[T] * x[t][N+1][v]    (= 0)
                           で書く。
  この版                   Z をネイティブ整数変数 (integer=) で持ち、車両ごとに不等式
                               ret_v = Σ_t t * x[t][N+1][v] <= Z
                           を qbpp.cons(..., between=(0, None)) で課す。

目的関数は Z そのもの。Z を実際の最大帰着時刻より下げると不等式が破れて罰せられ、
上げると目的関数が増えるので、最小化で Z = max_v ret_v に落ち着く。

宣言制約 qbpp.cons(body, between=(0, None)) はスラック変数を作らず、ソルバが
weight * max(0, -body)^2 を直接評価する (prec_disjunctive.py と同じ)。
したがって違反量 d = ret_v - Z に対してペナルティは d^2 で増える。

Z の定義域 [z_lo, depot_l] は time_makespan_multi.py と同じ
    z_lo = max_i (lo[i] + s[i] + c[i][N+1])
(どの顧客も誰かが回って帰るので m 台でも正当)。

使い方
------
    python src/mtsptw/time_makespan_multi_leq.py 60 -i instances/Dumas/n20w20.001.txt -m 2

車両数は -m / --vehicles（または環境変数 TSPTW_VEHICLES）。
"""
import os
import sys
import time

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path[:0] = [os.path.dirname(_HERE), _HERE]
# ↑ src/ (tsptwlib) と src/mtsptw/ (mtsptwlib) を探索パスに入れる。
#   python src/mtsptw/x.py でも python -m src.mtsptw.x でも動く。

import pyqbpp as qbpp

from tsptwlib import (conflict_terms, parse_args, print_energy,
                      print_time_detail, solve)
from mtsptwlib import (full_route, load_minstance, make_gap, make_vars_multi,
                       pop_vehicles, print_multi_summary, recover_routes,
                       save_plot_single, schedule_from_starts, simulate,
                       vehicle_view)

PREFIX = "tsptw_time_makespan_multi_leq"    # 図のファイル名の先頭
RECOMMENDED_TIME = 60.0                     # これより短いと解の骨格すら出にくい


def main(opt, m):
    inst = load_minstance(opt.instance)
    N, c, E, L = inst.N, inst.c, inst.E, inst.L
    print(inst.summary())
    print(f"vehicles    = {m}")
    print("objective   = max (帰着時刻の最大値, 不等式制約版)")
    if opt.time_limit < RECOMMENDED_TIME:
        print(f"HINT: この定式化はモデルが重いので "
              f"{RECOMMENDED_TIME:.0f} 秒以上を推奨 "
              f"(いまは {opt.time_limit} 秒)")

    s = [0] * (N + 2)               # Dumas はサービス時間なし
    end = inst.end                  # 帰着デポ N+1
    depot_l = L[end]
    cust = inst.customers           # 1..N
    nodes = cust + [end]
    veh = list(range(m))

    t_build = time.perf_counter()

    # ---------------- 1. 時刻ドメイン ----------------
    # time_makespan_multi.py と同じ。帰着デポ N+1 は車両ごとに [0, depot_l]。0 = 空車。
    lo = {i: max(E[i], c[0][i]) for i in cust}
    hi = {i: min(L[i], depot_l - s[i] - c[i][end]) for i in cust}
    lo[end] = 0
    hi[end] = depot_l

    dead = [i for i in cust if hi[i] < lo[i]]
    if dead:
        print(f"WARNING: 定義域が空の顧客 {dead} "
              f"(このインスタンスは実行不可能)")

    # ---------------- 2. 変数 ----------------
    x = make_vars_multi("x", lo, hi, nodes, veh)
    print(f"N={N}  m={m}  x vars = {len(x)}")

    # ---------------- 3. 制約A ----------------
    once_cust = qbpp.expr()
    for i in cust:
        once_cust += (qbpp.sum(x[t, i, v]
                               for v in veh
                               for t in range(lo[i], hi[i] + 1)) == 1)
    once_end = qbpp.expr()
    for v in veh:
        once_end += (qbpp.sum(x[t, end, v]
                              for t in range(lo[end], hi[end] + 1)) == 1)
    once_constraint = once_cust + once_end

    # ---------------- 4. 制約B: 車両ごとに 1 ブロック ----------------
    gap = make_gap(inst, s)
    conflict_constraint = qbpp.expr()
    n_terms = 0
    for v in veh:
        xv = vehicle_view(x, nodes, lo, hi, v)
        block, nb = conflict_terms(nodes, gap, xv, lo, hi, xv, lo, hi)
        conflict_constraint += block
        n_terms += nb
    print(f"conflict terms = {n_terms}")

    # ---------------- 5. 目的関数: Z と不等式 ret_v <= Z ----------------
    # 表示用の帰着時刻の和は別実体で作る (pyqbpp の演算が左辺を書き換えることがあるため)
    ret_total = qbpp.sum(t * x[t, end, v]
                         for v in veh
                         for t in range(lo[end], hi[end] + 1))
    z_lo = max(lo[i] + s[i] + c[i][end] for i in cust)
    # ネイティブ整数変数。幅 0 (z_lo == depot_l) なら pyqbpp が定数の式を返す
    Z = qbpp.var("Z", integer=(z_lo, depot_l))
    zmax_constraint = qbpp.expr()
    for v in veh:
        # body = Z - ret_v >= 0。本体は qbpp.expr() から組む (prec_disjunctive.py 参照)
        body = qbpp.expr() + Z
        for t in range(lo[end], hi[end] + 1):
            body -= t * x[t, end, v]
        zmax_constraint += qbpp.cons(body, between=(0, None))
    objective = qbpp.expr() + Z
    print(f"Z in [{z_lo}, {depot_l}] (integer)  ret<=Z cons = {m}")

    # ---------------- 6. QUBO 化 ----------------
    # ONCE, CONF は time_makespan_multi.py と同じ depot_l + 1。
    # ZMAX: 違反量 d >= 1 でペナルティ P*d^2、Z を下げて得する目的は高々 d なので
    # P > 1 で足りるが、他の制約と尺度をそろえて depot_l + 1 にする。
    ONCE_P = depot_l + 1
    CONF_P = depot_l + 1
    ZMAX_P = depot_l + 1
    f = (objective
         + ONCE_P * qbpp.cons(once_constraint)
         + CONF_P * qbpp.cons(conflict_constraint)
         + ZMAX_P * zmax_constraint)
    print(f"penalty: ONCE={ONCE_P} CONF={CONF_P} ZMAX={ZMAX_P}")

    f, sol, val = solve(f, None, opt, build_sec=time.perf_counter() - t_build)
    if sol is None:                             # --build-only
        mdl = qbpp.Model(f)
        print(f"qubo vars = {mdl.var_count}  qubo terms = {mdl.term_count()}")
        return

    print_energy(f, val, opt,
                 objective=objective,
                 ret_total=ret_total,
                 once_constraint=once_constraint,
                 conflict_constr=conflict_constraint,
                 zmax_constr=zmax_constraint)

    # ---------------- 7. 解の展開 ----------------
    routes, ret_t = recover_routes(inst, x, val, veh, lo, hi)
    scheds = {}
    for v in veh:
        seq = routes[v]
        sched = schedule_from_starts(inst, seq, s)
        scheds[v] = sched
        print(f"\n--- vehicle {v} --- ({len(seq)} 顧客)")
        print_time_detail(inst, seq, sched, quiet=opt.quiet)
        rv = ret_t[v][0] if len(ret_t[v]) == 1 else ret_t[v]
        print(f"  travel={sched.travel:4d} return={sched.ret:4d} "
              f"(x[·][{end}] = {rv})")

    print_multi_summary(inst, routes, scheds, ret_t, sol)
    # 検算値: 各ルートを最早開始で辿り直した帰着時刻（ソルバの時刻は使わない）
    rets = [simulate(inst, full_route(inst, routes[v])).ret for v in veh]
    print(f"max return  = {max(rets)} (最早開始。Z = {val(Z)} 以下になるはず)")
    print(f"used vehicles = {sum(1 for v in veh if routes[v])}/{m}")
    print("      (最遅以外の車両の帰着デポ変数は Z 以下のどこでも目的が変わらないので、\n"
          "       「帰着デポの変数 == モデルの帰着」は False になりうる)")

    # ---------------- 8. 描画 ----------------
    # plot_tour は単一ツアー前提。m >= 2 は描けないので m == 1 のときだけ。
    if m == 1:
        save_plot_single(inst, routes[0], s, PREFIX, opt)
    elif opt.plot:
        print("skip plot   = m >= 2 (plot_tour が単一ツアー前提のため)")


if __name__ == "__main__":
    _m, _rest = pop_vehicles()
    main(parse_args(_rest), _m)
