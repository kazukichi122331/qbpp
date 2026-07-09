# a[v][t][i]：車両vがt番目に都市iに訪れる
import math
import pyqbpp as qbpp
from nodes import distance, n
from plot_tour import plot_order_edges

R = 100  # 半径
cx, cy = 125, 125  # 中心座標
locations = []
for i in range(n):
    theta = 2 * math.pi * i / n
    x = round(cx + R * math.cos(theta))
    y = round(cy + R * math.sin(theta))
    locations.append((x, y))

N = len(locations)
V = 2

def make_edge(sol):
    edges = []
    for v in range(V):
        for t in range(N):
            next_t = (t + 1) % N
            for i in range(N):
                for j in range(N):
                    if i==j: 
                        continue
                    if sol(a[v][t][i]) == 1 and sol(a[v][next_t][j]) == 1:
                        edges.append((i, j))
    return edges

def vehicle_distance():
    L = [0 for _ in range(V)]
    for v in range(V):
        for t in range(N):
            next_t = (t+1) % N
            for i in range(N):
                for j in range(N):
                    if i==j: 
                        continue
                    L[v] += a[v][t][i]*a[v][next_t][j]*distance(i, j, locations)
    return L

a = qbpp.var("a", shape=(V, N, N))
L = vehicle_distance()
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


objective = qbpp.sum(L)


f = objective + 10000 * (row_constraint + column_constraint +
                          consecutive_constraint)

ml = {a[v][0][0]: 1 for v in range(V)}
ml.update({a[v][0][i]: 0 for v in range(V) for i in range(1, N)})
ml.update({a[v][1][0]: 0 for v in range(V)})

g = qbpp.replace(f, ml)
f.simplify_as_binary()
g.simplify_as_binary()
solver = qbpp.ABS3Solver(g)

best_energy = 100000
best_sol = None
for loop in range(5):
    print(f"solve{loop+1}: ", end="")
    sol = solver.search(time_limit=1.0)
    solg = sol(g)
    print(f"energy={solg}")

    if solg < best_energy:
        best_energy = solg
        best_sol = sol

full_sol = qbpp.Sol(f).set(best_sol, ml)

print(f"row_constraint = {full_sol(row_constraint)}")
print(f"column_constraint = {full_sol(column_constraint)}")
print(f"consecutive_constraint = {full_sol(consecutive_constraint)}")
print(f"objective = {full_sol(objective)}")
for v in range(V):
    print(f"L{v} = {full_sol(L[v])}")
print(f"var_count: {sol.info['var_count']}")
print(f"term_count: {sol.info['term_count']}")
print("")

for v in range(V):
    route = f"Vehicle {v} : 0 "
    for t in range(1, N):
        for i in range(1, N):
            if full_sol(a[v][t][i]) == 1:
                route += f"-> {i} "
                break
    route += "-> 0"
    print(route)

edges = make_edge(full_sol)
plot_order_edges(locations, edges, "vrp_order")