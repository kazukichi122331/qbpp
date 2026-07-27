import pyqbpp as qbpp
from nodes import travel_time #, time_nodes

time_nodes = [
    (0, 0, 0, 999),     # depot

    (10, 0, 0, 20),     # customer 1
    (20, 0, 0, 40),     # customer 2
    (30, 0, 0, 60),     # customer 3
    (40, 0, 0, 80),     # customer 4
    (50, 0, 0, 100),    # customer 5
]

nodes = time_nodes #(x座標, y座標, 訪問時間の開始, 訪問時間の終了)
N = len(nodes)-1 # len(nodes): デポ1箇所 + 顧客N箇所

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

#移動コストの最小化
objective = 0
for i in range(1, N+2):
    for u in range(N+1):
        for v in range(N+1):
            objective += x[u][v][i]*c[u][v]

#各ツアー位置で遷移が一つ(一つのiで選べるu,vは一つ)
i_constraint = 0
for i in range(1, N+2):
    sum_uv = qbpp.sum([x[u][v][i]
                       for u in range(N+1)
                       for v in range(N+1)
                       if u!=v])
    i_constraint += (sum_uv == 1)

#i=1でデポから出発し、i=N+1でデポに戻ってくる
sum_0v = qbpp.sum([x[0][v][1] for v in range(1, N+1)])
sum_u0 = qbpp.sum([x[u][0][N+1] for u in range(1, N+1)])
depo_constraint = (sum_0v == 1) + (sum_u0 == 1)

#各都市からは一度しか出発できない(一つのuで選べるv,iは一つ)
u_constraint = 0
for u in range(1, N+1):
    sum_vi = qbpp.sum([x[u][v][i]
                       for v in range(1, N+1)
                       for i in range(2, N+1)
                       if u!=v])
    u_constraint += (sum_vi == 1)

#各都市には一度しか訪問できない(一つのvで選べるu,iは一つ)
v_constraint = 0
for v in range(1, N+1):
    sum_ui = qbpp.sum([x[u][v][i]
                       for u in range(1, N+1)
                       for i in range(2, N+1)
                       if u!=v])
    v_constraint += (sum_ui == 1)

#time margin制約 各位置で余裕時間は一つ
k_constraint = 0
for i in range(1, N+1):
    sum_k = qbpp.sum([t[k][i] for k in range(0, K+1)])
    k_constraint += (sum_k == 1)

time_margin_constraint = 0
for i in range(1, N+1):
    sum_k = qbpp.sum([k*t[k][i] for k in range(0, K+1)])
    time_margin_constraint += (a[i] + sum_k - l[i] == 0)

tour_P = 1000
tour_constraints = (
    i_constraint
    + depo_constraint
    + u_constraint
    + v_constraint
)

tw_P = 10
tw_constraints = (
    k_constraint
    + time_margin_constraint
)

f = objective + qbpp.cons(tour_P*tour_constraints + tw_P*tw_constraints)
f.simplify_as_binary()

ml = {x[u][u][i]: 0 for u in range(N+1) for i in range(1, N+2)}

g = qbpp.replace(f, ml)
g.simplify_as_binary()

solver =qbpp.ABS3Solver(g)
sol = solver.search(time_limit=30.0)

print("energy = ", sol(g))
print("objective = ", sol(objective))
print("constraint = ", g.cons(sol))
print("i_constraint = ", sol(i_constraint))
print("depo_constraint = ", sol(depo_constraint))
print("u_constraint = ", sol(u_constraint))
print("v_constraint = ", sol(v_constraint))
print("k_constraint = ", sol(k_constraint))
print("time_margin_constraint = ", sol(time_margin_constraint))
print("N = ", N)
print("K = ", K)
for i in range(1, N+2):
    print(f"visit {i}: ", end="")
    for u in range(N+1):
        for v in range(N+1):
            if(sol(x[u][v][i]) == 1):
                print(f"{u}->{v} ", end="")
    print("")