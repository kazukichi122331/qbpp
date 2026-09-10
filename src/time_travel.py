"""
時間展開型 TSPTW QUBO — 課題1（総移動時間が目的関数に書けない）の解決版。

考え方
------
  総移動時間 = 帰着時刻 - 総待ち時間        （サービス時間は定数）

「総待ち時間」を在圏変数で表現する:

  x[t][v] = 1 <=> 頂点 v のサービスを時刻 t に開始する
  b[t][v] = 1 <=> 時刻 t に頂点 v に居る（到着済み・サービス前＝待機中）

  objective = t_RET - sum(b)          <- これが厳密に総移動時間

sum(b) を「最大化」する向きなので、b には上限（禁止）制約だけ与えれば
自動的に真の待ち時間まで埋まる。下限制約や max/min の表現が不要になるのが要点。

最早開始スケジュール（canonical schedule）への正規化
--------------------------------------------------
最早開始では t_v = max(arrival_v, E_v) なので、頂点 v での待ちは必ず
区間 [arrival_v, E_v) に入る。よって b の定義域を t < E_v に限れる。
どのツアーも最早開始スケジュールを持つので厳密性は失われず、
それ以外のスケジュール（途中で無駄に居座る解）は sum(b) が過小になり
objective が travel より大きく評価される => 最小化で自動的に排除される。
副作用として課題3（エネルギー地形の平坦性）も緩和される。

到着時刻下界の前処理
------------------
L[u] < E[v] なら u は必ず v に先行する。これを使って
  arr[v] = max( c[0][v],  max{ max(E[u],arr[u]) + s[u] + c[u][v] : L[u] < E[v] } )
を不動点まで回す。b の定義域が桁違いに縮む（n100w20 で 27245 -> 695）。
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

PREFIX = "tsptw_time_travel"            # 図のファイル名の先頭
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
    depot_l = L[0]
    ret = N
    cust = list(range(1, N))
    nodes = cust + [ret]

    t_build = time.perf_counter()

    # ---------------- 1. 到着時刻下界の前処理（不動点） ----------------
    arr = {v: c[0][v] for v in cust}
    must_before = {v: [u for u in cust if u != v and L[u] < E[v]] for v in cust}
    for _ in range(N + 5):
        changed = False
        for v in cust:
            lb = c[0][v]
            for u in must_before[v]:
                lb = max(lb, max(E[u], arr[u]) + s[u] + c[u][v])
            if lb > arr[v]:
                arr[v] = lb
                changed = True
        if not changed:
            break

    # ---------------- 2. 定義域 ----------------
    xlo = {v: max(E[v], arr[v]) for v in cust}
    xhi = {v: min(L[v], depot_l - s[v] - c[v][0]) for v in cust}
    xlo[ret] = max(xlo[v] + s[v] + c[v][0] for v in cust)
    xhi[ret] = depot_l

    # b は「最早開始での待機区間」= [arrival, E_v) にしか現れない
    blo = {v: arr[v] for v in cust}
    bhi = {v: E[v] - 1 for v in cust}

    # ---------------- 3. 変数 ----------------
    x = make_vars("x", xlo, xhi, nodes)
    b = make_vars("b", blo, bhi, cust)
    print(f"N={N}  x vars = {len(x)}  b vars = {len(b)}  "
          f"total = {len(x) + len(b)}")

    # ---------------- 4. 制約A: 各頂点ちょうど1回 ----------------
    # RET を落とすと makespan=0 で目的が一気に下がるので、顧客とは重みを分ける
    once_cust = qbpp.expr()
    for v in cust:
        once_cust += (qbpp.sum(x[t, v]
                               for t in range(xlo[v], xhi[v] + 1)) == 1)
    once_ret = (qbpp.sum(x[t, ret]
                         for t in range(xlo[ret], xhi[ret] + 1)) == 1)
    once_constraint = once_cust + once_ret

    # ---------------- 5. 制約B: 距離 + 前後関係（x と b の全組合せ） --------
    gap = make_gap(inst, s, ret)
    conflict_constraint = qbpp.expr()
    n_terms = 0
    for A, Alo, Ahi, B, Blo, Bhi in (
        (x, xlo, xhi, x, xlo, xhi),     # 訪問 -> 訪問
        (b, blo, bhi, x, xlo, xhi),     # 待機 -> 訪問
        (x, xlo, xhi, b, blo, bhi),     # 訪問 -> 待機
        (b, blo, bhi, b, blo, bhi),     # 待機 -> 待機
    ):
        expr, k = conflict_terms(nodes, gap, A, Alo, Ahi, B, Blo, Bhi)
        conflict_constraint += expr
        n_terms += k

    # 同一頂点: 待機は自分のサービス開始より真に前
    for v in cust:
        for t in range(blo[v], bhi[v] + 1):
            for tp in range(xlo[v], min(t, xhi[v]) + 1):
                conflict_constraint += b[t, v] * x[tp, v]
                n_terms += 1
    print(f"conflict terms = {n_terms}")

    # 待機の連続性: b[t][v]=1 なら t+1 も v に居るか、t+1 に v のサービスが始まる。
    # これが無いと「別の頂点への移動中に v を通過した」だけで sum(b) を稼げてしまい
    # （通過は待機ではないので）総移動時間が過小評価される。
    contiguity_constraint = qbpp.expr()
    for v in cust:
        for t in range(blo[v], bhi[v] + 1):
            nxt = qbpp.expr()
            if (t + 1, v) in b:
                nxt += b[t + 1, v]
            if (t + 1, v) in x:
                nxt += x[t + 1, v]
            contiguity_constraint += b[t, v] * (1 - nxt)

    # ---------------- 6. 目的関数: 総移動時間 ----------------
    makespan = qbpp.sum(t * x[t, ret]
                        for t in range(xlo[ret], xhi[ret] + 1))
    total_wait = qbpp.sum(b[t, v] for v in cust
                          for t in range(blo[v], bhi[v] + 1))
    objective = makespan - total_wait          # = 総移動時間

    # ---------------- 7. QUBO 化 ----------------
    # 重みは「違反1単位で得られる目的関数の改善」を上回れば十分。
    # depot_l+1 でも安全だが過大で、ペナルティ壁が急峻になり局所解から抜けにくくなる。
    maxc = max(max(row) for row in c)
    # RET を落とすと makespan が 0 になり目的が最大 depot_l 下がるので、
    # ここだけは大きい重みが必要
    P_RET = depot_l + 1
    # 顧客を1つ落として節約できる travel は c[pred][v]+c[v][succ] <= 2*max_c
    P_CUST = 4 * maxc + 1
    # 1違反でスケジュールを詰められる量は gap <= max_c
    P_CONF = 2 * maxc + 1
    # sum(b) が +1 されるだけ
    P_CONT = 2 * maxc + 1
    f = (objective
         + P_RET * qbpp.cons(once_ret)
         + P_CUST * qbpp.cons(once_cust)
         + P_CONF * qbpp.cons(conflict_constraint)
         + P_CONT * qbpp.cons(contiguity_constraint))
    print(f"penalty: RET={P_RET} CUST={P_CUST} CONF={P_CONF} CONT={P_CONT}")

    f, sol, val = solve(f, None, opt, build_sec=time.perf_counter() - t_build)
    if sol is None:                             # --build-only
        return

    print_energy(f, val, opt,
                 objective=objective,
                 makespan=makespan,
                 total_wait=total_wait,
                 once_constraint=once_constraint,
                 conflict_constr=conflict_constraint,
                 contiguity=contiguity_constraint)

    # ---------------- 8. 解の展開 ----------------
    tour, seq, start_t = recover_time_tour(inst, x, val, nodes, xlo, xhi, ret)
    sched = schedule_from_starts(inst, seq, s)
    print_time_detail(inst, seq, sched, quiet=opt.quiet)
    print(f"  return={sched.ret:4d} (RET var = {start_t.get(ret)})")
    print_summary(inst, tour, sched, sol)
    print("      (travel time は objective と一致すべき)")

    # ---------------- 9. 描画 ----------------
    save_plot(inst, tour, sched, PREFIX, opt)


if __name__ == "__main__":
    main(parse_args())
