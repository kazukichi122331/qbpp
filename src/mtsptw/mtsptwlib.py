"""mtsptwlib —— mTSPTW の時間展開型 QUBO で共通に使う部品。

頂点の番号づけ
--------------
    0        出発デポ
    1..N     顧客 (N = 顧客数)
    N+1      帰着デポ

Dumas 形式のファイルは depot を 1 つ (0) しか持たないので、読み込むときに
0 の行・列・時間枠を複製して N+1 を足す (c[i][N+1] = c[i][0],
E[N+1] = E[0], L[N+1] = L[0])。こうすると帰着は「N+1 という頂点への訪問」に
なり、gap も移動時間も顧客と同じ式で書ける。以前の版は帰着を仮想ノード RET と
して持ち、c[i][0] で読み替えていた。

tsptwlib の Instance は N を「depot を含む点数」(顧客 1..N-1) として扱うので、
ここでは別の MInstance を使う。tsptwlib の関数のうち c / E / L を頂点番号で
引くだけのもの (conflict_terms, colocated_terms, order_ties, print_time_detail)
はそのまま使える。N や depot 0 への帰着を前提にするもの (simulate,
schedule_from_starts, save_plot) はここで置き換える。
"""
import os
import sys
from dataclasses import dataclass, field

import pyqbpp as qbpp

from tsptwlib import (Schedule, load_instance, order_ties, save_plot,
                      schedule_from_starts as _schedule_from_starts_single)

DEFAULT_VEHICLES = 2


# --------------------------------------------------------------------------
# インスタンス
# --------------------------------------------------------------------------
@dataclass(frozen=True)
class MInstance:
    """デポを 0 と N+1 に分けた mTSPTW インスタンス。

    N : 顧客数。顧客は 1..N、出発デポ 0、帰着デポ N+1。
    c : 移動時間の行列 ((N+2) x (N+2))
    E : 各点の時間枠の開始時刻 (長さ N+2)
    L : 各点の時間枠の終了時刻 (長さ N+2)。L[N+1] は帰着期限。
    base : 読み込んだままの tsptwlib.Instance (m = 1 の描画に使う)
    """
    name: str
    path: str
    N: int
    c: list
    E: list
    L: list
    base: object = field(repr=False, compare=False)

    @property
    def customers(self):
        """顧客の番号 1..N。"""
        return list(range(1, self.N + 1))

    @property
    def end(self):
        """帰着デポの番号 N+1。"""
        return self.N + 1

    def summary(self):
        width = sum(self.L[u] - self.E[u] for u in self.customers)
        return (f"instance    = {self.name}  N={self.N} "
                f"(顧客 1..{self.N}, デポ 0 / {self.end})  "
                f"L[{self.end}]={self.L[self.end]}  "
                f"時間枠の平均幅 {width / max(1, self.N):.1f}")


def load_minstance(path):
    """Dumas 形式のファイルを読み、帰着デポ N+1 を足した MInstance を返す。"""
    base = load_instance(path)
    n = base.N - 1                              # 顧客数
    c = [row + [row[0]] for row in base.c]      # 列 N+1 = 列 0
    c.append(c[0][:])                           # 行 N+1 = 行 0
    c[n + 1][n + 1] = 0
    E = base.E + [base.E[0]]
    L = base.L + [base.L[0]]
    return MInstance(name=base.name, path=base.path, N=n, c=c, E=E, L=L,
                     base=base)


def full_route(inst, seq):
    """[(t, i), ...] を 0 と N+1 で挟んだ頂点列にする。"""
    return [0] + [i for _, i in seq] + [inst.end]


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------
def pop_vehicles(argv=None):
    """argv から -m / --vehicles を抜き取って (台数, 残りの argv) を返す。

    tsptwlib.cli は全定式化で共通なので車両数のオプションを持たない。
    共通 CLI に手を入れずに済ませるため、ここで先に取り除く。
    """
    argv = list(sys.argv[1:] if argv is None else argv)
    m = int(os.environ.get("TSPTW_VEHICLES", DEFAULT_VEHICLES))
    rest, i = [], 0
    while i < len(argv):
        a = argv[i]
        if a in ("-m", "--vehicles"):
            if i + 1 >= len(argv):
                sys.exit(f"{a} には台数が要る")
            m, i = int(argv[i + 1]), i + 2
        elif a.startswith("--vehicles="):
            m, i = int(a.split("=", 1)[1]), i + 1
        else:
            rest.append(a)
            i += 1
    if m < 1:
        sys.exit(f"車両数は 1 以上 (指定値 {m})")
    return m, rest


# --------------------------------------------------------------------------
# 変数・gap
# --------------------------------------------------------------------------
def make_gap(inst, s):
    """gap(u, v) = u のサービス開始から v のサービス開始までに必要な最小時間差。

    帰着デポ N+1 の後には何も来ないので gap(N+1, ·) = inf。それ以外は
    顧客も帰着デポも同じ s[u] + c[u][v]。同一地点ペア (c = 0) の扱いは
    tsptwlib.make_gap の docstring と同じ。
    """
    c, end = inst.c, inst.end

    def gap(u, v):
        if u == end:
            return qbpp.inf
        return s[u] + c[u][v]

    return gap


def make_vars_multi(name, lo, hi, nodes, vehicles):
    """tsptwlib.make_vars の (t, v) を (t, v, k) に広げただけ。

    定義域 lo / hi は頂点ごと。車両は同一なので台数で変わらない。
    """
    var = {}
    for k in vehicles:
        for v in nodes:
            for t in range(lo[v], hi[v] + 1):
                var[t, v, k] = qbpp.var(f"{name}_{t}_{v}_{k}")
    return var


def vehicle_view(o, nodes, lo, hi, k):
    """車両 k のぶんだけ抜き出した {(t, v): var}。

    conflict_terms() は単一車両の形 (t, v) を期待するので、車両ごとに
    この view を渡して呼ぶ。こうすると「衝突は同じ車両の中だけ」が
    自然に表現でき、ライブラリ側に手を入れなくて済む。
    """
    return {(t, v): o[t, v, k]
            for v in nodes for t in range(lo[v], hi[v] + 1)}


# --------------------------------------------------------------------------
# スケジュール (tsptwlib.simulate / schedule_from_starts の N+1 版)
# --------------------------------------------------------------------------
def simulate(inst, route, a0=None):
    """route = [0, 顧客..., N+1] を最早開始スケジュールで辿る。

    未訪問頂点の arrival は L[v]+1、start は None (tsptwlib.simulate と同じ)。
    ret は帰着デポ N+1 への到着時刻。
    """
    c, E, L = inst.c, inst.E, inst.L
    n = inst.N + 2
    now = E[0] if a0 is None else a0

    arrival = [L[v] + 1 for v in range(n)]
    wait = [0] * n
    start = [None] * n
    travel = 0
    prev = route[0]
    for u in route[1:-1]:
        arrive = now + c[prev][u]
        begin = max(arrive, E[u])
        arrival[u] = arrive
        wait[u] = begin - arrive
        start[u] = begin
        travel += c[prev][u]
        now, prev = begin, u
    end = route[-1]
    travel += c[prev][end]
    ret = now + c[prev][end]
    arrival[end] = start[end] = ret
    return Schedule(arrival=arrival, wait=wait, start=start,
                    travel=travel, ret=ret)


def schedule_from_starts(inst, seq, s, a0=0):
    """ソルバが選んだ開始時刻 t をそのまま使って時刻を埋める。

    seq : 1 台ぶんの顧客 [(t, v), ...] を時刻順に並べたもの
    """
    c, L, end = inst.c, inst.L, inst.end
    n = inst.N + 2

    arrival = [L[v] + 1 for v in range(n)]
    wait = [0] * n
    start = [None] * n
    travel = 0
    now, prev = a0, 0
    for t, v in seq:
        arrive = now + c[prev][v]
        arrival[v] = arrive
        wait[v] = t - arrive
        start[v] = t
        travel += c[prev][v]
        now, prev = t + s[v], v
    travel += c[prev][end]
    ret = now + c[prev][end]
    arrival[end] = start[end] = ret
    return Schedule(arrival=arrival, wait=wait, start=start,
                    travel=travel, ret=ret)


# --------------------------------------------------------------------------
# 解の復元・要約
# --------------------------------------------------------------------------
def recover_routes(inst, o, val, veh, lo, hi):
    """o[t][i][k] から車両ごとの [(t, i), ...]（時刻順）と帰着時刻を返す。

    lo / hi は顧客のサービス域と帰着デポの定義域。
    顧客の重複訪問・未訪問、帰着デポの 0 回 / 複数回はここで報告する（制約A の検算）。
    """
    cust, end = inst.customers, inst.end
    routes = {k: [] for k in veh}
    for i in cust:
        hits = [(t, k) for k in veh
                for t in range(lo[i], hi[i] + 1) if val(o[t, i, k]) == 1]
        if len(hits) != 1:
            print(f"customer {i}: {len(hits)} visits VIOLATION! {hits}")
        for t, k in hits:
            routes[k].append((t, i))
    # 同一地点 (c[u][v] == 0) のペアは gap が 0 なので同時刻に来うる。
    # 他の点への距離は同じとは限らないので、並びは order_ties() で決める
    # (order_ties は 0 への帰着で締めるが、c[·][0] == c[·][N+1] なので同じこと)。
    for k in veh:
        routes[k] = order_ties(inst, sorted(routes[k]))

    ret_t = {k: [t for t in range(lo[end], hi[end] + 1)
                 if val(o[t, end, k]) == 1] for k in veh}
    for k in veh:
        if len(ret_t[k]) != 1:
            print(f"vehicle {k}: 帰着デポ {end} が {len(ret_t[k])} 個 "
                  "VIOLATION!")
    return routes, ret_t


def print_multi_summary(inst, routes, scheds, ret_t, sol):
    """全車両をまとめた要約。QUBO のエネルギーとは独立に検算する。

    feasible / total travel / return は、各車両のルートを最早開始で辿り直した
    値（tsptwlib.verify_tour() と同じ基準）。scheds はモデル側の時刻で、
    「ソルバの時刻の辻褄が合っているか」は model times の行に分けて出す。
    """
    E, L, N, end = inst.E, inst.L, inst.N, inst.end
    visited = [i for k in routes for _, i in routes[k]]
    dup = len(visited) != len(set(visited))
    chks = {k: simulate(inst, full_route(inst, routes[k])) for k in routes}
    tw_violations = sum(1 for k, seq in routes.items() for _, i in seq
                        if chks[k].start[i] > L[i])
    over = [k for k, ch in chks.items() if ch.ret > L[end]]
    total_travel = sum(ch.travel for ch in chks.values())
    feasible = (not dup and len(set(visited)) == N
                and tw_violations == 0 and not over)

    # モデル側の時刻（ソルバが選んだ開始時刻）の辻褄
    early = sum(1 for k, seq in routes.items() for t, i in seq
                if t < scheds[k].arrival[i])
    late = sum(1 for k, seq in routes.items() for t, i in seq
               if not (E[i] <= t <= L[i]))
    ret_ok = all(len(ts) == 1 and ts[0] == scheds[k].ret
                 for k, ts in ret_t.items())

    print("\n=== summary ===")
    for k in sorted(routes):
        print(f"route[{k}]    =", full_route(inst, routes[k]))
    print(f"visited     = {len(set(visited))}/{N}"
          f"{'  (重複あり)' if dup else ''}")
    print("total travel =", total_travel)
    print("max travel  =", max((ch.travel for ch in chks.values()),
                               default=0))
    print(f"return      = {[chks[k].ret for k in sorted(chks)]} "
          f"(limit {L[end]}, 最早開始)"
          f"{'  VIOLATION! ' + str(over) if over else ''}")
    print("tw violations =", tw_violations)
    print("feasible    =", feasible)
    ok = early == 0 and late == 0
    print(f"model times = {'ok' if ok else 'INCONSISTENT'} "
          f"(ソルバの時刻: 到着前の開始 {early} / 時間枠外 {late})")
    print(f"帰着デポ {end} の変数 == モデルの帰着 = {ret_ok}")
    if sol is not None:
        print("var_count   =", sol.info["var_count"])
        print("term_count  =", sol.info["term_count"])
    return feasible


def save_plot_single(inst, seq, s, prefix, opt):
    """m = 1 のときだけ描く。tsptwlib.plot_tour は depot 0 で閉じるツアー前提
    なので、読み込んだままのインスタンス (inst.base) に戻して渡す。"""
    base = inst.base
    tour = [0] + [i for _, i in seq] + [0]
    sched = _schedule_from_starts_single(base, seq, s)
    return save_plot(base, tour, sched, prefix, opt)
