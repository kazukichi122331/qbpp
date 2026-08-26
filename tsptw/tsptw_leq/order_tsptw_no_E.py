import pyqbpp as qbpp
from datetime import datetime
from travel_time import travel_time
from tsptw_plot_no_e import plot_tour
from time_nodes import time_nodes_10, time_nodes_15, time_nodes_20, time_nodes_30


TIME = 10.0
LOOP = 10

nodes = time_nodes_20
N = len(nodes) - 1

x = qbpp.var("x", shape=(N+1,N+1))

c = [[travel_time(u, v, nodes) for v in range(N+1)] for u in range(N+1)]
a = [0] #a[i]: i番目の顧客までの移動時間
for i in range(1, N+1):
    dist = qbpp.sum(x[i-1][u]*x[i][v]*c[u][v] for u in range(N+1) for v in range(N+1))
    next_a = a[i-1] + dist
    a.append(next_a)

l = [] #l[i]: i番目の顧客の締切時刻
for i in range(N+1):
    l_i = qbpp.sum(
        x[i][u] * nodes[u][3]
        for u in range(N+1)
    )
    l.append(l_i)
    
row_constraint = qbpp.sum(qbpp.vector_sum(x, axis=0) == 1)
col_constraint = qbpp.sum(qbpp.vector_sum(x, axis=1) == 1)

time_constraint = qbpp.expr()
for i in range(N+1):
    time_constraint += qbpp.cons(a[i] - l[i] <= 0)


objective = qbpp.expr()
for i in range(N+1):
    next_i = (i+1)%(N+1)
    for u in range(N+1):
        for v in range(N+1):
            objective += x[i][u]*x[next_i][v]*c[u][v]

P = 1000
f = objective + P*qbpp.cons(row_constraint + col_constraint) + time_constraint*P
f.simplify_as_binary()

ml = {}
ml.update({x[0][0]: 1})
ml.update({x[0][u]: 0 for u in range(1, N+1)})
ml.update({x[i][0]: 0 for i in range(1, N+1)})

g = qbpp.replace(f, ml)
g.simplify_as_binary()

solver = qbpp.ABS3Solver(g)
sol = solver.search(time_limit=TIME)

full_sol = qbpp.Sol(f).set(sol, ml)

print("energy = ", full_sol(f))
print("constarint = ", f.cons(full_sol))

plot_nodes = [(x, y) for x, y, _, _ in nodes]

tour = []
for i in range(N+1):
    for u in range(N+1):
        if full_sol(x[i][u]) == 1:
            tour.append(u)
if len(tour) == N+1:
    arrival_times = [0]*(N+1)
    for i in range(N+1):
        v = tour[i]
        arrival_times[v] = full_sol(a[i])
    due_times = [nodes[v][3] for v in range(N+1)]
    filename = "tsptw_no_E_" + datetime.now().strftime("%m%d%H%M")

    tour.append(0)

    plot_tour(
        plot_nodes,
        tour,
        arrival_times,
        due_times,
        c,
        filename
    )
    print("tour: ", tour)
    print("a_tm: ", arrival_times)
    print("l_tm: ", due_times)
else:
    print("ツアー制約違反")
    for i in range(N+1):
        visit = 0
        for u in range(N+1):
            if full_sol(x[i][u]) == 1:
                print(f"pos {i}: {u}")
                visit = 1
                break
        if visit == 0:
            print(f"pos {i}: None")
var_count = sol.info["var_count"]
term_count = sol.info["term_count"]

print("var_count = ", var_count)
print("term_count = ", term_count)