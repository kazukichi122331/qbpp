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

import pyqbpp as qbpp
from datetime import datetime
try:                                        # python -m src.time_tsptw_travel
    from src.dist_matrix import N, c, L, E
    from src.plot_tsptw import plot_tour, recover_coordinates
except ImportError:                         # python src/time_tsptw_travel.py
    from dist_matrix import N, c, L, E
    from plot_tsptw import plot_tour, recover_coordinates

# 既定は従来どおり 60 秒。ベンチマークでは引数か TSPTW_TIME で上書きする。
TIME = float(sys.argv[1]) if len(sys.argv) > 1 else float(os.environ.get("TSPTW_TIME", 60.0))
PLOT = os.environ.get("TSPTW_PLOT", "1") != "0"
PLOT_MAX_N = 60        # recover_coordinates() は N が大きいと非常に重い

s = [0] * N                 # Dumas はサービス時間なし
DEPOT_L = L[0]
RET = N
CUST = list(range(1, N))

# ---------------- 1. 到着時刻下界の前処理（不動点） ----------------
arr = {v: c[0][v] for v in CUST}
must_before = {v: [u for u in CUST if u != v and L[u] < E[v]] for v in CUST}
for _ in range(N + 5):
    changed = False
    for v in CUST:
        lb = c[0][v]
        for u in must_before[v]:
            lb = max(lb, max(E[u], arr[u]) + s[u] + c[u][v])
        if lb > arr[v]:
            arr[v] = lb
            changed = True
    if not changed:
        break

# ---------------- 2. 定義域 ----------------
xlo = {v: max(E[v], arr[v]) for v in CUST}
xhi = {v: min(L[v], DEPOT_L - s[v] - c[v][0]) for v in CUST}
xlo[RET] = max(xlo[v] + s[v] + c[v][0] for v in CUST)
xhi[RET] = DEPOT_L
s.append(0)

# b は「最早開始での待機区間」= [arrival, E_v) にしか現れない
blo = {v: arr[v] for v in CUST}
bhi = {v: E[v] - 1 for v in CUST}

NODES = CUST + [RET]


def gap(u, v):
    """u に居た時刻から v に居られる時刻までの最小差。"""
    if u == RET:
        return qbpp.inf              # 帰着より後には何も無い
    if v == RET:
        return s[u] + c[u][0]
    return max(s[u] + c[u][v], 1)


# ---------------- 3. 変数 ----------------
x = {}
for v in NODES:
    for t in range(xlo[v], xhi[v] + 1):
        x[t, v] = qbpp.var(f"x_{t}_{v}")
b = {}
for v in CUST:
    for t in range(blo[v], bhi[v] + 1):
        b[t, v] = qbpp.var(f"b_{t}_{v}")
print(f"N={N}  x vars = {len(x)}  b vars = {len(b)}  total = {len(x)+len(b)}")

# ---------------- 4. 制約A: 各頂点ちょうど1回 ----------------
# RET を落とすと makespan=0 で目的が一気に下がるので、顧客とは重みを分ける
once_cust = qbpp.expr()
for v in CUST:
    once_cust += (qbpp.sum(x[t, v] for t in range(xlo[v], xhi[v] + 1)) == 1)
once_ret = (qbpp.sum(x[t, RET] for t in range(xlo[RET], xhi[RET] + 1)) == 1)
once_constraint = once_cust + once_ret

# ---------------- 5. 制約B: 距離 + 前後関係（x と b の全組合せ） ----------------
n_terms = 0


def add_conflicts(A, Alo, Ahi, B, Blo, Bhi):
    """A に居る時刻 t と B に居る時刻 t' が t <= t' < t+gap(u,v) なら両立しない。"""
    global n_terms, conflict_constraint
    for u in NODES:
        if u not in Alo:
            continue
        for v in NODES:
            if u == v or v not in Blo:
                continue
            d = gap(u, v)
            for t in range(Alo[u], Ahi[u] + 1):
                a = max(t, Blo[v])
                z = Bhi[v] if d is qbpp.inf else min(t + d - 1, Bhi[v])
                for tp in range(a, z + 1):
                    conflict_constraint += A[t, u] * B[tp, v]
                    n_terms += 1


conflict_constraint = qbpp.expr()
add_conflicts(x, xlo, xhi, x, xlo, xhi)   # 訪問 -> 訪問
add_conflicts(b, blo, bhi, x, xlo, xhi)   # 待機 -> 訪問
add_conflicts(x, xlo, xhi, b, blo, bhi)   # 訪問 -> 待機
add_conflicts(b, blo, bhi, b, blo, bhi)   # 待機 -> 待機

# 同一頂点: 待機は自分のサービス開始より真に前
for v in CUST:
    for t in range(blo[v], bhi[v] + 1):
        for tp in range(xlo[v], min(t, xhi[v]) + 1):
            conflict_constraint += b[t, v] * x[tp, v]
            n_terms += 1

# 待機の連続性: b[t][v]=1 なら t+1 も v に居るか、t+1 に v のサービスが始まる。
# これが無いと「別の頂点への移動中に v を通過した」だけで sum(b) を稼げてしまい
# （通過は待機ではないので）総移動時間が過小評価される。
contiguity_constraint = qbpp.expr()
for v in CUST:
    for t in range(blo[v], bhi[v] + 1):
        nxt = qbpp.expr()
        if (t + 1, v) in b:
            nxt += b[t + 1, v]
        if (t + 1, v) in x:
            nxt += x[t + 1, v]
        contiguity_constraint += b[t, v] * (1 - nxt)
print(f"conflict terms = {n_terms}")

# ---------------- 6. 目的関数: 総移動時間 ----------------
makespan = qbpp.sum(t * x[t, RET] for t in range(xlo[RET], xhi[RET] + 1))
total_wait = qbpp.sum(b[t, v] for v in CUST for t in range(blo[v], bhi[v] + 1))
objective = makespan - total_wait          # = 総移動時間

# ---------------- 7. QUBO 化 ----------------
# 重みは「違反1単位で得られる目的関数の改善」を上回れば十分。
#   once   : 頂点を1つ落として節約できる travel は c[pred][v]+c[v][succ] <= 2*max_c
#   conflict: 1違反でスケジュールを詰められる量は gap <= max_c
#   contiguity: sum(b) が +1 されるだけなので 2 で足りる
# DEPOT_L+1 でも安全だが過大で、ペナルティ壁が急峻になり局所解から抜けにくくなる。
MAXC = max(max(row) for row in c)
# RET を落とすと makespan が 0 になり目的が最大 DEPOT_L 下がるので、ここだけは大きい重みが必要
P_RET = DEPOT_L + 1
# 顧客を1つ落として節約できる travel は c[pred][v]+c[v][succ] <= 2*max_c
P_CUST = 4 * MAXC + 1
# 1違反でスケジュールを詰められる量は gap <= max_c
P_CONF = 2 * MAXC + 1
# sum(b) が +1 されるだけ
P_CONT = 2 * MAXC + 1
f = (objective
     + P_RET * qbpp.cons(once_ret)
     + P_CUST * qbpp.cons(once_cust)
     + P_CONF * qbpp.cons(conflict_constraint)
     + P_CONT * qbpp.cons(contiguity_constraint))
print(f"penalty: RET={P_RET} CUST={P_CUST} CONF={P_CONF} CONT={P_CONT}")
f = qbpp.simplify_as_binary(f)

solver = qbpp.ABS3Solver(f)
print(f"solve now...({TIME} sec)")
sol = solver.search(time_limit=TIME)

print(f"\n----------result({TIME} sec)----------")
print("energy           =", sol(f))
print("objective(travel)=", sol(objective))
print("makespan         =", sol(makespan))
print("total_wait       =", sol(total_wait))
print("once_constraint  =", sol(once_constraint))
print("conflict_constr  =", sol(conflict_constraint))
print("contiguity       =", sol(contiguity_constraint))

# ---------------- 8. 解の展開 ----------------
start = {}
for v in NODES:
    ts = [t for t in range(xlo[v], xhi[v] + 1) if sol(x[t, v]) == 1]
    if len(ts) != 1:
        print(f"node {v}: {len(ts)} visits VIOLATION!")
    if ts:
        start[v] = ts[0]

seq = sorted((t, v) for v, t in start.items() if v != RET)
tour = [0] + [v for _, v in seq] + [0]

arrival_times = [L[v] + 1 for v in range(N)]
wait_times = [0] * N

now, travel = 0, 0
prev = 0
for t, v in seq:
    arrive = now + c[prev][v]
    arrival_times[v] = arrive
    wait_times[v] = t - arrive
    travel += c[prev][v]
    flag = "" if (E[v] <= t <= L[v] and t >= arrive) else "  VIOLATION!"
    print(f"  v={v:3d} start={t:4d} arrive={arrive:4d} wait={t-arrive:4d} [{E[v]:4d},{L[v]:4d}]{flag}")
    now, prev = t + s[v], v
travel += c[prev][0]
ret = now + c[prev][0]
arrival_times[0] = ret
print(f"  return={ret:4d} (RET var = {start.get(RET)})")
print("tour        =", tour)
print("travel time =", travel, " <- 実測（objective と一致すべき）")
print("var_count   =", sol.info["var_count"])
print("term_count  =", sol.info["term_count"])

# ---------------- 9. 描画 ----------------
if PLOT and N <= PLOT_MAX_N:
    filename = "tsptw_travel_" + datetime.now().strftime("%m%d%H%M")
    nodes = recover_coordinates(c)
    plot_tour(nodes, tour, E, wait_times, arrival_times, L, c, filename)
    print("saved       =", f"results/{filename}.png")
elif PLOT:
    print(f"skip plot   = N={N} > PLOT_MAX_N={PLOT_MAX_N} "
          "(recover_coordinates が重いため)")
