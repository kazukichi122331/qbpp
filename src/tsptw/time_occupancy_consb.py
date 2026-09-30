"""時間展開型 TSPTW QUBO (在圏型) — 制約B を「許可側」でも書けるようにした版。

time_occupancy.py との違いは制約B（在圏の時空間衝突）の書き方だけで、
変数・制約A・連続性・同一地点ペア・目的関数はそのまま。

発想: 禁止項の代わりに「満たしている組」をマイナスで与える
--------------------------------------------------------------
単純に全体を反転する（許可される組 o[t,u]*o[t',v] に -1 を与える）と、
項数はかえって 10〜40 倍に増える。時間窓が地平線に比べて狭いので、
大半の頂点ペアは時刻が遠く離れていて「全部許可」だからである
（n100w20.001 のサービス×サービスで 禁止 4.2 万 / 許可 196 万）。

そこで反転を「行」単位で選ぶ。v のサービス域は制約A で one-hot
（Σ_{t'∈S_v} o[t',v] = 1）なので、発側の 1 スロット r = (t,u) を固定すると

    o_r * Σ_{t'∈F_r} o[t',v]  =  o_r * (1 - Σ_{t'∈C_r} o[t',v])     (one-hot 下)

が成り立つ。F_r は r と両立しない v のスロット、C_r = S_v \\ F_r が両立する
スロット。右辺は「満たしている組」を -1 で与え、定数 1 を o_r の 1 次項に
押し込んだ形で、二次項は |C_r| 個になる。行ごとに |F_r| と |C_r| の小さい
方を選ぶ。禁止窓の幅は最大 gap(u,v)+gap(v,u)-1 で、v の定義域がそれより
狭い（時間窓が狭い・距離が長い）行ほど許可側が得をする。

  - 相手側 (v) がサービス域のときだけ使える（待機域は one-hot ではない）。
    発側 r は待機スロットでもよい。
  - (u,v) ともサービス域のブロックは「u を行にする」か「v を行にする」かを
    ブロックごとに選ぶ（混ぜると同じ組を 2 回数える）。
  - 待機×待機は従来どおり禁止側だけ。
  - 同時刻 t'=t の組は time_occupancy.py では両方向から数えて係数 2 に
    なっていたが、ここでは 1 回だけ数える（係数 1）。

項数（ユニークな禁止組の数に対する二次項の数）:
  n40w20.001 56%、n100w20.001 66%、n40w100.001 86%、n60w100.001 82%

代償: one-hot が破れたときの報酬
--------------------------------
o_r * (1 - Σ_C o_v) = o_r * Σ_F o_v + o_r * (1 - S_v)   (S_v = Σ_{S_v} o)
なので、S_v = 1 なら元の禁止項と一致するが、S_v >= 2 だと o_r = 1 の行ごとに
(S_v - 1) だけ報酬が出る（S_v = 0 は罰が増えるだけで無害）。これを打ち消す
ため、v の制約A の重みを P_CUST + P_CONF * K_v に上げる。K_v は
「v を相手にする許可側の行のうち、同時に 1 になりうる数」の上界で、
ONEHOT_BOUND で選ぶ:

  "rows"     許可側の行の総数。既定。厳密に安全（S_v = k のとき罰は元の
             P_CUST*(k-1)^2 以上）だが K_v が 100 前後になり、壁が急峻になる。
  "partners" 許可側の行を持つ相手頂点の数（各相手はほぼ 1 行しか 1 に
             ならないという近似）。使えない: 60 秒・seed 1 で n40w20.001 /
             n100w20.001 とも one-hot を破って報酬を稼ぐ解に落ちた
             （once_constraint 11 / 16、conflict_constr が負、feasible False）。

実測 (60 秒, seed 1, "rows"): n40w20.001 travel 500 (最適, TTS 13.6s,
元 4.4s)、n100w20.001 travel 749 (元 738)。項数は減るが、制約A の壁が
高くなる分だけ探索は遅くなっている。
"""
import os
import sys
import time
from collections import Counter, defaultdict

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
# ↑ src/ を探索パスに入れる (tsptwlib のため)。

import pyqbpp as qbpp

from tsptwlib import (arrival_lower_bounds, colocated_terms,
                      load_instance, make_gap, make_vars,
                      parse_args, print_energy, print_summary,
                      print_time_detail, recover_time_tour, save_plot,
                      schedule_from_starts, solve)

PREFIX = "tsptw_time_occupancy_consb"   # 図のファイル名の先頭
RECOMMENDED_TIME = 60.0
ONEHOT_BOUND = os.environ.get("TSPTW_CONSB_BOUND", "rows")  # rows / partners


def conflict_rows(nodes, gap, o, src_lo, olo, svc, ohi):
    """制約B を行ごとに禁止側／許可側の少ない方で書いた式と、その内訳を返す。

    返り値: (expr, n_quad, n_comp, K)
      n_quad ... 二次項の数
      n_comp ... 許可側で書いた行の数
      K      ... K[v] = v を相手にする許可側の行（ONEHOT_BOUND に応じた数え方）
    src_lo は time_occupancy.py の --slim と同じく、発側として禁止を課す下端。
    """
    def g(a, b):
        d = gap(a, b)
        return None if d is qbpp.inf else d

    def forbidden(t, u, tp, v):
        d = g(u, v)
        if t >= src_lo[u] and tp >= t and (d is None or tp < t + d):
            return True
        d = g(v, u)
        return tp >= src_lo[v] and t >= tp and (d is None or t < tp + d)

    def split(t, u, v, lo, hi):
        F, C = [], []
        for tp in range(lo, hi + 1):
            (F if forbidden(t, u, tp, v) else C).append(tp)
        return F, C

    expr = qbpp.expr()
    n_quad = n_comp = 0
    rows = Counter()
    partners = defaultdict(set)

    def emit(t, u, v, F, C, complement):
        nonlocal n_quad, n_comp, expr
        if complement:
            s = qbpp.expr()
            for tp in C:
                s += o[tp, v]
            expr += o[t, u] * (1 - s)
            n_quad += len(C)
            n_comp += 1
            rows[v] += 1
            partners[v].add(u)
        else:
            for tp in F:
                expr += o[t, u] * o[tp, v]
            n_quad += len(F)

    for i, u in enumerate(nodes):
        for v in nodes[i + 1:]:
            # 待機×待機: 禁止側だけ
            for t in range(olo[u], svc[u]):
                F, _ = split(t, u, v, olo[v], svc[v] - 1)
                emit(t, u, v, F, None, False)
            # 待機×サービス: 待機スロットを行にする
            for a, b in ((u, v), (v, u)):
                for t in range(olo[a], svc[a]):
                    F, C = split(t, a, b, svc[b], ohi[b])
                    emit(t, a, b, F, C, len(C) < len(F))
            # サービス×サービス: 行にする側をブロックごとに選ぶ
            best = None
            for a, b in ((u, v), (v, u)):
                rs = [(t,) + split(t, a, b, svc[b], ohi[b])
                      for t in range(svc[a], ohi[a] + 1)]
                cost = sum(min(len(F), len(C)) for _, F, C in rs)
                if best is None or cost < best[0]:
                    best = (cost, a, b, rs)
            _, a, b, rs = best
            for t, F, C in rs:
                emit(t, a, b, F, C, len(C) < len(F))

    if ONEHOT_BOUND == "rows":
        K = rows
    else:
        K = Counter({v: len(us) for v, us in partners.items()})
    return expr, n_quad, n_comp, K


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

    # ---------------- 5. 制約B: 行ごとに禁止側／許可側 ----------------
    # 制約A の重みが K_v に依存するので、先に作る。
    gap = make_gap(inst, s, ret)
    src_lo = svc if opt.slim else olo
    conflict_constraint, n_terms, n_comp, K = conflict_rows(
        nodes, gap, o, src_lo, olo, svc, ohi)
    print(f"conflict terms = {n_terms}  (許可側の行 {n_comp}, "
          f"max K_v = {max(K.values(), default=0)} [{ONEHOT_BOUND}])"
          f"{'  (slim)' if opt.slim else ''}")

    colocated_constraint, n_col = colocated_terms(inst, cust, o, olo, svc, ohi)
    print(f"colocated terms = {n_col}")

    # ---------------- 4. 制約A: 重みを K_v だけ上げる ----------------
    maxc = max(max(row) for row in c)
    P_RET = depot_l + 1
    P_CUST = 4 * maxc + 1
    P_CONF = 2 * maxc + 1
    P_CONT = 2 * maxc + 1
    once_constraint = qbpp.expr()      # 表示用（重みなし）
    once_pen = qbpp.expr()             # 重み付き
    for v in nodes:
        body = qbpp.sum(o[t, v] for t in range(svc[v], ohi[v] + 1)) == 1
        once_constraint += (qbpp.sum(o[t, v]
                                     for t in range(svc[v], ohi[v] + 1)) == 1)
        base = P_RET if v == ret else P_CUST
        once_pen += (base + P_CONF * K[v]) * qbpp.cons(body)

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
    f = (objective
         + once_pen
         + P_CONF * qbpp.cons(conflict_constraint)
         + P_CONF * qbpp.cons(colocated_constraint)
         + P_CONT * qbpp.cons(contiguity_constraint))
    print(f"penalty: RET={P_RET} CUST={P_CUST}+{P_CONF}*K_v "
          f"CONF={P_CONF} CONT={P_CONT}")

    f, sol, val = solve(f, None, opt, build_sec=time.perf_counter() - t_build)
    if sol is None:                             # --build-only
        return

    # conflict_constr は one-hot が破れていると負になりうる（docstring）
    print_energy(f, val, opt,
                 objective=objective,
                 makespan=makespan,
                 total_wait=total_wait,
                 once_constraint=once_constraint,
                 conflict_constr=conflict_constraint,
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
