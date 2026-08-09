from datetime import datetime

import pyqbpp as qbpp
from time_nodes import time_nodes_10
from travel_time import travel_time
from tsptw_plot import plot_tour

TIME = 10.0 #ソルバーの実行時間

nodes = time_nodes_10 #デポ+顧客10人
N = len(nodes) - 1

L = [] #顧客番号順の訪問締切時刻
E = [] #顧客番号順の訪問開始時刻
for _,_,e,l in nodes:
    L.append(l)
    E.append(e)

#u->vの移動時間
c = []
for u in range(N+1):
    c.append([travel_time(u, v, nodes) for v in range(N+1)])

x = qbpp.var("x", shape=(N+1,N+1)) #x[i][u]=1: i番目に顧客uに訪れる

l = [] #顧客訪問順の締切時刻
for i in range(N+1):
    expr = qbpp.expr()
    for u in range(N+1):
        expr += L[u]*x[i][u]
    l.append(expr)

e = [] #顧客訪問順の訪問時刻
for i in range(N+1):
    expr = qbpp.expr()
    for u in range(N+1):
        expr += E[u]*x[i][u]
    e.append(expr)

a = {}
for i in range(N+1):
    arrival_i = qbpp.expr()
    for j in range(i):
        next_j = j+1
        for u in range(N+1):
            for v in range(N+1):
                arrival_i += x[j][u]*x[next_j][v]*travel_time(u, v, nodes)
    a[i] = arrival_i
    
row_constraint = qbpp.sum(qbpp.vector_sum(x, axis=0) == 1) 
col_constraint = qbpp.sum(qbpp.vector_sum(x, axis=1) == 1)

time_constraint = qbpp.expr()
for i in range(N+1):
    time_constraint += (a[i] - l[i] <= 0)
    time_constraint += (e[i] - a[i] <= 0)

objective = qbpp.expr()
for i in range(N+1):
    next_i = (i+1)%(N+1)
    for u in range(N+1):
        for v in range(N+1):
            objective += x[i][u]*x[next_i][v]*c[u][v]

P = 1000
f = objective + P*qbpp.cons(row_constraint + col_constraint + time_constraint)
f = qbpp.simplify_as_binary(f)

ml = {x[0][0]: 1}
ml = {x[N][0]: 1}
ml.update({x[i][0]: 0 for i in range(1, N)})
ml.update({x[0][i]: 0 for i in range(1, N+1)})

g = qbpp.replace(f, ml)
g = qbpp.simplify_as_binary(g)

solver = qbpp.ABS3Solver(g)
sol = solver.search(time_limit=TIME)
full_sol = qbpp.Sol(f).set(sol, ml)

print("エネルギー値：", full_sol(f))
print("違反した制約の本数：", f.cons(full_sol))

tour = []
for i in range(N+1):
    for u in range(N+1):
        if full_sol(x[i][u]) == 1:
            tour.append(u)
            break
tour.append(0)
print(f"Tour: {tour}")

filename = "tsptw_" + datetime.now().strftime("%m%d%H%M")
plot_nodes = [(x, y) for x, y, _, _ in nodes]
arrival_times = [0]*(N+1)
due_times = [nodes[v][3] for v in range(N+1)]
for i in range(N+1):
    for u in range(N+1):
            if full_sol(x[i][u]) == 1:
                arrival_times[u] = full_sol(a[i])
                break

plot_tour(
    plot_nodes,
    tour,
    arrival_times,
    due_times,
    c,
    filename
)