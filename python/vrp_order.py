#目的関数が四次になって項数爆発(項数数280万)が起こる
import pyqbpp as qbpp
from nodes import nodes, distance 
from plot_tour import plot_tour

N = len(nodes)-2
V = 3

a = qbpp.var("a", shape=(V, N, N))

row_constraint = qbpp.sum(qbpp.vector_sum(a) == 1)

column_sum = [0 for _ in range(N - 1)]
for v in range(V):
    for t in range(N):
        for i in range(1, N):
            column_sum[i - 1] += a[v][t][i]
column_constraint = 0
for i in range(N - 1):
    column_constraint += (column_sum[i] == 1)

consecutive_constraint = 0
for v in range(V):
    for t in range(1, N - 1):
        consecutive_constraint += a[v][t][0] * (1 - a[v][t + 1][0])

objective = 0
for v in range(V):
    for t in range(N):
        next_t = (t + 1) % N
        for i in range(N):
            x1, y1 = nodes[i][0], nodes[i][1]
            for j in range(N):
                x2, y2 = nodes[j][0], nodes[j][1]
                dist = distance(i, j, nodes)
                objective += dist * a[v][t][i] * a[v][next_t][j]

f = objective + 10000 * (row_constraint + column_constraint +
                          consecutive_constraint)

ml = {a[v][0][0]: 1 for v in range(V)}
ml.update({a[v][0][i]: 0 for v in range(V) for i in range(1, N)})

g = qbpp.replace(f, ml)
f.simplify_as_binary()
g.simplify_as_binary()
solver = qbpp.EasySolver(g)

sol = solver.search()

full_sol = qbpp.Sol(f).set(sol, ml)

print(f"row_constraint = {full_sol(row_constraint)}")
print(f"column_constraint = {full_sol(column_constraint)}")
print(f"consecutive_constraint = {full_sol(consecutive_constraint)}")
print(f"objective = {full_sol(objective)}")

vehicle_load = [0 for _ in range(V)]
for v in range(V):
    load = full_sol(vehicle_load[v])
    for t in range(1, N):
        for i in range(1, N):
            if full_sol(a[v][t][i]) == 1:
                route += f"-> {i}({nodes[i][2]}) "
                break
    route += "-> 0"
    print(route)