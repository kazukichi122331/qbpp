import pyqbpp as qbpp
from datetime import datetime
from travel_time import travel_time
from tsptw_plot import plot_tour

def make_tour(sol):
    tour = [0]  # depotから開始

    current = 0

    for i in range(1, N + 2):

        found = False

        for v in range(N + 1):

            if current == v:
                continue

            if sol(x[current][v][i]) == 1:
                tour.append(v)
                current = v
                found = True
                break

        if not found:
            raise ValueError(
                f"position {i} の遷移が見つかりません"
            )

    return tour

time_nodes = [
    (0, 0, 0, 100), #デポ
    (2, 0, 0, 20),   #都市1
    (3, 1, 0, 20),   #都市2
    (4, 0, 0, 20),   #都市3
    (5, 5, 0, 20),   #都市4
    (3, 4, 0, 20),  #都市5
    (2, 4, 0, 4),  #都市6
    (0, 5, 0, 6),  #都市7
    (0, 3, 0, 20),  #都市8
    (1, 2, 0, 2),  #都市9
]

nodes = time_nodes #(x座標, y座標, 訪問時間の開始, 訪問時間の終了)
N = len(nodes)-1 # len(nodes): デポ1箇所 + 顧客N箇所
TIME = 30.0
#締め切りの最大値
K = max(nodes[v][3] for v in range(1, N + 1))

#u->vの移動時間
c = []
for u in range(N+1):
    c.append([travel_time(u, v, nodes) for v in range(N+1)])

#x[u][v][i]=1: 顧客uと顧客vがi-1 -> iの順で連続して現れる
#u,v ∈ {0, ..., N} なので N+1個
#i ∈ {1, ..., N+1} なので N+2個にしてt=0は使わない
x = qbpp.var("x", shape=(N+1,N+1,N+2)) 

#t[k][i]=1: ツアー位置iのtime marginがk (到着時にどれくらい余裕があるか)
#k = 10なら、10余裕をもって到着した
t = qbpp.var("t", shape=(K+1,N+1))

#ツアーのi番目にいる顧客の到着時刻
a = {}
for i in range(1, N + 1):
    arrival_i = qbpp.sum([
        x[0][v][1] * c[0][v]
        for v in range(1, N + 1)
    ])

    for d in range(2, i + 1):
        arrival_i += qbpp.sum([
            x[u][v][d] * c[u][v]
            for u in range(1, N + 1)
            for v in range(1, N + 1)
            if u != v
        ])

    a[i] = arrival_i

#訪問時間の終了
l = {}
# 位置1はデポ0から顧客vへの遷移
l[1] = qbpp.sum([
    x[0][v][1] * nodes[v][3]
    for v in range(1, N + 1)
])
# 位置2,...,N
for i in range(2, N + 1):
    l[i] = qbpp.sum([
        x[u][v][i] * nodes[v][3]
        for u in range(1, N + 1)
        for v in range(1, N + 1)
        if u != v
    ])

#各ツアー位置で遷移が一つ(一つのiで選べるu,vは一つ)
i_constraint = 0
for i in range(1, N+2):
    sum_uv = 0
    for u in range(N+1):
        for v in range(N+1):
            if u!=v:
                sum_uv += x[u][v][i]
    i_constraint += (sum_uv == 1)

#i=1でデポから出発し、i=N+1でデポに戻ってくる
sum_0u = 0
sum_u0 = 0
for u in range(1, N+1):
    sum_0u += x[0][u][1]
    sum_u0 += x[u][0][N+1]
depo_constraint = (sum_0u == 1) + (sum_u0 == 1)

#各都市からは一度しか出発できない(一つのuで選べるv,iは一つ)
u_constraint = 0
for u in range(1, N+1):
    sum_vi = 0
    for v in range(N+1):
        if u != v:
            for i in range(2, N+2):
                sum_vi += x[u][v][i]
    u_constraint += (sum_vi == 1)

#各都市には一度しか訪問できない(一つのvで選べるu,iは一つ)
v_constraint = 0
for v in range(1, N+1):
    sum_ui = 0
    for u in range(N+1):
        if u != v:
            for i in range(1, N+1):
                sum_ui += x[u][v][i]
    v_constraint += (sum_ui == 1)

#部分巡回路除去制約 i:u->v i+1:v->w i番目にvに来た辺の数とi+1番目にvを出た辺の数が一致する
flow_constraint = 0
for i in range(1, N+1):
    for v in range(N+1):
        inflow_sum = 0
        outflow_sum = 0
        for u in range(N+1):
            if u != v:
                inflow_sum += x[u][v][i]
        for w in range(N+1):
            if v != w:
                outflow_sum += x[v][w][i+1]
        flow_constraint += (inflow_sum - outflow_sum == 0)

tour_P = 500
tour_constraints = (
    i_constraint
    + depo_constraint
    + u_constraint
    + v_constraint
    + flow_constraint
)

#time margin制約 各位置で余裕時間は一つ
k_constraint = 0
for i in range(1, N+1):
    sum_k = 0
    for k in range(0, K+1):
        sum_k += t[k][i]
    k_constraint += (sum_k == 1)

#余裕時間を考え (余裕時間 >= 0)なら時間内であるという制約
time_margin_constraint = 0
for i in range(1, N+1):
    sum_tm = 0
    for k in range(0, K+1):
        sum_tm += k*t[k][i]
    time_margin_constraint += (a[i] + sum_tm - l[i] == 0)

tw_P = 30
tw_constraints = (
    10*k_constraint
    + time_margin_constraint
)

#移動コストの最小化
objective = 0
for i in range(1, N+2):
    for u in range(N+1):
        for v in range(N+1):
            objective += x[u][v][i]*c[u][v]

f = objective + qbpp.cons(tour_P*tour_constraints + tw_P*tw_constraints)
f = qbpp.simplify_as_binary(f)

ml = {}
ml.update({x[u][u][i]: 0 for u in range(N+1) for i in range(1, N+2)})#自己ループ禁止
ml.update({x[u][v][1]: 0 for u in range(1, N+1) for v in range(N+1)})#i=1ならばu=0なのでそれ以外は禁止
ml.update({x[u][v][N+1]: 0 for u in range(N+1) for v in range(1, N+1)})#i=N+1ならばv=0なのでそれ以外は禁止
ml.update({x[u][0][i]: 0 for u in range(1, N+1) for i in range(1, N+1)})#デポに戻れるのはi=N+1のみ
ml.update({x[0][v][i]: 0 for v in range(1, N+1) for i in range(2, N+2)})#デポから出るのはi=1のみ

g = qbpp.replace(f, ml)
g = qbpp.simplify_as_binary(g)

solver =qbpp.ABS3Solver(g)
sol = solver.search(time_limit=TIME)

print("energy = ", sol(g))
print("objective = ", sol(objective))
print("constraint = ", g.cons(sol))
print("i_constraint = ", sol(i_constraint))
print("depo_constraint = ", sol(depo_constraint))
print("u_constraint = ", sol(u_constraint))
print("v_constraint = ", sol(v_constraint))
print("k_constraint = ", sol(k_constraint))
print("time_margin_constraint = ", sol(time_margin_constraint))
print("K = ", K)

tour = make_tour(sol)
print(tour)

filename = "tsptw_" + datetime.now().strftime("%m%d%H%M")
plot_nodes = [(x, y) for x, y, _, _ in time_nodes]
arrival_times = [0]*(N+1)
due_times = [nodes[v][3] for v in range(N+1)]
for i in range(1, N+1):
    for u in range(N+1):
        for v in range(N+1):
            if sol(x[u][v][i]) == 1:
                arrival_times[v] = sol(a[i])
                
plot_tour(
    plot_nodes,
    tour,
    arrival_times,
    due_times,
    c,
    filename
)
