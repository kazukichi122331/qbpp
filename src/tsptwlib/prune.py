"""時刻の定義域とアーク・前後関係の枝刈り (顧客ごとの時刻を持つ定式化用)。

prec_disjunctive.py のように「顧客 u のサービス開始時刻」を 1 個の整数で持つ
定式化は、定義域 [lo[u], hi[u]] が狭いほどビットが減り、前後関係が決まる組が
多いほど 2 値変数が減る。ここではその両方を不動点反復で締める。

すべて健全 (実行可能解を落とさない)。Dumas の既知最適ツアー 135 件で、
ツアーのアークがすべて残り、最早開始時刻がすべて定義域に入ることを確認済み。
"""


def shortest_paths(c):
    """Floyd–Warshall。

    Dumas の距離行列は三角不等式を破っているので、「u の後いつか v」という
    直行とは限らない前後関係の推論には c ではなく最短路 d を使う
    (c を使うと、寄り道の方が近い組で健全性が崩れる)。
    """
    N = len(c)
    d = [row[:] for row in c]
    for k in range(N):
        dk = d[k]
        for i in range(N):
            dik = d[i][k]
            di = d[i]
            for j in range(N):
                if dik + dk[j] < di[j]:
                    di[j] = dik + dk[j]
    return d


def precedence(inst, lo, hi, d):
    """must[u, v] = True <=> u は必ず v より前 (v を u より前に置くと間に合わない)。"""
    cust = range(1, inst.N)
    return {(u, v): lo[v] + d[v][u] > hi[u]
            for u in cust for v in cust if u != v}


def prune_time_windows(inst):
    """(lo, hi, arcs, n_iter) を返す。

    lo[u], hi[u] : 顧客 u のサービス開始時刻の下限 / 上限 (lo[0] = hi[0] = E[0])
    arcs         : 直行可能なアーク (u, v) の集合 (0 は depot)

    lo[u] = max(E[u], d[0][u]),  hi[u] = min(L[u], L[0] - d[u][0]) から始めて、
    以下を不動点まで繰り返す。
      - アーク u -> v は lo[u] + c[u][v] > hi[v] なら不可能
      - u ≺ w (u は必ず w より前) : lo[w] + d[w][u] > hi[u]
      - u ≺ w ≺ v なる w があればアーク u -> v は不可能 (間に w が要る)
        0 -> v は w ≺ v があれば、u -> 0 は u ≺ w があれば不可能
      - lo[v] >= min_{u -> v 可能} (lo[u] + c[u][v]),  lo[v] >= lo[u] + d[u][v] (u ≺ v)
      - hi[u] <= max_{u -> v 可能} (hi[v] - c[u][v]),  hi[u] <= hi[w] - d[u][w] (u ≺ w)
    """
    N, c, E, L = inst.N, inst.c, inst.E, inst.L
    d = shortest_paths(c)
    cust = range(1, N)

    lo = [E[0]] + [max(E[u], d[0][u]) for u in cust]
    hi = [E[0]] + [min(L[u], L[0] - d[u][0]) for u in cust]
    # depot は出発 (時刻 E[0]) と帰着 (期限 L[0]) で役割が違うので別に持つ
    dep_lo, ret_hi = E[0], L[0]

    arcs = {(0, v) for v in cust} | {(u, 0) for u in cust}
    arcs |= {(u, v) for u in cust for v in cust if u != v}

    it = 0
    for it in range(1, 10 * N + 1):
        changed = False

        # 前後関係 u ≺ w をビット集合で持つ (u の後に必ず来る集合 / 前に必ず来る集合)
        after = [0] * N
        before = [0] * N
        for u in cust:
            for w in cust:
                if u != w and lo[w] + d[w][u] > hi[u]:
                    after[u] |= 1 << w
                    before[w] |= 1 << u

        # アークの削除
        for (u, v) in list(arcs):
            if u == 0:
                dead = before[v] != 0
            elif v == 0:
                dead = after[u] != 0
            else:
                dead = (lo[u] + c[u][v] > hi[v]) or (after[u] & before[v])
            if dead:
                arcs.discard((u, v))
                changed = True

        # 定義域の締め付け
        preds = {v: [] for v in range(N)}
        succs = {u: [] for u in range(N)}
        for (u, v) in arcs:
            preds[v].append(u)
            succs[u].append(v)
        for v in cust:
            new_lo = lo[v]
            if preds[v]:
                new_lo = max(new_lo, min((dep_lo if u == 0 else lo[u]) + c[u][v]
                                         for u in preds[v]))
            for u in cust:
                if before[v] >> u & 1:
                    new_lo = max(new_lo, lo[u] + d[u][v])
            new_hi = hi[v]
            if succs[v]:
                new_hi = min(new_hi, max((ret_hi if w == 0 else hi[w]) - c[v][w]
                                         for w in succs[v]))
            for w in cust:
                if after[v] >> w & 1:
                    new_hi = min(new_hi, hi[w] - d[v][w])
            if new_lo != lo[v] or new_hi != hi[v]:
                lo[v], hi[v] = new_lo, new_hi
                changed = True
        if not changed:
            break
    return lo, hi, arcs, it
