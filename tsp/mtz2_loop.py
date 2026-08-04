from datetime import datetime
import pyqbpp as qbpp
from nodes import distance, ran_nodes
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

nodes = ran_nodes
N = len(nodes) - 1
TIME = 10.0
LOOP = 10

x = qbpp.var("x", shape=(N+1, N+1))
u = qbpp.var("u", shape=N+1, between=(1, N))

row_constraint = qbpp.expr()
for i in range(N+1):
    row_sum = 0
    for j in range(N+1):
        if i!=j:
            row_sum += x[i][j]
    row_constraint += (row_sum == 1)

col_constraint = qbpp.expr()
for j in range(N+1):
    col_sum = 0
    for i in range(N+1):
        if i!=j:
            col_sum += x[i][j]
    col_constraint += (col_sum == 1)

constraint1 = qbpp.expr()
for i in range(1, N+1):
    for j in range(1, N+1):
        if i!=j:
            constraint1 += (u[i]*x[i][j] - (u[j]-1)*x[i][j] == 0)

constraint2 = qbpp.expr()
for j in range(1, N+1):
    constraint2 += (u[j]*x[0][j] - x[0][j] == 0)

constraint3 = qbpp.expr()
#for i in range(1, N+1):
#    constraint3 += (u[i]*x[i][0] - N*x[i][0] == 0)

objective = qbpp.expr()
for i in range(N+1):
    for j in range(N+1):
        objective += x[i][j]*distance(i, j, nodes)

constraint = (
    row_constraint
    + col_constraint
    + constraint1
    + constraint2
    + constraint3
)

P = 1000
f = objective + P * qbpp.cons(constraint)
f = qbpp.simplify_as_binary(f)

ml = {x[i][i]: 0 for i in range(N+1)}

g = qbpp.replace(f, ml)
g = qbpp.simplify_as_binary(g)

solver = qbpp.ABS3Solver(g)

saved_energy = []
saved_violation = []
for loop in range(LOOP):
    sol = solver.search(time_limit=TIME)
    energy = sol(g)
    violation = g.cons(sol)
    saved_energy.append(energy)
    saved_violation.append(violation)
    print("energy = ", energy)
    print("violated constraints =", violation)
    tour = make_tour(sol)
    print(tour)
    filename = "mtz2_" + datetime.now().strftime("%m%d%H%M%S")
    plot_tour(nodes, tour, filename)
    plot_tour(nodes, tour, "mtz2")

print(energy)
print(violation)