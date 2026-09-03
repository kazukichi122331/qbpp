"""
時間展開型 (time-indexed) TSPTW QUBO 定式化。

各頂点 v を「離散時刻ごとに独立した別ノード」に分割し、
  x[t][v] = 1  <=>  頂点 v のサービスを時刻 t に開始する
とする。訪問順インデックス i は使わない（順序は時刻から導出される）。

  制約A: 各 v はちょうど 1 つの t を持つ            -> 次数 2
  制約B: t <= t' < t + s[u] + c[u][v] なる (t,u),(t',v) を禁止  -> 次数 2
         ここに「距離」と「前後関係」が同時に入る
  時間窓: 変数の定義域そのもの                      -> ペナルティ不要

  目的:  depot への帰着時刻（makespan）を最小化
"""
import pyqbpp as qbpp
from datetime import datetime
from dist_matrix import N, c, L, E
from tsptw_plot import plot_tour, recover_coordinates

TIME = 60.0

s = [0] * N                 # Dumas はサービス時間なし
DEPOT_L = L[0]              # 帰着期限
RET = N                     # depot 帰着を表す「もう一つのノード」

# ---------------- 1. 時刻ドメインの枝刈り ----------------
# lo[v]: v のサービス開始可能な最早時刻
#        三角不等式より、誰よりも早く v に着けるのは depot から直行した場合
# hi[v]: そこから depot に帰着できる最遅時刻
lo = [0] * (N + 1)
hi = [0] * (N + 1)
for v in range(1, N):
    lo[v] = max(E[v], c[0][v])
    hi[v] = min(L[v], DEPOT_L - s[v] - c[v][0])
lo[RET] = max(lo[v] + s[v] + c[v][0] for v in range(1, N))
hi[RET] = DEPOT_L
s.append(0)

NODES = list(range(1, N)) + [RET]


def gap(u, v):
    """u のサービス開始から v のサービス開始までに必要な最小時間差。"""
    if u == RET:
        return qbpp.inf          # 帰着より後には何も来ない
    if v == RET:
        return s[u] + c[u][0]
    return max(s[u] + c[u][v], 1)   # c[u][v]==0 の同一地点でも同時刻は禁止


# ---------------- 2. 変数（存在するものだけ生成） ----------------
x = {}
for v in NODES:
    for t in range(lo[v], hi[v] + 1):
        x[t, v] = qbpp.var(f"x_{t}_{v}")
print(f"N={N}  x vars = {len(x)}  (order-based なら {(N-1)**2})")

# ---------------- 3. 制約A: 各頂点ちょうど 1 回 ----------------
# 「重複訪問にペナルティ」だけでは全ゼロ解が最適になるので等式にする
once_constraint = qbpp.expr()
for v in NODES:
    once_constraint += (qbpp.sum(x[t, v] for t in range(lo[v], hi[v] + 1)) == 1)

# ---------------- 4. 制約B: 距離 + 前後関係 ----------------
# (t,u) と (t',v) が t <= t' < t + gap(u,v) なら両立しない。
#  - t と t' の非対称性が「前後関係」を表す（順序変数は不要）
#  - gap に c[u][v] が入る ->「距離」は禁止窓の幅として効く
#  - t'==t のケースが「同時刻に 2 頂点」を禁止する
# 三角不等式が成り立つので、隣接ペアだけでなく全ペアに課しても
# 実行可能ツアーを排除しない（かつ隣接ペアの充足から全体の実行可能性が従う）。
conflict_constraint = qbpp.expr()
n_terms = 0
for u in NODES:
    for v in NODES:
        if u == v:
            continue
        d = gap(u, v)
        for t in range(lo[u], hi[u] + 1):
            a = max(t, lo[v])
            b = hi[v] if d is qbpp.inf else min(t + d - 1, hi[v])
            for tp in range(a, b + 1):
                conflict_constraint += x[t, u] * x[tp, v]
                n_terms += 1
print(f"conflict terms = {n_terms}")

# ---------------- 5. 目的関数: 帰着時刻 ----------------
# makespan = 総移動時間 + 総待ち時間（サービス時間は定数）
# 総移動時間そのものは x[t][v] の 2 次式では書けない（後述）
objective = qbpp.sum(t * x[t, RET] for t in range(lo[RET], hi[RET] + 1))

# ---------------- 6. QUBO 化 ----------------
# 制約違反は必ず整数 >= 1、目的関数は O(DEPOT_L) なので
# ペナルティは DEPOT_L より少し大きいだけでよい（order-based の 50000 は不要）
ONCE_P = DEPOT_L + 1
CONF_P = DEPOT_L + 1
f = objective + ONCE_P * qbpp.cons(once_constraint) + CONF_P * qbpp.cons(conflict_constraint)
f = qbpp.simplify_as_binary(f)

solver = qbpp.ABS3Solver(f)
print(f"solve now...({TIME} sec)")
sol = solver.search(time_limit=TIME)

print(f"\n----------result({TIME} sec)----------")
print("energy           =", sol(f))
print("objective        =", sol(objective))
print("once_constraint  =", sol(once_constraint))
print("conflict_constr  =", sol(conflict_constraint))

# ---------------- 7. 解の展開 ----------------
start = {}
for v in NODES:
    ts = [t for t in range(lo[v], hi[v] + 1) if sol(x[t, v]) == 1]
    if len(ts) != 1:
        print(f"node {v}: {len(ts)} visits VIOLATION!")
    if ts:
        start[v] = ts[0]

seq = sorted((t, v) for v, t in start.items() if v != RET)
tour = [0] + [v for _, v in seq] + [0]

# 描画用（頂点番号でインデックス）。未訪問頂点は目立つ値のままにしておく
arrival_times = [0] * N
wait_times = [0] * N

now, travel = 0, 0
prev = 0
for t, v in seq:
    arrive = now + c[prev][v]
    wait = t - arrive
    arrival_times[v] = arrive
    wait_times[v] = wait
    travel += c[prev][v]
    flag = "" if (E[v] <= t <= L[v] and wait >= 0) else "  VIOLATION!"
    print(f"  v={v:3d} start={t:4d} arrive={arrive:4d} wait={wait:4d} [{E[v]:4d},{L[v]:4d}]{flag}")
    now, prev = t + s[v], v
travel += c[prev][0]
ret = now + c[prev][0]
arrival_times[0] = ret          # depot は帰着時刻を表示
print(f"  return={ret:4d} (RET var = {start.get(RET)})")
print("tour        =", tour)
print("travel time =", travel)
print("var_count   =", sol.info["var_count"])
print("term_count  =", sol.info["term_count"])

# ---------------- 8. 描画 ----------------
filename = "tsptw_time_" + datetime.now().strftime("%m%d%H%M")
nodes = recover_coordinates(c)
plot_tour(
    nodes,
    tour,
    E,
    wait_times,
    arrival_times,
    L,
    c,
    filename
)
print("saved       =", f"results/{filename}.png")
