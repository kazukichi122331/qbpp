"""時間展開型 TSPTW QUBO (在圏型) — 制約B の罰をずれの大きさに応じて変える版。

time_occupancy.py との違いは制約B（在圏の時空間衝突）の係数だけで、
禁止する組そのもの・他の制約・目的関数はそのまま。

発想
----
time_occupancy.py は禁止組 o[t,u]*o[t',v] (t <= t' < t + gap(u,v)) に一律
P_CONF = 2*max_c + 1 を掛ける。これは「1 違反で詰められる量は gap <= max_c」
という最悪ケースに合わせた値で、ほとんどの違反には過大である。
そこで組ごとに「実行可能な位置からどれだけ離れているか」

    δ = t + gap(u,v) - t'        （u -> v の順で見たときの不足時間, 1..gap）

を測り、係数を

    w(δ) = SLOPE * min(δ, max_c) + 1          （SLOPE = 2）

にする。t' が本来居るべき t + gap(u,v) から離れているほど（t' = t の
同時刻が最大）罰が大きく、窓の端（あと 1 で両立）では最小の 3 になる。
δ だけ詰める違反で目的関数（総移動時間）が稼げるのは高々 δ なので、
2δ+1 はその 2 倍 +1 で、元の 2*gap+1 と同じ余裕を組ごとに持たせたもの。

  - 同時刻 t' = t の組は両方向から禁止されるので、1 項にまとめて
    δ = min(gap(u,v), gap(v,u)) とする（time_occupancy.py では係数 2 だった）。
  - 帰着 RET が発側 (gap = ∞) の組は「帰着後に v に居る」で、
    直すには v を RET の c[v][0] 前まで戻す必要がある: δ = t' - t + c[v][0]。
    これは上限なしだと depot_l 程度まで伸びて壁が急峻になるので、
    min(δ, max_c) で頭打ちにする（最大値は元の P_CONF と一致する）。

したがって各組の係数は元の P_CONF 以下で、違反の浅い組ほど罰が軽い。
項数・変数数は time_occupancy.py と同じ（t'=t の重複をまとめる分だけ減る）。
係数の平均は n100w20.001 で 11.8（元は一律 125）。

実測 (60 秒, seed 1): n40w20.001 travel 500 (最適, TTS 7.7s, 元 4.4s)、
n100w20.001 travel 738 (最適, TTS 19.8s, 元 14.3s)。どちらも実行可能で
最適に届いたが、この 2 件では元より速くはなっていない。
"""
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
# ↑ src/ を探索パスに入れる (tsptwlib のため)。

import pyqbpp as qbpp

from tsptwlib import (arrival_lower_bounds, colocated_terms,
                      load_instance, make_gap, make_vars,
                      parse_args, print_energy, print_summary,
                      print_time_detail, recover_time_tour, save_plot,
                      schedule_from_starts, solve)

PREFIX = "tsptw_time_occupancy_penalty"  # 図のファイル名の先頭
RECOMMENDED_TIME = 60.0
SLOPE = 2                               # 不足時間 1 あたりの罰


def weighted_conflict_terms(nodes, gap, o, src_lo, lo, hi, dcap):
    """禁止組を不足時間 δ で重み付けした式と、その項数・係数の内訳を返す。

    組 (t,u),(t',v) (t <= t') の δ は、その組を禁止している方向ごとの
    不足時間の最小値（両方向が禁止するのは t' = t のときだけ）。
    src_lo は time_occupancy.py の --slim と同じく発側の下端。
    """
    delta = {}                      # (t, u, t', v) -> δ,  u < v で正規化

    def put(t, u, tp, v, d):
        key = (t, u, tp, v) if u < v else (tp, v, t, u)
        if key not in delta or d < delta[key]:
            delta[key] = d

    for u in nodes:
        for v in nodes:
            if u == v:
                continue
            g = gap(u, v)
            for t in range(src_lo[u], hi[u] + 1):
                tlo = max(t, lo[v])
                thi = hi[v] if g is qbpp.inf else min(t + g - 1, hi[v])
                for tp in range(tlo, thi + 1):
                    if g is qbpp.inf:       # u = RET: 帰着後に v に居る
                        d = tp - t + gap(v, u)
                    else:
                        d = t + g - tp
                    put(t, u, tp, v, d)

    expr = qbpp.expr()
    hist = {}
    for (t, u, tp, v), d in delta.items():
        w = SLOPE * min(d, dcap) + 1
        expr += w * o[t, u] * o[tp, v]
        hist[w] = hist.get(w, 0) + 1
    return expr, len(delta), hist


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

    # ---------------- 1〜3. 定義域と変数（time_occupancy.py と同じ） -------
    arr = arrival_lower_bounds(inst, s, cust)
    svc = {v: max(E[v], arr[v]) for v in cust}
    olo = {v: arr[v] for v in cust}
    ohi = {v: min(L[v], depot_l - s[v] - c[v][0]) for v in cust}
    svc[ret] = olo[ret] = max(svc[v] + s[v] + c[v][0] for v in cust)
    ohi[ret] = depot_l

    o = make_vars("o", olo, ohi, nodes)
    n_wait = sum(svc[v] - olo[v] for v in cust)
    print(f"N={N}  o vars = {len(o)}  (待機 {n_wait} / サービス {len(o) - n_wait})")

    # ---------------- 4. 制約A ----------------
    once_cust = qbpp.expr()
    for v in cust:
        once_cust += (qbpp.sum(o[t, v]
                               for t in range(svc[v], ohi[v] + 1)) == 1)
    once_ret = (qbpp.sum(o[t, ret]
                         for t in range(svc[ret], ohi[ret] + 1)) == 1)
    once_constraint = once_cust + once_ret

    # ---------------- 5. 制約B: 不足時間で重み付け ----------------
    maxc = max(max(row) for row in c)
    gap = make_gap(inst, s, ret)
    src_lo = svc if opt.slim else olo
    conflict_constraint, n_terms, hist = weighted_conflict_terms(
        nodes, gap, o, src_lo, olo, ohi, maxc)
    ws = sorted(hist)
    mean_w = sum(w * n for w, n in hist.items()) / max(n_terms, 1)
    print(f"conflict terms = {n_terms}  (係数 {ws[0]}..{ws[-1]}, "
          f"平均 {mean_w:.1f})" + ("  (slim)" if opt.slim else ""))

    colocated_constraint, n_col = colocated_terms(inst, cust, o, olo, svc, ohi)
    print(f"colocated terms = {n_col}")

    # ---------------- 6. 連続性 ----------------
    contiguity_constraint = qbpp.expr()
    for v in cust:
        for t in range(olo[v], min(svc[v], ohi[v] + 1)):
            nxt = qbpp.expr()
            if (t + 1, v) in o:
                nxt += o[t + 1, v]
            contiguity_constraint += o[t, v] * (1 - nxt)

    # ---------------- 7. 目的関数: 総移動時間 ----------------
    total_wait = qbpp.sum(o[t, v] for v in cust
                          for t in range(olo[v], svc[v]))
    objective = qbpp.sum(t * o[t, ret]
                         for t in range(svc[ret], ohi[ret] + 1)) - total_wait
    makespan = qbpp.sum(t * o[t, ret]
                        for t in range(svc[ret], ohi[ret] + 1))

    # ---------------- 8. QUBO 化 ----------------
    # 制約B の係数は式の中に入っている（最大 2*max_c+1 = 元の P_CONF）
    P_RET = depot_l + 1
    P_CUST = 4 * maxc + 1
    P_CONF = 2 * maxc + 1           # 同一地点ペア用（制約B には使わない）
    P_CONT = 2 * maxc + 1
    f = (objective
         + P_RET * qbpp.cons(once_ret)
         + P_CUST * qbpp.cons(once_cust)
         + qbpp.cons(conflict_constraint)
         + P_CONF * qbpp.cons(colocated_constraint)
         + P_CONT * qbpp.cons(contiguity_constraint))
    print(f"penalty: RET={P_RET} CUST={P_CUST} CONF=2*min(δ,{maxc})+1 "
          f"COLOC={P_CONF} CONT={P_CONT}")

    f, sol, val = solve(f, None, opt, build_sec=time.perf_counter() - t_build)
    if sol is None:                             # --build-only
        return

    print_energy(f, val, opt,
                 objective=objective,
                 makespan=makespan,
                 total_wait=total_wait,
                 once_constraint=once_constraint,
                 conflict_w=conflict_constraint,
                 colocated=colocated_constraint,
                 contiguity=contiguity_constraint)

    # ---------------- 9. 解の展開 ----------------
    x = {(t, v): o[t, v]
         for v in nodes for t in range(svc[v], ohi[v] + 1)}
    tour, seq, start_t = recover_time_tour(inst, x, val, nodes, svc, ohi, ret)
    sched = schedule_from_starts(inst, seq, s)
    print_time_detail(inst, seq, sched, quiet=opt.quiet)
    print(f"  return={sched.ret:4d} (RET var = {start_t.get(ret)})")
    print_summary(inst, tour, sched, sol)

    # ---------------- 10. 描画 ----------------
    save_plot(inst, tour, sched, PREFIX, opt)


if __name__ == "__main__":
    main(parse_args(supports=("slim",)))
