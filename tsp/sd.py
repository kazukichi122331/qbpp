from datetime import datetime
import pyqbpp as qbpp
from nodes import distance, reg_nodes
from plot_tour import plot_tour

def make_tour(sol):
    tour = [0]
    current = 0
    visited = {0}

    for _ in range(N+1):
        next_city = None

        for j in range(N+1):
            if j == current:
                continue

            if round(sol(x[current][j])) == 1:
                next_city = j
                break

        if next_city is None:
            break

        tour.append(next_city)
        current = next_city

        # 実際に選択された枝によって0に戻った
        if current == 0:
            break

        if current in visited:
            break

        visited.add(current)

    return tour

nodes = reg_nodes
N = len(nodes) - 1

x = qbpp.var("x", shape=(N+1, N+1))
u = qbpp.var("u", shape=N+1, between=(1, N))
y = qbpp.var("y", shape=(N+1, N+1), between=(0, N-1))

row_constraint = 0
for i in range(N+1):
    row_sum = 0
    for j in range(N+1):
        if i!=j:
            row_sum += x[i][j]
    row_constraint += (row_sum == 1)

col_constraint = 0
for j in range(N+1):
    col_sum = 0
    for i in range(N+1):
        if i!=j:
            col_sum += x[i][j]
    col_constraint += (col_sum == 1)

constraint1 = 0
for i in range(1, N+1):
    sum_y = 0
    for j in range(1, N+1):
        if i!=j:
            sum_y += y[i][j]
    constraint1 += (sum_y + N*x[i][0] - u[i] == 0)

constraint2 = 0
for j in range(1, N+1):
    sum_y = 0
    for i in range(1, N+1):
        if i!=j:
            sum_y += y[i][j]
    constraint2 += (sum_y + 1 - u[j] == 0)

constraint3 = 0
for i in range(1, N+1):
    for j in range(1, N+1):
        if i!=j:
            constraint3 += (x[i][j] - y[i][j] <= 0)
            constraint3 += (y[i][j] - (N-1)*x[i][j] <= 0)

constraint4 = 0
for i in range(1, N+1):
    for j in range(1, N+1):
        if i!=j:
            constraint4 += (u[j] + (N-1)*x[i][j]-N*(1-x[j][i]) - y[i][j] - y[j][i] <= 0)

constraint5 = 0
for i in range(1, N+1):
    for j in range(1, N+1):
        if i!=j:
            constraint5 += (y[i][j] + y[j][i] - u[j] + (1 - x[i][j]) <= 0)

constraint6 = 0
for j in range(1, N+1):
    constraint6 += (1 + (1-x[0][j]) + (N-2)*x[j][0] - u[j] <= 0)

constraint7 = 0
for j in range(1, N+1):
    constraint7 += (u[j] - N + (N-2)*x[0][j] + (1 - x[j][0]) <= 0 )

objective = 0
for i in range(N+1):
    for j in range(N+1):
        objective += x[i][j]*distance(i, j, nodes)

constraint = (
    row_constraint
    + col_constraint
    + constraint1
    + constraint2
    + constraint3
    + constraint4
    + constraint5
    + constraint6
    + constraint7
)

P = 1000
f = objective + P * qbpp.cons(constraint)
f = qbpp.simplify_as_binary(f)

ml = {x[i][i]: 0 for i in range(N+1)}

g = qbpp.replace(f, ml)
g = qbpp.simplify_as_binary(g)

solver = qbpp.ABS3Solver(g)
sol = solver.search(time_limit=10.0)

print("energy =", sol(g))
print("total constraint penalty =", g.cons(sol))
print("objective =", sol(objective))
print("row_constraint =", sol(row_constraint))
print("col_constraint =", sol(col_constraint))
print("constraint1 =", sol(constraint1))
print("constraint2 =", sol(constraint2))
print("constraint3 =", sol(constraint3))
print("constraint4 =", sol(constraint4))
print("constraint5 =", sol(constraint5))
print("constraint6 =", sol(constraint6))
print("constraint7 =", sol(constraint7))

tour = make_tour(sol)
filename = "sd" + datetime.now().strftime("%m%d%H%M")
plot_tour(nodes, tour, filename)
plot_tour(nodes, tour, "sd")
print(tour)