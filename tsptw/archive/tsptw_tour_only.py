import pyqbpp as qbpp
from tsptw.archive.travel_time import travel_time

time_nodes = [
    (0, 0, 0, 100),
    (2, 0, 0, 100),
    (4, 0, 0, 100),
    (0, 3, 0, 100),
    (0, 5, 0, 100),
    (1, 2, 0, 100),
    (3, 4, 0, 100),
    (5, 5, 0, 100),
    (3, 1, 0, 100),
    (2, 4, 0, 100),
]

nodes = time_nodes #(x座標, y座標, 訪問時間の開始, 訪問時間の終了)
N = len(nodes)-1 # len(nodes): デポ1箇所 + 顧客N箇所

#u->vの移動時間
c = []
for u in range(N+1):
    c.append([travel_time(u, v, nodes) for v in range(N+1)])

#x[u][v][i]=1: 顧客uと顧客vがi-1 -> iの順で連続して現れる
#u,v ∈ {0, ..., N} なので N+1個
#i ∈ {1, ..., N+1} なので N+2個にしてt=0は使わない
x = qbpp.var("x", shape=(N+1,N+1,N+2)) 

#移動コストの最小化
objective = 0
for i in range(1, N+2):
    for u in range(N+1):
        for v in range(N+1):
            objective += x[u][v][i]*c[u][v]

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

tour_P = 1000
tour_constraints = (
    i_constraint
    + depo_constraint
    + u_constraint
    + v_constraint
    + flow_constraint
)

f = objective + qbpp.cons(tour_P*tour_constraints)
f.simplify_as_binary()

ml = {x[u][u][i]: 0 for u in range(N+1) for i in range(1, N+2)}

g = qbpp.replace(f, ml)
g.simplify_as_binary()

solver =qbpp.ABS3Solver(g)
sol = solver.search(time_limit=10.0)

print("energy = ", sol(g))
print("objective = ", sol(objective))
print("constraint = ", g.cons(sol))
print("i_constraint = ", sol(i_constraint))
print("depo_constraint = ", sol(depo_constraint))
print("u_constraint = ", sol(u_constraint))
print("v_constraint = ", sol(v_constraint))
print("flow_constraint = ", sol(flow_constraint))
for i in range(1, N+2):
    print(f"visit {i}: ", end="")
    for u in range(N+1):
        for v in range(N+1):
            if(sol(x[u][v][i]) == 1):
                print(f"{u}->{v} ", end="")
    print("")