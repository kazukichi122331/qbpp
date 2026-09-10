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

    seq = sorted((t, v) for v, t in start_t.items() if v != ret_node)
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


def print_summary(inst, tour, sched, sol):
    """ツアーの要約。全定式化で同じ書式にしてあるので結果を並べて比べられる。"""
    L, N = inst.L, inst.N
    visited = tour[1:-1]
    dup = len(visited) != len(set(visited))
    tw_violations = sum(1 for u in visited
                        if sched.start[u] is None or sched.start[u] > L[u]
                        or sched.start[u] < inst.E[u])
    feasible = (not dup and len(set(visited)) == N - 1
                and tw_violations == 0 and sched.ret <= L[0])

    print("tour        =", tour)
    print(f"visited     = {len(set(visited))}/{N - 1}"
          f"{'  (重複あり)' if dup else ''}")
    print("travel time =", sched.travel)
    print(f"return      = {sched.ret} (limit {L[0]})"
          f"{'  VIOLATION!' if sched.ret > L[0] else ''}")
    print("tw violations =", tw_violations)
    print("feasible    =", feasible)
    if sol is not None:
        print("var_count   =", sol.info["var_count"])
        print("term_count  =", sol.info["term_count"])
    return feasible


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
