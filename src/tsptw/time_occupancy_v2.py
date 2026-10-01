"""在圏型 TSPTW QUBO の改良版（実験用）。変数 o[t][v] の意味は time_occupancy.py と同じ。

    o[t][v] = 1 <=> 時刻 t に頂点 v に居る（到着済み・出発前）

time_occupancy.py からの変更点（どれもオプションで切り替えられる）
-------------------------------------------------------------------
1. 定義域の締め付け（既定 on、--no-prune で切る）
   prune_time_windows()（prec_disjunctive.py と共通）の不動点で、サービス域
   [lo[v], hi[v]] と直行可能なアークを締める。待機域の下端（最早到着）は
   「直行可能な先行頂点からの最早到着」と「必ず先に来る頂点からの最短路」で決める。
2. 必ず先に来るペアの全面禁止（既定 on、--no-prec）
   u ≺ v（u は必ず v より前）が前処理で分かっているペアは、
   「u に時刻 t、v に時刻 t' < t + gap(u,v)」をすべて禁止する（逆順も含む）。
   逆向きの衝突項（v が先で u が後）は作らない。
3. 直行できない対の gap を最短路にする（既定 on、--no-arcgap）
4. 学習ラウンド（--rounds R）
   制限時間を R 等分して解き直し、破れた衝突ペアの係数と、破れた（落ちた・
   二重の）顧客の係数を --grow 倍する（初期値の --cap 倍まで）。初期解は直前の解。
5. 部分問題の解き直し（--lns K）
   最初の --lns-init 秒は全体を解き、その後は現在の解でツアー上に連続する
   K 顧客だけを自由にし、残りの o を現在値に固定した QUBO を --lns-time 秒ずつ
   解き直す（窓は K/2 ずつずらす）。エネルギーが下がらなければ元に戻す。
   変数も式も同じ QUBO で、固定の仕方を変えて何度も解くだけ。
"""
import argparse
import os
import random
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pyqbpp as qbpp

from tsptwlib import (colocated_terms, load_instance, print_time_detail,
                      recover_time_tour, save_plot, schedule_from_starts)
from tsptwlib.cli import parse_args
from tsptwlib.prune import prune_time_windows, shortest_paths
from tsptwlib.report import print_summary, verify_tour
from tsptwlib.timeindex import arrival_lower_bounds

PREFIX = "tsptw_time_occupancy_v2"


def extra_args(argv):
    """共通 CLI にない、この実験版だけのオプションを argv から抜き出す。"""
    p = argparse.ArgumentParser(add_help=False)
    p.add_argument("--no-prune", dest="prune", action="store_false")
    p.add_argument("--no-prec", dest="prec", action="store_false")
    p.add_argument("--no-arcgap", dest="arcgap", action="store_false")
    p.add_argument("--early", type=int, default=0, metavar="S",
                   help="目的を S*総移動時間 + Σ出発時刻 にする (0 で使わない、"
                        "-1 で自動 = Σ(サービス域の幅)+1。これなら最適な移動時間は変わらない)。"
                        "同じ移動時間なら早い時刻ほど低エネルギーになり、"
                        "後続の時刻を詰める連鎖が坂道になる")
    p.add_argument("--slim2", action="store_true",
                   help="発側が待機スロットの衝突項を落とす（time_occupancy.py の --slim と同じ理屈）")
    p.add_argument("--lns-mode", choices=("tour", "time", "mix"), default="tour",
                   help="部分問題の選び方。tour: ツアー上で連続する K 顧客、"
                        "time: ランダムな時刻の近くにサービス域がかかる K 顧客、mix: 交互")
    p.add_argument("--exact", action="store_true",
                   help="三角不等式が破れたアークの帯の端を 3 次の補正項にする")
    p.add_argument("--alt", action="store_true",
                   help="LNS の部分問題で --early あり/なしの目的を交互に使う")
    p.add_argument("--stay", action="store_true",
                   help="サービス域でも滞在してよい（出発 = 在圏区間の最後）")
    p.add_argument("--rounds", type=int, default=1)
    p.add_argument("--grow", type=float, default=2.0)
    p.add_argument("--cap", type=float, default=4.0)
    p.add_argument("--conf-scale", type=float, default=1.0)
    p.add_argument("--cust-scale", type=float, default=1.0)
    p.add_argument("--restart", action="store_true",
                   help="学習ラウンドで直前の解を初期解に渡さない")
    p.add_argument("--lns", type=int, default=0, metavar="K",
                   help="部分問題で自由にする連続顧客数 (0 で使わない)")
    p.add_argument("--lns-init", type=float, default=None,
                   help="LNS の前に全体を解く秒数 (既定 制限時間の 1/4)")
    p.add_argument("--lns-time", type=float, default=1.0,
                   help="部分問題 1 回の制限時間 (秒)。K が広がるとその比で延ばす")
    p.add_argument("--lns-tpt", type=float, default=1.0,
                   help="部分問題の制限時間を 部分 QUBO 10 万項あたりこの秒数にする "
                        "(下限 --lns-time、上限 --lns-tmax)")
    p.add_argument("--lns-tmax", type=float, default=10.0)
    p.add_argument("--init-early", action="store_true",
                   help="最初の全体の求解にも --early の目的を使う (既定は使わない)")
    p.add_argument("--lns-max", type=int, default=60,
                   help="1 周改善がなければ K を 1.5 倍に広げる。その上限")
    p.add_argument("--solver-param", action="append", default=[],
                   metavar="KEY=VAL", help="ABS3 に渡す追加パラメータ")
    return p.parse_known_args(argv)


def domains(inst, use_prune):
    """(svc, olo, ohi, prec, d, arcs)。svc..ohi がサービス域、olo..svc-1 が待機域。"""
    N, c, E, L = inst.N, inst.c, inst.E, inst.L
    cust = list(range(1, N))
    d = shortest_paths(c)
    if not use_prune:
        arr = arrival_lower_bounds(inst, [0] * (N + 1), cust)
        svc = {v: max(E[v], arr[v]) for v in cust}
        ohi = {v: min(L[v], L[0] - c[v][0]) for v in cust}
        return svc, dict(arr), ohi, set(), d, None

    lo, hi, arcs, _ = prune_time_windows(inst)
    prec = {(u, v) for u in cust for v in cust
            if u != v and lo[v] + d[v][u] > hi[u]}
    svc = {v: lo[v] for v in cust}
    ohi = {v: hi[v] for v in cust}
    olo = {}
    for v in cust:
        if lo[v] > E[v]:            # サービス開始の下界が窓より遅い -> 待機しない
            olo[v] = lo[v]
            continue
        a = min(c[u][v] if u == 0 else lo[u] + c[u][v]
                for (u, w) in arcs if w == v)
        for u in cust:
            if (u, v) in prec:
                a = max(a, lo[u] + d[u][v])
        olo[v] = min(max(a, c[0][v]), lo[v])
    return svc, olo, ohi, prec, d, arcs


class OccupancyModel:
    """在圏型の QUBO 一式。係数（学習ラウンドの重み）を変えて何度でも組み直せる。"""

    def __init__(self, inst, ex):
        self.inst, self.ex = inst, ex
        N, c, L = inst.N, inst.c, inst.L
        self.ret = ret = N
        self.cust = cust = list(range(1, N))
        self.nodes = nodes = cust + [ret]

        svc, olo, ohi, prec, d, arcs = domains(inst, ex.prune)
        svc[ret] = olo[ret] = max(svc[v] + d[v][0] for v in cust)
        ohi[ret] = L[0]
        self.svc, self.olo, self.ohi = svc, olo, ohi
        empty = [v for v in nodes if svc[v] > ohi[v]]
        if empty:
            print(f"WARNING: サービス域が空の頂点 {empty}（実行不可能なインスタンス）")

        o = self.o = {}
        for v in nodes:
            for t in range(olo[v], ohi[v] + 1):
                o[t, v] = qbpp.var(f"o_{t}_{v}")
        n_wait = sum(svc[v] - olo[v] for v in cust)
        print(f"N={N}  o vars = {len(o)}  (待機 {n_wait} / サービス {len(o) - n_wait})"
              f"  prune={ex.prune}  prec={ex.prec} ({len(prec)} 組)  arcgap={ex.arcgap}")

        # 制約A: サービス域にちょうど 1 スロット（顧客ごと）
        #   --stay: サービス域に「区間の終わり（出発）」がちょうど 1 つ。
        #   終わり = o[t] (1 - o[t+1])。待機域では連続性が終わりを禁じるので、
        #   区間がちょうど 1 本でサービス域で終わることと同値。本体は 2 次式だが
        #   宣言制約なので展開されない（違反量の 2 乗をソルバが直接計算する）。
        self.stay = ex.stay
        if ex.stay:
            def end(t, v):
                if (t + 1, v) in o:
                    return o[t, v] * (1 - o[t + 1, v])
                return o[t, v]
            self.once = {v: qbpp.sum(end(t, v) for t in range(svc[v], ohi[v] + 1)) == 1
                         for v in cust}
            self.once[ret] = qbpp.sum(o[t, ret]
                                      for t in range(svc[ret], ohi[ret] + 1)) == 1
        else:
            self.once = {v: qbpp.sum(o[t, v] for t in range(svc[v], ohi[v] + 1)) == 1
                         for v in nodes}

        # 制約B: 衝突（頂点の対ごとに束ねる。学習ラウンドの単位）
        def gap(u, v):
            if u == ret:
                return qbpp.inf
            w = 0 if v == ret else v
            if ex.arcgap and arcs is not None and (u, w) not in arcs:
                return d[u][w]      # 直行できない -> 間に必ず誰かが挟まる
            return c[u][w]

        pt = self.pair_terms = {}

        def add(u, t, v, tp, ws=None):
            key = (u, v) if u < v else (v, u)
            pt.setdefault(key, []).append((t, u, tp, v, ws))

        # --exact: 直行しうるが c(u,v) > d(u,v) の対（三角不等式の破れ）は、
        # u と v の間に近道の頂点 w が挟まるなら d(u,v) までしか離れなくてよい。
        # 帯 [t+d, t+c) は「間に w の出発が無いときだけ」禁止する 3 次の項にする。
        # 間に 2 頂点挟める対は補正項が負の報酬になりうるので補正しない。
        def shortcut(u, v):
            if not ex.exact or u == ret or arcs is None:
                return None
            tgt = 0 if v == ret else v
            cuv = c[u][tgt]
            if (u, tgt) not in arcs or cuv <= d[u][tgt]:
                return None
            W = [w for w in cust if w not in (u, v)
                 and d[u][w] + d[w][tgt] <= cuv - 1]
            for w1 in W:
                for w2 in W:
                    if (w1 != w2 and c[u][w1] + c[w1][w2] + c[w2][tgt] <= cuv - 1
                            and (u, w1) in arcs and (w1, w2) in arcs
                            and (w2, tgt) in arcs):
                        return None
            return d[u][tgt], W
        n_cubic = 0

        for u in nodes:
            for v in nodes:
                if u == v:
                    continue
                if ex.prec and (v, u) in prec:
                    continue        # v が必ず先: u 先の向きは (v, u) 側の全面禁止で覆う
                g = gap(u, v)
                full = ex.prec and (u, v) in prec
                # 発側 u が待機スロット t なら、u の出発 s > t からの項が常に強い
                src_lo = svc[u] if (ex.slim2 and u != ret) else olo[u]
                sc = shortcut(u, v)
                for t in range(src_lo, ohi[u] + 1):
                    lo_ = olo[v] if full else max(t, olo[v])
                    hi_ = ohi[v] if g is qbpp.inf else min(t + g - 1, ohi[v])
                    for tp in range(lo_, hi_ + 1):
                        if sc is not None and tp >= t + sc[0]:
                            ws = tuple((tau, w) for w in sc[1]
                                       for tau in range(max(t + 1, svc[w]),
                                                        min(tp - 1, ohi[w]) + 1))
                            add(u, t, v, tp, ws)
                            n_cubic += 1
                        else:
                            add(u, t, v, tp)

        def term(t, u, tp, v, ws):
            if ws is None:
                return o[t, u] * o[tp, v]
            e = qbpp.expr() + o[t, u] * o[tp, v]
            for k in ws:
                e -= o[t, u] * o[tp, v] * o[k]
            return e
        self.pair_expr = {k: qbpp.sum(term(*e) for e in x) for k, x in pt.items()}
        print(f"conflict terms = {sum(len(x) for x in pt.values())}  ({len(pt)} 対)"
              f"  うち 3 次の補正 {n_cubic}")

        if ex.stay:
            # 同一地点ペア (c = 0) は衝突項が無いので、在圏が 2 スロット以上重なる
            # （同じ時間を 2 頂点に数える）ことだけを 4 次の項で禁じる。
            # 1 スロットの重なりは受け渡し（片方の出発と片方の到着が同時刻）。
            self.colocated = qbpp.expr()
            n_col = 0
            for u in cust:
                for v in cust:
                    if u < v and c[u][v] == 0 and c[v][u] == 0:
                        for t in range(max(olo[u], olo[v]), min(ohi[u], ohi[v])):
                            self.colocated += (o[t, u] * o[t + 1, u]
                                               * o[t, v] * o[t + 1, v])
                            n_col += 1
        else:
            self.colocated, n_col = colocated_terms(inst, cust, o, olo, svc, ohi)
        print(f"colocated terms = {n_col}")

        self.contiguity = qbpp.expr()
        for v in cust:
            for t in range(olo[v], min(svc[v], ohi[v] + 1)):
                nxt = qbpp.expr()
                if (t + 1, v) in o:
                    nxt += o[t + 1, v]
                self.contiguity += o[t, v] * (1 - nxt)

        if ex.stay:     # 滞在 = 在圏スロット数 - 1（最後のスロットが出発）
            self.total_wait = (qbpp.sum(o[t, v] for v in cust
                                        for t in range(olo[v], ohi[v] + 1))
                               - len(cust))
        else:
            self.total_wait = qbpp.sum(o[t, v] for v in cust
                                       for t in range(olo[v], svc[v]))
        self.objective = (qbpp.sum(t * o[t, ret]
                                   for t in range(svc[ret], ohi[ret] + 1))
                          - self.total_wait)

        # 出発時刻の和（--early のタイブレーク用）。サービス域の o は出発の one-hot
        self.depart_sum = qbpp.sum(t * o[t, v] for v in cust
                                   for t in range(svc[v], ohi[v] + 1))
        # Σ出発時刻の変動幅。S がこれを超えれば、移動時間 1 の差は時刻の和で覆せない
        self.early_auto = sum(ohi[v] - svc[v] for v in cust) + 1
        maxc = max(max(row) for row in c)
        self.P_RET = L[0] + 1
        self.P_CUST = int((4 * maxc + 1) * ex.cust_scale)
        self.P_CONF = int((2 * maxc + 1) * ex.conf_scale)
        self.P_CONT = 2 * maxc + 1
        print(f"penalty: RET={self.P_RET} CUST={self.P_CUST} "
              f"CONF={self.P_CONF} CONT={self.P_CONT}")
        self.w_cust = {v: 1.0 for v in cust}
        self.w_pair = {k: 1.0 for k in pt}

    def build(self, early=None):
        early = self.ex.early if early is None else early
        if early < 0:
            early = self.early_auto
        S = max(1, early)
        f = S * self.objective + S * self.P_RET * qbpp.cons(self.once[self.ret])
        if early > 0:
            f += self.depart_sum
        for v in self.cust:
            f += int(round(S * self.P_CUST * self.w_cust[v])) * qbpp.cons(self.once[v])
        for k, e in self.pair_expr.items():
            f += int(round(S * self.P_CONF * self.w_pair[k])) * e
        f += S * self.P_CONF * self.colocated + S * self.P_CONT * self.contiguity
        return qbpp.simplify_as_binary(f)

    def bits(self, sol):
        return {k: sol(var) for k, var in self.o.items()}

    def n_ends(self, bit, v):
        if self.stay and v != self.ret:
            return sum(1 for t in range(self.svc[v], self.ohi[v] + 1)
                       if bit[t, v] and not bit.get((t + 1, v), 0))
        return sum(bit[t, v] for t in range(self.svc[v], self.ohi[v] + 1))

    def departure(self, bit, v):
        """出発（サービス）時刻。--stay ならサービス域で最後の 1、そうでなければ最初の 1。"""
        ts = [t for t in range(self.svc[v], self.ohi[v] + 1) if bit[t, v]]
        if not ts:
            return None
        return ts[-1] if self.stay else ts[0]

    def evaluate(self, bit):
        """(bad_cust, bad_pair, tour, chk)。tour はサービススロットの時刻順。"""
        svc, ohi = self.svc, self.ohi
        bad_cust = [v for v in self.nodes if self.n_ends(bit, v) != 1]
        bad_pair = [k for k, x in self.pair_terms.items()
                    if any(bit[t, u] and bit[tp, v]
                           and not (ws and any(bit[q] for q in ws))
                           for (t, u, tp, v, ws) in x)]
        start = {v: self.departure(bit, v) for v in self.cust}
        seq = sorted((t, v) for v, t in start.items() if t is not None)
        tour = [0] + [v for _, v in seq] + [0]
        return bad_cust, bad_pair, tour, verify_tour(self.inst, tour)

    def time_window(self, bit, rng, K):
        """ランダムな顧客の出発時刻を中心に、サービス域がその時刻に近い順に K 顧客。"""
        center = rng.choice(self.cust)
        T = self.departure(bit, center)
        if T is None:
            T = (self.svc[center] + self.ohi[center]) // 2

        def dist(v):
            if self.svc[v] <= T <= self.ohi[v]:
                return 0
            return min(abs(self.svc[v] - T), abs(self.ohi[v] - T))
        near = sorted(self.cust, key=lambda v: (dist(v), rng.random()))[:K]
        free = set(near)
        if max(self.departure(bit, v) or 0 for v in near) >= max(
                self.departure(bit, v) or 0 for v in self.cust):
            free.add(self.ret)
        return free

    def order(self, bit):
        """現在の解でのツアー順。落ちている顧客はサービス域の中央の時刻で差し込む。"""
        key = {}
        for v in self.cust:
            t = self.departure(bit, v)
            key[v] = t if t is not None else (self.svc[v] + self.ohi[v]) / 2
        return sorted(self.cust, key=lambda v: key[v])


def solver_kw(opt, ex, time_limit, seed_offset=0):
    kw = {"time_limit": max(time_limit, 0.1)}
    if opt.seed is not None:
        kw["seed"] = int(opt.seed) + seed_offset
    if opt.auto_swap:
        kw["auto_swap"] = 1
    for kv in ex.solver_param:
        k, v = kv.split("=", 1)
        kw[k] = v
    return kw


def main(opt, ex):
    inst = load_instance(opt.instance)
    print(inst.summary())
    t_build = time.perf_counter()
    m = OccupancyModel(inst, ex)
    f = m.build()
    build_sec = time.perf_counter() - t_build
    print(f"build       = {build_sec:.3f} sec")
    if opt.build_only:
        return

    target = opt.target_energy
    t0 = time.perf_counter()
    elapsed = lambda: time.perf_counter() - t0
    best = {"key": None}

    def record(sol, f_now, tag):
        bit = m.bits(sol)
        bad_cust, bad_pair, tour, chk = m.evaluate(bit)
        e = sol(f_now)
        key = (not chk["feasible"], chk["travel"])
        if best["key"] is None or key < best["key"]:
            best.update(key=key, bit=bit, t=elapsed(), tour=tour)
        print(f"{tag}: energy={e} obj={sol(m.objective)} feasible={chk['feasible']} "
              f"travel={chk['travel']} bad_cust={bad_cust[:6]} "
              f"bad_pair={len(bad_pair)} {bad_pair[:4]} t={elapsed():.1f}",
              flush=True)
        return bit, bad_cust, bad_pair, chk

    def reached(chk):
        return target is not None and chk["feasible"] and chk["travel"] <= target

    # ---------------- 1. 全体を解く（学習ラウンドつき） ----------------
    t_full = opt.time_limit if ex.lns <= 0 else (
        ex.lns_init if ex.lns_init is not None else opt.time_limit / 4)
    hint = None
    done = False
    init_early = None if ex.init_early else 0       # None = ex.early をそのまま使う
    f = m.build(early=init_early)
    for r in range(ex.rounds):
        if r > 0:
            f = m.build(early=init_early)
        kw = solver_kw(opt, ex, (t_full - elapsed()) / (ex.rounds - r), 1000 * r)
        if target is not None and (ex.early == 0 or not ex.init_early):
            kw["target_energy"] = float(target)
        if hint is not None and not ex.restart:
            kw["hint"] = qbpp.Sol(f).set(hint)
        sol = qbpp.ABS3Solver(f).search(**kw)
        bit, bad_cust, bad_pair, chk = record(sol, f, f"round {r}")
        if reached(chk):
            done = True
            break
        for v in bad_cust:
            if v != m.ret:
                m.w_cust[v] = min(m.w_cust[v] * ex.grow, ex.cap)
        for k in bad_pair:
            m.w_pair[k] = min(m.w_pair[k] * ex.grow, ex.cap)
        hint = sol
        if t_full - elapsed() <= 0.5:
            break

    # ---------------- 2. 部分問題の解き直し ----------------
    # 現在の解は bit（o の値の辞書）で持つ。部分問題ごとに目的の版 fv を選び、
    # その版でのエネルギーが下がらなければ採用しない（同じなら採用 = 平地を歩く）。
    if ex.lns > 0 and not done:
        if ex.early != 0:
            fe = m.build()
            variants = [("early", fe)] + ([("plain", m.build(early=0))] if ex.alt else [])
        else:
            variants = [("", m.build(early=0))]
        bit = m.bits(sol)

        def energy(fv, b):
            return qbpp.Sol(fv).set({m.o[k]: x for k, x in b.items()}).comp_energy()

        K0 = K = min(ex.lns, len(m.cust))
        stride = max(1, K // 3)
        start = 0
        it = 0
        rng = random.Random(opt.seed or 0)
        n_acc = 0
        improved_in_pass = False
        n_restart = 0
        lns_time = ex.lns_time
        while elapsed() < opt.time_limit - lns_time * 0.5:
            order = m.order(bit)
            if start >= len(order):
                # 1 周したら窓の位置をずらす。1 周まるごと改善がなければ窓を広げ、
                # 上限でも改善がなければ初期の幅に戻す
                if not improved_in_pass:
                    if K < min(ex.lns_max, len(m.cust)):
                        K = min(int(K * 1.5), ex.lns_max, len(m.cust))
                    else:
                        # どの幅でも改善しない -> 初期解なしで全体を解き直して再出発
                        K = K0
                        n_restart += 1
                        f0 = m.build(early=0)
                        kw = solver_kw(opt, ex, min(t_full, opt.time_limit - elapsed()),
                                       5000 + n_restart)
                        if target is not None:
                            kw["target_energy"] = float(target)
                        rs = qbpp.ABS3Solver(f0).search(**kw)
                        bit, _, _, chk = record(rs, f0, f"restart {n_restart}")
                        if reached(chk):
                            break
                    stride = max(1, K // 3)
                    print(f"lns: K = {K} (t={elapsed():.1f})", flush=True)
                    start = 0
                else:
                    start = rng.randrange(stride)
                improved_in_pass = False
            use_time = ex.lns_mode == "time" or (ex.lns_mode == "mix" and it % 2 == 1)
            if use_time:
                free = m.time_window(bit, rng, K)
            else:
                free = set(order[start:start + K])
                if start + K >= len(order):
                    free.add(m.ret)
                start += stride
            name, fv = variants[it % len(variants)]
            cur_e = energy(fv, bit)
            ml = {var: bit[k] for k, var in m.o.items() if k[1] not in free}
            g = qbpp.Model(qbpp.simplify_as_binary(qbpp.replace(fv, ml)))
            lns_time = min(max(ex.lns_time, ex.lns_tpt * g.term_count() / 1e5),
                           ex.lns_tmax)
            kw = solver_kw(opt, ex, min(lns_time, opt.time_limit - elapsed()),
                           10 + it)
            kw["hint"] = qbpp.Sol(g).set({var: bit[k] for k, var in m.o.items()
                                          if k[1] in free and g.has(var)})
            sub = qbpp.ABS3Solver(g).search(**kw)
            new = qbpp.Sol(fv).set(sub, ml)
            new_e = new.comp_energy()
            it += 1
            if new_e <= cur_e:
                bit = m.bits(new)
                if new_e < cur_e:
                    n_acc += 1
                    improved_in_pass = True
                    if not use_time:        # 改善した窓の近くをもう一度探る
                        start = max(0, start - 2 * stride)
                    _, _, _, chk = record(new, fv, f"lns {it} {name}(K={K})")
                    if reached(chk):
                        break
        print(f"lns: {it} 回解き直し、改善 {n_acc} 回、再出発 {n_restart} 回")

    # ---------------- 3. 結果（最良の検算値の解） ----------------
    print(f"\n----------result({opt.time_limit} sec)----------")
    bit = best["bit"]
    final = qbpp.Sol(f).set({m.o[k]: b for k, b in bit.items()})
    print("energy          =", final.comp_energy())
    print("objective       =", final(m.objective))
    print("total_wait      =", final(m.total_wait))
    bad_cust, bad_pair, _, _ = m.evaluate(bit)
    print("violated cons   =", len(bad_cust) + len(bad_pair))
    print(f"TTS         = {best['t']:.3f} sec (最良解を見つけた時刻)")
    from tsptwlib.report import order_ties
    dep = {v: m.departure(bit, v) for v in m.cust}
    seq = order_ties(inst, sorted((t, v) for v, t in dep.items() if t is not None))
    tour = [0] + [v for _, v in seq] + [0]
    sched = schedule_from_starts(inst, seq, [0] * (inst.N + 1))
    print_time_detail(inst, seq, sched, quiet=opt.quiet)
    print_summary(inst, tour, sched, None)
    print("var_count   =", len(m.o))
    print("term_count  =", qbpp.Model(f).term_count())
    print(f"build       = {build_sec:.3f} sec (式の構築 + simplify)")
    save_plot(inst, tour, sched, PREFIX, opt)


if __name__ == "__main__":
    ex, rest = extra_args(sys.argv[1:])
    main(parse_args(rest, supports=()), ex)
