"""
時間展開型 (time-indexed) TSPTW QUBO 定式化。

各頂点 v を「離散時刻ごとに独立した別ノード」に分割し、
  x[t][v] = 1  <=>  頂点 v のサービスを時刻 t に開始する
とする。訪問順インデックス i は使わない（順序は時刻から導出される）。

  制約A: 各 v はちょうど 1 つの t を持つ            -> 次数 2
  制約B: t <= t' < t + s[u] + c[u][v] なる (t,u),(t',v) を禁止  -> 次数 2
         ここに「距離」と「前後関係」が同時に入る
         s[u]は顧客uでのサービス時間
  時間窓: 変数の定義域そのもの                      -> ペナルティ不要

  目的:  depot への帰着時刻（makespan）を最小化

残っている課題
    総移動時間そのものは x[t][v] の 2 次式では書けないので、
    ここでは makespan (= 総移動時間 + 総待ち時間) を最小化している。
    待ち時間を在圏変数 b[t][v] で表して総移動時間を厳密に書いたのが
    time_travel.py。

    モデルは時間枠の幅に強く依存する (変数は Σ_v |時間枠| 個)。
    w100 系のインスタンスでは項数が 10^5 を超えるので、
    制限時間は 60 秒以上を見た方がよい。
"""
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
# ↑ src/ を探索パスに入れる。python src/x.py でも python -m src.x でも動く。

import pyqbpp as qbpp

from tsptwlib import (conflict_terms, load_instance, make_gap, make_vars,
                      parse_args, print_energy, print_summary,
                      print_time_detail, recover_time_tour, save_plot,
                      schedule_from_starts, solve)

PREFIX = "tsptw_time_makespan"          # 図のファイル名の先頭
RECOMMENDED_TIME = 60.0                 # これより短いと解の骨格すら出にくい


def main(opt):
    inst = load_instance(opt.instance)
    N, c, E, L = inst.N, inst.c, inst.E, inst.L
    print(inst.summary())
    if opt.time_limit < RECOMMENDED_TIME:
        print(f"HINT: この定式化はモデルが重いので "
              f"{RECOMMENDED_TIME:.0f} 秒以上を推奨 "
              f"(いまは {opt.time_limit} 秒)")

    s = [0] * (N + 1)               # Dumas はサービス時間なし
    depot_l = L[0]                  # 帰着期限
    ret = N                         # depot 帰着を表す「もう一つのノード」
    nodes = list(range(1, N)) + [ret]

    t_build = time.perf_counter()

    # ---------------- 1. 時刻ドメインの枝刈り ----------------
    # lo[v]: v のサービス開始可能な最早時刻
    #        三角不等式より、誰よりも早く v に着けるのは depot から直行した場合
    # hi[v]: そこから depot に帰着できる最遅時刻
    lo = {v: max(E[v], c[0][v]) for v in range(1, N)}
    hi = {v: min(L[v], depot_l - s[v] - c[v][0]) for v in range(1, N)}
    lo[ret] = max(lo[v] + s[v] + c[v][0] for v in range(1, N))
    hi[ret] = depot_l

    # ---------------- 2. 変数（存在するものだけ生成） ----------------
    x = make_vars("x", lo, hi, nodes)
    print(f"N={N}  x vars = {len(x)}  (order-based なら {(N - 1) ** 2})")

    # ---------------- 3. 制約A: 各頂点ちょうど 1 回 ----------------
    # 「重複訪問にペナルティ」だけでは全ゼロ解が最適になるので等式にする
    once_constraint = qbpp.expr()
    for v in nodes:
        once_constraint += (qbpp.sum(x[t, v]
                                     for t in range(lo[v], hi[v] + 1)) == 1)

    # ---------------- 4. 制約B: 距離 + 前後関係 ----------------
    gap = make_gap(inst, s, ret)
    conflict_constraint, n_terms = conflict_terms(nodes, gap,
                                                  x, lo, hi, x, lo, hi)
    print(f"conflict terms = {n_terms}")

    # ---------------- 5. 目的関数: 帰着時刻 ----------------
    # makespan = 総移動時間 + 総待ち時間（サービス時間は定数）
    objective = qbpp.sum(t * x[t, ret]
                         for t in range(lo[ret], hi[ret] + 1))

    # ---------------- 6. QUBO 化 ----------------
    # 制約違反は必ず整数 >= 1、目的関数は O(depot_l) なので
    # ペナルティは depot_l より少し大きいだけでよい（順序型の 50000 は不要）
    ONCE_P = depot_l + 1
    CONF_P = depot_l + 1
    f = (objective
         + ONCE_P * qbpp.cons(once_constraint)
         + CONF_P * qbpp.cons(conflict_constraint))
    print(f"penalty: ONCE={ONCE_P} CONF={CONF_P}")

    f, sol, val = solve(f, None, opt, build_sec=time.perf_counter() - t_build)
    if sol is None:                             # --build-only
        return

    print_energy(f, val, opt,
                 objective=objective,
                 once_constraint=once_constraint,
                 conflict_constr=conflict_constraint)

    # ---------------- 7. 解の展開 ----------------
    tour, seq, start_t = recover_time_tour(inst, x, val, nodes, lo, hi, ret)
    sched = schedule_from_starts(inst, seq, s)
    print_time_detail(inst, seq, sched, quiet=opt.quiet)
    print(f"  return={sched.ret:4d} (RET var = {start_t.get(ret)})")
    print_summary(inst, tour, sched, sol)

    # ---------------- 8. 描画 ----------------
    save_plot(inst, tour, sched, PREFIX, opt)


if __name__ == "__main__":
    main(parse_args())
