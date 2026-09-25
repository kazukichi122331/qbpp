"""アーク型 (後続型) TSPTW QUBO —— 「誰の次に誰へ行くか」と「各顧客の時刻」を持つ。

変数
    x[u][v] = 1  <=>  u の直後に v へ移動する (アーク u -> v を使う)
                      u, v = 0..N-1 (0 は depot)。枝刈りで不可能なアークは作らない
    a[u]         =    顧客 u のサービス開始時刻 (整数変数, 2 進符号化)
                      定義域は [lo[u], hi[u]] ⊂ [E[u], L[u]]

order_* (x[i][u]: 位置 i に誰) とも time_* (x[t][u]: 時刻 t に誰) とも違い、
添字に「位置」も「時刻」も持たない。位置は後続リンクをたどれば決まり、時刻は
各顧客に 1 個だけの整数で持つ。MILP で言えば MTZ 型の 2 添字 (two-index)
定式化 (Desrochers & Laporte 1991, Ascheuer et al. 2001) の QUBO 版である。

制約
    (D-out) 各点からちょうど 1 本出る        Σ_v x[u][v] == 1     (u = 0..N-1)
    (D-in)  各点へちょうど 1 本入る          Σ_u x[u][v] == 1     (v = 0..N-1)
    (T)     使うアークでは時刻が進む         x[u][v] = 1 => a[v] >= a[u] + c[u][v]
            QUBO では big-M で 1 本の不等式にする:
                a[v] - a[u] - c[u][v] + M[u][v] (1 - x[u][v]) >= 0
                M[u][v] = hi[u] + c[u][v] - lo[v]   (定義域から決まる最小の M)
            x = 0 のとき左辺は (a[v] - lo[v]) + (hi[u] - a[u]) >= 0 で自動的に成立。
            x = 1 のとき違反量はちょうど max(0, a[u] + c[u][v] - a[v])。
            M を定義域から最小に取っているので「M が大きすぎて罰が鈍る」ことがない。
    (Z)     距離 0 の閉路を禁止                x[u][v] x[v][u] (と 3 点の閉路)
    時間枠  E[u] <= a[u] <= L[u]          -> 変数の定義域そのもの。制約は要らない
    depot   0 -> v では a[v] >= c[0][v]、u -> 0 では a[u] + c[u][0] <= L[0]
            -> どちらも定義域 lo / hi に織り込み済み。制約は要らない

部分巡回 (subtour) は (T) が消す。depot を含まない閉路 C では (T) を一周足すと
0 >= Σ_{C} c となり、Σ_C c > 0 なら必ずどこかが破れる (MTZ と同じ理屈)。
Σ_C c = 0 になるのは距離 0 の点だけでできた閉路で、Dumas には大きさ 2 の
同一地点グループが 201 個、大きさ 3 が 4 個ある (138 ファイル中 75 ファイル)。
これは (Z) で直接罰する (2 点なら 2 次、3 点なら 3 次の項)。

目的
    総移動時間 = Σ_{u,v} c[u][v] x[u][v]            <- 1 次式

宣言制約 qbpp.cons(body, between=(0, None)) はスラック変数を作らず、ソルバが
weight * max(0, -body)^2 を直接評価する。したがって (T) はアーク 1 本あたり
「a[u] と a[v] のビット + x 1 個」だけの本体で済み、補助変数は a[] だけになる。

既存の 2 系統との比較
    - order_*: x[i][u] は N^2 個。時間枠が広いと位置 i に置ける顧客が絞れない。
               leg[i] が x の 2 次式なので目的関数・時刻制約が高次になる。
    - time_*:  x[t][u] は Σ(時間枠の幅) 個。時間枠が広いと変数も衝突項も急増する。
               全ペアに衝突項を課すので三角不等式が破れる Dumas では厳密でない。
    - arc:     x[u][v] は「時間的に隣り合える組」の数だけ。時刻は 2 進なので
               時間枠の幅には対数でしか効かない。隣接ペアにしか時刻制約を
               課さないので、三角不等式の破れの影響を受けない (厳密な TSPTW)。

枝刈り (すべて健全: 実行可能解を落とさない)
    d = c の最短路距離 (三角不等式が破れていても推論が健全になるよう使う)。
    lo[u] = max(E[u], d[0][u]),  hi[u] = min(L[u], L[0] - d[u][0]) から始めて
    以下を不動点まで繰り返す。
      - アーク u -> v は lo[u] + c[u][v] > hi[v] なら不可能
      - u ≺ w (u は必ず w より前) : lo[w] + d[w][u] > hi[u]
      - u ≺ w ≺ v なる w があればアーク u -> v は不可能 (間に w が要る)
        0 -> v は w ≺ v があれば不可能、u -> 0 は u ≺ w があれば不可能
      - lo[v] >= min_{u -> v 可能} (lo[u] + c[u][v]),  lo[v] >= lo[u] + d[u][v] (u ≺ v)
      - hi[u] <= max_{u -> v 可能} (hi[v] - c[u][v]),  hi[u] <= hi[w] - d[u][w] (u ≺ w)
"""
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
# ↑ src/ を探索パスに入れる。python src/x.py でも python -m src.x でも動く。

import pyqbpp as qbpp

from tsptwlib import (load_instance, parse_args, print_energy,
                      print_summary, save_plot, simulate, solve)

PREFIX = "tsptw_arc_time"               # 図のファイル名の先頭


# --------------------------------------------------------------------------
# 前処理: 最短路・時刻の定義域・アークの枝刈り
# --------------------------------------------------------------------------
def shortest_paths(c):
    """Floyd–Warshall。枝刈りの推論 (直行とは限らない前後関係) にだけ使う。"""
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


def prune_arcs(inst):
    """(lo, hi, arcs, n_iter) を返す。arcs は可能なアーク (u, v) の集合。"""
    N, c, E, L = inst.N, inst.c, inst.E, inst.L
    d = shortest_paths(c)
    cust = range(1, N)

    lo = [E[0]] + [max(E[u], d[0][u]) for u in cust]
    hi = [E[0]] + [min(L[u], L[0] - d[u][0]) for u in cust]
    # depot は出発 (時刻 E[0]) と帰着 (期限 L[0]) で役割が違うので別に持つ
    dep_lo, ret_hi = E[0], L[0]

    arcs = {(0, v) for v in cust} | {(u, 0) for u in cust}
    arcs |= {(u, v) for u in cust for v in cust if u != v}

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
            dead = False
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
            return lo, hi, arcs, it
    return lo, hi, arcs, it


def zero_cycles(inst, arcs):
    """距離 0 のアークだけでできる長さ 2 / 3 の閉路 (顧客のみ)。"""
    N, c = inst.N, inst.c
    zero = {(u, v) for (u, v) in arcs if u and v and c[u][v] == 0}
    cyc2 = [(u, v) for (u, v) in zero if u < v and (v, u) in zero]
    cyc3 = []
    for (u, v) in zero:
        for w in range(1, N):
            # 3 点閉路 u -> v -> w -> u を最小頂点始まりで 1 回ずつ数える
            if u < v and u < w and w != v \
                    and (v, w) in zero and (w, u) in zero:
                cyc3.append((u, v, w))
    return cyc2, cyc3


# --------------------------------------------------------------------------
# 解の復元
# --------------------------------------------------------------------------
def recover_arc_tour(inst, x, val):
    """depot から後続リンクをたどってツアーを作る。

    出次数が 2 以上なら最初の未訪問を選び、途切れたらそこで depot に戻す。
    たどれなかった顧客 (部分巡回に入っている等) は tour に現れないので、
    print_summary() の visited で見える。
    """
    N = inst.N
    succ = {u: [] for u in range(N)}
    for (u, v), var in x.items():
        if val(var) == 1:
            succ[u].append(v)
    bad = [u for u in range(N) if len(succ[u]) != 1]
    tour, seen, cur = [0], {0}, 0
    while True:
        nxt = [v for v in succ[cur] if v not in seen]
        if not nxt:
            break
        cur = nxt[0]
        tour.append(cur)
        seen.add(cur)
    tour.append(0)
    return tour, succ, bad


def print_arc_detail(inst, tour, sched, val, a, quiet=False):
    if quiet:
        return
    E, L = inst.E, inst.L
    for k, u in enumerate(tour[1:-1], start=1):
        begin = sched.start[u]
        flag = "" if E[u] <= begin <= L[u] else " VIOLATION!"
        print(f"pos{k:3d}: u={u:3d} solver_start={val(a[u]):5d} "
              f"arrive={sched.arrival[u]:5d} wait={sched.wait[u]:5d} "
              f"start={begin:5d} [{E[u]:5d}, {L[u]:5d}]{flag}")


# --------------------------------------------------------------------------
def main(opt):
    inst = load_instance(opt.instance)
    N, c, L = inst.N, inst.c, inst.L
    print(inst.summary())
    cust = list(range(1, N))

    t_build = time.perf_counter()

    # ---- 1. 前処理 --------------------------------------------------------
    lo, hi, arcs, n_iter = prune_arcs(inst)
    bad = [u for u in cust if lo[u] > hi[u]]
    if bad:
        print(f"WARNING: 定義域が空の顧客 (実行不可能なインスタンス): {bad}")
    no_in = [v for v in range(N) if not any((u, v) in arcs for u in range(N))]
    no_out = [u for u in range(N) if not any((u, v) in arcs for v in range(N))]
    if no_in or no_out:
        print(f"WARNING: 入るアークが無い点={no_in} 出るアークが無い点={no_out}")
    full = N * (N - 1)
    width = sum(hi[u] - lo[u] for u in cust)
    print(f"arcs = {full} -> {len(arcs)} (枝刈り {n_iter} 回)  "
          f"平均出次数 {len(arcs) / N:.1f}  a の定義域幅 平均 "
          f"{width / max(1, N - 1):.1f}")

    # ---- 2. 変数 ----------------------------------------------------------
    x = {(u, v): qbpp.var(f"x_{u}_{v}") for (u, v) in sorted(arcs)}
    native = os.environ.get("ARC_ENC", "bin") == "int"
    a = [qbpp.expr() + lo[0]]
    for u in cust:
        if lo[u] >= hi[u]:
            a.append(qbpp.expr() + lo[u])           # 幅 0 は定数に潰す
        elif native:
            a.append(qbpp.expr() + qbpp.var(f"a{u}", integer=(lo[u], hi[u])))
        else:
            a.append(qbpp.var(f"a{u}", between=(lo[u], hi[u])))

    # ---- 3. 次数制約 (出 1 本・入 1 本) -----------------------------------
    out_sum = {u: qbpp.expr() for u in range(N)}
    in_sum = {v: qbpp.expr() for v in range(N)}
    for (u, v), var in x.items():
        out_sum[u] += var
        in_sum[v] += var
    out_constraint = qbpp.expr()
    in_constraint = qbpp.expr()
    for u in range(N):
        out_constraint += qbpp.cons(out_sum[u], equal=1)
        in_constraint += qbpp.cons(in_sum[u], equal=1)

    # ---- 4. 時刻の連結 (big-M, アーク 1 本に不等式 1 本) -------------------
    time_constraint = qbpp.expr()
    n_link = 0
    for (u, v), var in x.items():
        if u == 0 or v == 0:
            continue                    # 定義域 lo / hi に織り込み済み
        M = hi[u] + c[u][v] - lo[v]
        if M <= 0:
            continue                    # どの値でも成立する
        time_constraint += qbpp.cons(qbpp.expr() + a[v] - a[u] - c[u][v] + M * (1 - var),
                                     between=(0, None))
        n_link += 1

    # ---- 5. 距離 0 の閉路 --------------------------------------------------
    cyc2, cyc3 = zero_cycles(inst, arcs)
    cycle_penalty = qbpp.expr()
    for (u, v) in cyc2:
        cycle_penalty += x[u, v] * x[v, u]
    for (u, v, w) in cyc3:
        cycle_penalty += x[u, v] * x[v, w] * x[w, u]
    print(f"time links = {n_link}  zero cycles = {len(cyc2)} (2点) "
          f"+ {len(cyc3)} (3点)")

    # ---- 6. 目的関数 ------------------------------------------------------
    objective = qbpp.expr()
    for (u, v), var in x.items():
        if c[u][v]:
            objective += c[u][v] * var

    # ---- 7. ペナルティ係数 ------------------------------------------------
    # 次数 1 本の違反で節約できる移動時間は高々 max c 程度 (顧客 v を飛ばすと
    # v の出入り 2 本が同時に破れ、節約は c[u][v] + c[v][w] - c[u][w] <= 2 max c)。
    # 時刻の違反 δ は weight * δ^2 で効くので、δ = 1 の罰を max c 程度にしておく。
    maxc = max(c[u][v] for (u, v) in arcs) if arcs else 1
    P_DEG = int(os.environ.get("ARC_P_DEG", 2 * maxc + 1))
    P_TIME = int(os.environ.get("ARC_P_TIME", 2 * maxc + 1))
    P_CYC = 2 * maxc + 1
    f = (qbpp.expr() + objective
         + P_DEG * out_constraint
         + P_DEG * in_constraint
         + P_TIME * time_constraint)
    if cyc2 or cyc3:
        f += P_CYC * qbpp.cons(cycle_penalty)
    print(f"penalty: DEG={P_DEG} TIME={P_TIME} CYC={P_CYC}")

    f, sol, val = solve(f, None, opt, build_sec=time.perf_counter() - t_build)
    if sol is None:                     # --build-only
        return

    print_energy(f, val, opt,
                 objective=objective,
                 out_constraint=out_constraint,
                 in_constraint=in_constraint,
                 time_constraint=time_constraint,
                 cycle_penalty=cycle_penalty)

    # ---- 8. 復元と検証 ----------------------------------------------------
    tour, succ, bad = recover_arc_tour(inst, x, val)
    if bad:
        print(f"出次数 != 1 の点: {bad}")
    sched = simulate(inst, tour)
    print_arc_detail(inst, tour, sched, val, a, quiet=opt.quiet)
    print_summary(inst, tour, sched, sol)
    save_plot(inst, tour, sched, PREFIX, opt)


if __name__ == "__main__":
    main(parse_args())
