"""順序型 (x[i][u]) の定義域・枝刈り・上下界。

もともと order_start.py / order_start_tiered.py / order_wait.py / order_prefix.py に
同じ関数が 4 セット重複していたものを 1 か所にまとめた。健全性 (実行可能解を
落とさないこと) の根拠は各関数の docstring に書いてある。

枝刈りを使う定式化は prepare_order(inst) を 1 回呼べば必要な配列が揃う。
枝刈りを使わない定式化 (order_prefix.py) は個別の関数を直接呼ぶ。
"""
from dataclasses import dataclass


# --------------------------------------------------------------------------
# 移動時間そのものの上下界
# --------------------------------------------------------------------------
def min_leg(inst):
    """u != v の最小移動時間。0 でも健全 (枝刈りが弱くなるだけ)。"""
    c, N = inst.c, inst.N
    legs = [c[u][v] for u in range(N) for v in range(N) if u != v]
    return min(legs) if legs else 0


def max_leg(inst):
    """u != v の最大移動時間。"""
    c, N = inst.c, inst.N
    legs = [c[u][v] for u in range(N) for v in range(N) if u != v]
    return max(legs) if legs else 0


def travel_range(inst):
    """総移動時間の下界 / 上界 (各行の最小 / 最大 leg の総和)。

    ツアーは各点をちょうど 1 回出るので、行ごとの最小 (最大) を足したものが
    総移動時間の下界 (上界) になる。ペナルティ係数の基準に使う。
    """
    c, N = inst.c, inst.N
    lb = sum(min(c[u][v] for v in range(N) if v != u) for u in range(N))
    ub = sum(max(c[u][v] for v in range(N) if v != u) for u in range(N))
    return lb, ub


# --------------------------------------------------------------------------
# 顧客ごと / 位置ごとの時刻の上下界
# --------------------------------------------------------------------------
def customer_time_bounds(inst):
    """顧客ごとのサービス開始時刻の下限 lo / 上限 hi。

    lo[u] : depot から直行しても c[0][u] はかかるので max(E[u], c[0][u])
    hi[u] : ここから depot に L[0] までに帰れる必要があるので
            min(L[u], L[0] - c[u][0])
    """
    c, E, L, N = inst.c, inst.E, inst.L, inst.N
    lo = [0] * N
    hi = [0] * N
    lo[0] = E[0]
    hi[0] = L[0]
    for u in range(1, N):
        lo[u] = max(E[u], c[0][u])
        hi[u] = min(L[u], L[0] - c[u][0])
    return lo, hi


def position_bounds(inst, lo, hi, cmin, a0):
    """位置 i (1..N-1) のサービス開始時刻の下限 / 上限。

    a[i] >= a[i-1] + cmin, a[i] <= a[i+1] - cmin が成り立つので、
    両端から cmin ずつ積み上げる。
    """
    N = inst.N
    lo_pos = [0] * N
    hi_pos = [0] * N
    lo_pos[0] = a0
    hi_pos[0] = a0
    first_lo = max(min(lo[u] for u in range(1, N)), a0 + cmin)
    last_hi = max(hi[u] for u in range(1, N))
    for i in range(1, N):
        lo_pos[i] = first_lo + (i - 1) * cmin
        hi_pos[i] = last_hi - (N - 1 - i) * cmin
    return lo_pos, hi_pos


def order_bounds(inst, lo, hi):
    """顧客 u が取り得る位置の下限 first / 上限 last。

    サービス開始時刻はツアーに沿って単調非減少 (c >= 0) なので、
      u の前に来る顧客 v は lo[v] <= hi[u]
      u の後に来る顧客 v は hi[v] >= lo[u]
    を満たす。それぞれの個数が u の前後に必要な人数以上でなければならない。
    """
    N = inst.N
    first = [1] * N
    last = [N - 1] * N
    for u in range(1, N):
        preds = sum(1 for v in range(1, N) if v != u and lo[v] <= hi[u])
        succs = sum(1 for v in range(1, N) if v != u and hi[v] >= lo[u])
        first[u] = max(1, (N - 1) - succs)
        last[u] = min(N - 1, preds + 1)
    return first, last


def allowed_customers(inst, lo, hi, lo_pos, hi_pos, first, last):
    """位置 i に置ける顧客の集合。allowed[0] は depot のみ。

    時刻区間が交わらない (i, u) と、位置の上下界から外れる (i, u) を落とす。
    ここで落ちた x[i][u] は fix_map() で 0 に固定される。
    """
    N = inst.N
    allowed = [[] for _ in range(N)]
    allowed[0] = [0]
    for i in range(1, N):
        for u in range(1, N):
            if not (first[u] <= i <= last[u]):
                continue
            if max(lo[u], lo_pos[i]) > min(hi[u], hi_pos[i]):
                continue
            allowed[i].append(u)
    return allowed


def all_allowed(inst):
    """枝刈りをしない場合の allowed (位置 0 は depot、以降は全顧客)。"""
    N = inst.N
    return [[0]] + [list(range(1, N)) for _ in range(1, N)]


def start_domains(inst, allowed, lo, hi, lo_pos, hi_pos, a0):
    """位置 i のサービス開始時刻 a[i] の定義域 [a_lo, a_hi]。

    a[0] は depot 出発時刻なので幅 0 (定数になる)。
    """
    N = inst.N
    dom = [(a0, a0)] * N
    for i in range(1, N):
        if allowed[i]:
            a_lo = max(lo_pos[i], min(lo[u] for u in allowed[i]))
            a_hi = min(hi_pos[i], max(hi[u] for u in allowed[i]))
        else:
            a_lo, a_hi = lo_pos[i], hi_pos[i]
        dom[i] = (a_lo, a_hi)
    return dom


def prefix_domains(inst, lo, hi, a0, cmin):
    """order_prefix.py の w[i] の定義域。

    w[i] は「位置 i のサービス開始時刻」そのものなので範囲は時刻。
    枝刈り (allowed) を使わないぶん、position_bounds と同じ積み上げだけで絞る。
    下限が上限を超えた位置は幅 0 に潰す (max(wlo, whi))。
    """
    N = inst.N
    first_lo = max(min(lo[1:]), a0 + cmin)
    last_hi = max(hi[1:])
    dom = [(a0, a0)]
    for i in range(1, N):
        wlo = first_lo + (i - 1) * cmin
        whi = last_hi - (N - 1 - i) * cmin
        dom.append((wlo, max(wlo, whi)))
    return dom


def leg_bounds(inst, allowed, i):
    """位置 i-1 -> i の leg の最小 / 最大。allowed が空なら (0, 0)。"""
    c = inst.c
    legs = [c[u][v] for u in allowed[i - 1] for v in allowed[i] if u != v]
    return (min(legs), max(legs)) if legs else (0, 0)


def wait_upper_bounds(inst, allowed, dom, a0, travel_lb):
    """位置ごとの待ち時間の上界 w_hi[i] (i = 1..N-1)。

    order_cumulative.py の between=(0, 100) 固定を置き換える。2 つの上界の小さい方。

      (1) 定義域から: w[i] = a[i] - a[i-1] - leg[i]
                          <= a_hi[i] - a_lo[i-1] - (i に入る最小 leg)
      (2) 総量から  : 実行可能なツアーでは
                      Σ_i w[i] = (帰着時刻) - a[0] - (総移動時間)
                               <= L[0] - a[0] - travel_lb
                      なので、どの 1 位置の待ちもこれを超えられない。
    """
    N, L = inst.N, inst.L
    budget = max(0, L[0] - a0 - travel_lb)
    w_hi = [0] * N
    for i in range(1, N):
        leg_lo, _ = leg_bounds(inst, allowed, i)
        by_dom = dom[i][1] - dom[i - 1][0] - leg_lo
        w_hi[i] = max(0, min(by_dom, budget))
    return w_hi


# --------------------------------------------------------------------------
# 枝刈りありの順序型で使う一式
# --------------------------------------------------------------------------
@dataclass
class OrderBounds:
    """順序型の前処理結果。prepare_order() が作る。"""
    a0: int                     # depot 出発時刻 (= E[0])
    cmin: int                   # 最小 leg
    lo: list                    # 顧客ごとの開始時刻下限
    hi: list                    # 顧客ごとの開始時刻上限
    lo_pos: list                # 位置ごとの下限
    hi_pos: list                # 位置ごとの上限
    first: list                 # 顧客が取り得る位置の下限
    last: list                  # 顧客が取り得る位置の上限
    allowed: list               # 位置 i に置ける顧客
    dom: list                   # a[i] の定義域 (lo, hi)
    travel_lb: int
    travel_ub: int


def prepare_order(inst, *, prune=True):
    """順序型の前処理をまとめて実行する。

    prune=False なら枝刈りをせず allowed を「全顧客」にする
    (order_prefix のように枝刈りを持たない定式化と界を揃えて比べたいとき用)。
    """
    a0 = inst.E[0]                              # depot 出発時刻 (Dumas では 0)
    lo, hi = customer_time_bounds(inst)
    cmin = min_leg(inst)
    lo_pos, hi_pos = position_bounds(inst, lo, hi, cmin, a0)
    first, last = order_bounds(inst, lo, hi)
    if prune:
        allowed = allowed_customers(inst, lo, hi, lo_pos, hi_pos, first, last)
    else:
        allowed = all_allowed(inst)
    dom = start_domains(inst, allowed, lo, hi, lo_pos, hi_pos, a0)
    travel_lb, travel_ub = travel_range(inst)
    return OrderBounds(a0=a0, cmin=cmin, lo=lo, hi=hi,
                       lo_pos=lo_pos, hi_pos=hi_pos,
                       first=first, last=last, allowed=allowed, dom=dom,
                       travel_lb=travel_lb, travel_ub=travel_ub)


# --------------------------------------------------------------------------
# 前処理の結果を報告する (どの定式化でも同じ書式で出す)
# --------------------------------------------------------------------------
def report_pruning(inst, b):
    """到達不能な顧客・枝刈りの効き具合を表示する。"""
    N = inst.N
    unreachable = [u for u in range(1, N) if b.lo[u] > b.hi[u]]
    if unreachable:
        print(f"WARNING: 時間枠だけで到達不能な顧客があります: {unreachable}")

    empty_pos = [i for i in range(1, N) if not b.allowed[i]]
    unplaceable = [u for u in range(1, N)
                   if not any(u in b.allowed[i] for i in range(1, N))]
    if empty_pos or unplaceable:
        print(f"WARNING: 枝刈りで空になった位置={empty_pos} "
              f"置けない顧客={unplaceable}")

    kept = sum(len(b.allowed[i]) for i in range(N))
    print(f"N={N}  x vars = {N * N} -> {kept} "
          f"(枝刈りで {N * N - kept} 個を 0 に固定)")
