"""解の復元・検証・表示・描画 —— 全定式化で同じ書式にする。

QUBO のエネルギーを信用せず、復元したツアーを最早開始スケジュールで
直接シミュレートして移動時間と時間枠違反を数える。ペナルティの重みづけを
誤っても結果の良し悪しを見誤らないための独立した検算になる。
"""
from dataclasses import dataclass
from datetime import datetime

from .plot import plot_tour, recover_coordinates


@dataclass
class Schedule:
    """ツアーを時刻に落とした結果 (すべて頂点番号でインデックス)。"""
    arrival: list               # 到着時刻。未訪問頂点は L[v]+1 (描画で赤になる)
    wait: list                  # 待ち時間
    start: list                 # サービス開始時刻。未訪問は None
    travel: int                 # 総移動時間
    ret: int                    # depot 帰着時刻


def simulate(inst, tour, a0=None):
    """最早開始スケジュールで到着 / 待ち / 開始時刻を計算する。

    未訪問頂点の arrival は L[v]+1 にしておき、plot_tour 側で違反 (赤) として
    描かれるようにする。
    """
    c, E, L, N = inst.c, inst.E, inst.L, inst.N
    if a0 is None:
        a0 = E[0]

    arrival = [L[v] + 1 for v in range(N)]
    wait = [0] * N
    start = [None] * N
    travel = 0
    now, prev = a0, 0
    for u in tour[1:-1]:
        arrive = now + c[prev][u]
        begin = max(arrive, E[u])
        arrival[u] = arrive
        wait[u] = begin - arrive
        start[u] = begin
        travel += c[prev][u]
        now, prev = begin, u
    travel += c[prev][0]
    ret = now + c[prev][0]
    arrival[0] = ret                # depot は帰着時刻を表示する
    return Schedule(arrival=arrival, wait=wait, start=start,
                    travel=travel, ret=ret)


def schedule_from_starts(inst, seq, s=None, a0=0):
    """時間展開型用。ソルバが選んだ開始時刻 t をそのまま使って時刻を埋める。

    seq : [(t, v), ...] を時刻順に並べたもの
    s   : 各頂点のサービス時間 (None なら 0)
    """
    c, L, N = inst.c, inst.L, inst.N
    if s is None:
        s = [0] * (N + 1)

    arrival = [L[v] + 1 for v in range(N)]
    wait = [0] * N
    start = [None] * N
    travel = 0
    now, prev = a0, 0
    for t, v in seq:
        arrive = now + c[prev][v]
        arrival[v] = arrive
        wait[v] = t - arrive
        start[v] = t
        travel += c[prev][v]
        now, prev = t + s[v], v
    travel += c[prev][0]
    ret = now + c[prev][0]
    arrival[0] = ret
    return Schedule(arrival=arrival, wait=wait, start=start,
                    travel=travel, ret=ret)


# --------------------------------------------------------------------------
# ツアーの復元
# --------------------------------------------------------------------------
def recover_order_tour(inst, x, val, allowed=None):
    """順序型: x[i][u] からツアーを復元する。

    位置ごとの選択結果 picked[i] をそのまま保持するので、one-hot が壊れて
    「訪問のない位置」があってもインデックスがずれない。
    """
    N = inst.N
    picked = []
    for i in range(N):
        targets = range(1, N) if allowed is None else allowed[i]
        if i == 0:
            picked.append([0])
            continue
        picked.append([u for u in targets if val(x[i][u]) == 1])

    tour = [0]
    for i in range(1, N):
        if len(picked[i]) == 1:
            tour.append(picked[i][0])
    tour.append(0)
    return tour, picked


def order_ties(inst, seq):
    """同時刻に開始した頂点の並びを、総移動時間が最小になるように決める。

    seq は [(t, v), ...] の時刻順。同一地点ペア (c = 0) は gap が 0 なので
    同じ t に開始しうるが、Dumas では c = 0 でも他の点への距離が 1 ほど違う
    ことが多く、頂点番号で並べると travel が 1 ずれる。同時刻のまとまりごとに
    順列を試し、前後のまとまりとのつながりまで含めて DP で最小化する
    （まとまりはせいぜい数頂点なので順列で足りる）。
    時刻が 1 つずつ違うなら何もしない。
    """
    from itertools import groupby, permutations
    c = inst.c
    groups = [[v for _, v in g] for _, g in groupby(seq, key=lambda p: p[0])]
    if all(len(g) == 1 for g in groups):
        return list(seq)
    times = [t for t, _ in groupby(seq, key=lambda p: p[0])]

    # dp[last] = (コスト, それまでの並び)。last は直前のまとまりの最後の頂点
    dp = {0: (0, [])}
    for g in groups:
        nxt = {}
        for perm in permutations(g):
            inner = sum(c[a][b] for a, b in zip(perm, perm[1:]))
            for last, (cost, path) in dp.items():
                cand = cost + c[last][perm[0]] + inner
                if perm[-1] not in nxt or cand < nxt[perm[-1]][0]:
                    nxt[perm[-1]] = (cand, path + [list(perm)])
        dp = nxt
    best_path = min(dp.items(), key=lambda kv: kv[1][0] + c[kv[0]][0])[1][1]
    return [(t, v) for t, g in zip(times, best_path) for v in g]


def recover_time_tour(inst, x, val, nodes, lo, hi, ret_node):
    """時間展開型: x[t][v] からツアーを復元する。

    返り値は (tour, seq, start_t)。seq は [(t, v), ...] の時刻順。
    """
    start_t = {}
    for v in nodes:
        ts = [t for t in range(lo[v], hi[v] + 1) if val(x[t, v]) == 1]
        if len(ts) != 1:
            print(f"node {v}: {len(ts)} visits VIOLATION!")
        if ts:
            start_t[v] = ts[0]

    # 同一地点 (c[u][v] == 0) のペアは gap が 0 なので同時刻に来うる。
    # 他の点への距離は同じとは限らないので、並びは order_ties() で決める。
    seq = order_ties(inst, sorted((t, v) for v, t in start_t.items()
                                  if v != ret_node))
    tour = [0] + [v for _, v in seq] + [0]
    return tour, seq, start_t


# --------------------------------------------------------------------------
# 表示
# --------------------------------------------------------------------------
def print_energy(f, val, opt, **constraints):
    """エネルギーと制約の値。キーワード引数の名前がそのまま行の見出しになる。"""
    print(f"\n----------result({opt.time_limit} sec)----------")
    print("energy          =", val(f))
    for name, expr in constraints.items():
        print(f"{name:15s} =", val(expr))
    print("violated cons   =", f.cons(val))


def print_order_detail(inst, picked, sched, val=None, a=None, w=None,
                       quiet=False):
    """位置ごとの 1 行明細 (順序型)。

    a, w を渡すとソルバが持っている整数変数の値も並べて出すので、
    モデル内部の時刻と最早開始スケジュールのずれが見える。
    """
    if quiet:
        return
    E, L, N = inst.E, inst.L, inst.N
    for i in range(1, N):
        if len(picked[i]) != 1:
            print(f"pos{i:3d}: {picked[i]} VIOLATION! (one-hot)")
            continue
        u = picked[i][0]
        begin = sched.start[u]
        flag = "" if begin is not None and E[u] <= begin <= L[u] \
            else " VIOLATION!"
        extra = ""
        if a is not None and val is not None:
            extra += f" solver_start={val(a[i]):5d}"
        if w is not None and val is not None:
            extra += f" solver_wait={val(w[i]):5d}"
        print(f"pos{i:3d}: u={u:3d}{extra} "
              f"arrive={sched.arrival[u]:5d} wait={sched.wait[u]:5d} "
              f"start={begin if begin is not None else '-':>5} "
              f"[{E[u]:5d}, {L[u]:5d}]{flag}")


def print_time_detail(inst, seq, sched, quiet=False):
    """頂点ごとの 1 行明細 (時間展開型)。"""
    if quiet:
        return
    E, L = inst.E, inst.L
    for t, v in seq:
        arrive = sched.arrival[v]
        flag = "" if (E[v] <= t <= L[v] and t >= arrive) else "  VIOLATION!"
        print(f"  v={v:3d} start={t:4d} arrive={arrive:4d} "
              f"wait={t - arrive:4d} [{E[v]:4d},{L[v]:4d}]{flag}")


def verify_tour(inst, tour):
    """ツアーそのものの実行可能性と値を、最早開始スケジュールで検算する。

    ソルバの時刻は使わない。時間展開型でも順序型でも同じ基準で判定するための
    独立した検算で、runs.csv の feasible / travel time / return はこれに拠る。
    返り値は dict: visited, dup, travel, ret, tw_violations, feasible, sched。
    """
    L, N = inst.L, inst.N
    visited = tour[1:-1]
    dup = len(visited) != len(set(visited))
    chk = simulate(inst, tour)
    # 最早開始なので start >= max(到着, E) は常に成り立つ。破れうるのは L 側だけ
    tw_violations = sum(1 for u in visited if chk.start[u] > L[u])
    feasible = (not dup and len(set(visited)) == N - 1
                and tw_violations == 0 and chk.ret <= L[0])
    return {"visited": len(set(visited)), "dup": dup, "travel": chk.travel,
            "ret": chk.ret, "tw_violations": tw_violations,
            "feasible": feasible, "sched": chk}


def print_summary(inst, tour, sched, sol):
    """ツアーの要約。全定式化で同じ書式にしてあるので結果を並べて比べられる。

    feasible / travel time / return は verify_tour() の検算値（ツアーを最早開始で
    辿り直したもの）。sched はモデル側の時刻で、検算とは独立に
    「ソルバの時刻が物理的に辻褄が合っているか」だけを別の行で報告する。
    時間展開型は schedule_from_starts() がソルバの開始時刻をそのまま使うので、
    衝突制約が破れると到着前にサービスを始める頂点が出る（順序型は常に 0）。
    """
    N, L = inst.N, inst.L
    chk = verify_tour(inst, tour)
    visited = tour[1:-1]
    early = sum(1 for u in visited
                if sched.start[u] is not None
                and sched.start[u] < sched.arrival[u])
    late = sum(1 for u in visited
               if sched.start[u] is None or sched.start[u] > L[u]
               or sched.start[u] < inst.E[u])

    print("tour        =", tour)
    print(f"visited     = {chk['visited']}/{N - 1}"
          f"{'  (重複あり)' if chk['dup'] else ''}")
    print("travel time =", chk["travel"])
    print(f"return      = {chk['ret']} (limit {L[0]}, 最早開始)"
          f"{'  VIOLATION!' if chk['ret'] > L[0] else ''}")
    print("tw violations =", chk["tw_violations"])
    print("feasible    =", chk["feasible"])
    ok = early == 0 and late == 0 and sched.ret <= L[0]
    print(f"model times = {'ok' if ok else 'INCONSISTENT'} "
          f"(ソルバの時刻: 到着前の開始 {early} / 時間枠外 {late} / "
          f"帰着 {sched.ret})")
    if sol is not None:
        print("var_count   =", sol.info["var_count"])
        print("term_count  =", sol.info["term_count"])
    return chk["feasible"]


# --------------------------------------------------------------------------
# 描画
# --------------------------------------------------------------------------
def save_plot(inst, tour, sched, prefix, opt):
    """results/<prefix>_<インスタンス>_<時刻>.png に保存する。

    plot_tour() 側で results/tsptw.png (最新結果のコピー) にも書かれる。
    """
    if not opt.plot:
        return None
    if inst.N > opt.plot_max_n:
        print(f"skip plot   = N={inst.N} > plot_max_n={opt.plot_max_n} "
              "(recover_coordinates が重いため)")
        return None

    filename = f"{prefix}_{inst.name}_{datetime.now():%m%d%H%M}"
    nodes = recover_coordinates(inst.c)
    plot_tour(nodes, tour, inst.E, sched.wait, sched.arrival,
              inst.L, inst.c, filename)
    print("saved       =", f"results/{filename}.png")
    return filename
