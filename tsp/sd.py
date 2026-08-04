from datetime import datetime
import pyqbpp as qbpp
from nodes import distance, ran_nodes
from plot_tour import plot_tour

def make_tour(sol):
    tour = [0]
    current = 0
    visited = {0}

    for _ in range(n):
        next_city = None

        for j in range(n):
            if j == current:
                continue

            if round(sol(x[current][j])) == 1:
                next_city = j
                break

        if next_city is None:
            break

        tour.append(next_city)
        current = next_city

        if current == 0:
            break

        if current in visited:
            break

        visited.add(current)

    return tour

nodes = ran_nodes

# 論文の n
n = len(nodes)

LOOP = 1
TIME = 20.0

x = qbpp.var("x", shape=(n, n))
u = qbpp.var("u", shape=n, between=(1, n - 1))
y = qbpp.var("y", shape=(n, n), between=(0, n - 2))

row_constraint = 0

for i in range(n):
    row_sum = 0

    for j in range(n):
        if i != j:
            row_sum += x[i][j]

    row_constraint += (row_sum == 1)

col_constraint = 0

for j in range(n):
    col_sum = 0

    for i in range(n):
        if i != j:
            col_sum += x[i][j]

    col_constraint += (col_sum == 1)

constraint1 = 0

for i in range(1, n):
    sum_y = 0

    for j in range(1, n):
        if i != j:
            sum_y += y[i][j]

    constraint1 += (
        sum_y + (n - 1) * x[i][0] - u[i] == 0
    )

constraint2 = 0

for j in range(1, n):
    sum_y = 0

    for i in range(1, n):
        if i != j:
            sum_y += y[i][j]

    constraint2 += (
        sum_y + 1 - u[j] == 0
    )

constraint3 = 0

for i in range(1, n):
    for j in range(1, n):
        if i != j:
            constraint3 += (x[i][j] - y[i][j] <= 0)
            constraint3 += (y[i][j] - (n - 2) * x[i][j] <= 0)

constraint4 = 0

for i in range(1, n):
    for j in range(1, n):
        if i != j:

            constraint4 += (
                u[j]
                + (n - 2) * x[i][j]
                - (n - 1) * (1 - x[j][i])
                - y[i][j]
                - y[j][i]
                <= 0
            )

            constraint4 += (
                y[i][j]
                + y[j][i]
                - u[j]
                + (1 - x[i][j])
                <= 0
            )

constraint5 = 0

for j in range(1, n):

    constraint5 += (
        1
        + (1 - x[0][j])
        + (n - 3) * x[j][0]
        - u[j]
        <= 0
    )

    constraint5 += (
        u[j]
        - ((n - 2) - (n - 3) * x[0][j] + x[j][0])
        <= 0
    )

objective = 0

for i in range(n):
    for j in range(n):
        if i != j:
            objective += (
                x[i][j]
                * distance(i, j, nodes)
            )

constraint = (
    row_constraint
    + col_constraint
    + constraint1
    + constraint2
    + constraint3
    + constraint4
    + constraint5
)

P = 100
f = objective + P * qbpp.cons(constraint)
f = qbpp.simplify_as_binary(f)

ml = {x[i][i]: 0 for i in range(n)}

g = qbpp.replace(f, ml)
g = qbpp.simplify_as_binary(g)

solver = qbpp.ABS3Solver(g)

saved_energy = []
saved_violation = []
for loop in range(LOOP):
    print("solve:", loop+1)
    sol = solver.search(time_limit=TIME)
    energy = sol(g)
    violation = g.cons(sol)
    saved_energy.append(energy)
    saved_violation.append(violation)
    print("energy = ", energy)
    print("objective", sol(objective))
    print("violated constraints =", violation)
    print("constraint", sol(constraint))
    print("row_constraint", sol(row_constraint))
    print("col_constraint", sol(col_constraint))
    print("constraint1", sol(constraint1))
    print("constraint2", sol(constraint2))
    print("constraint3", sol(constraint3))
    print("constraint4", sol(constraint4))
    print("constraint5", sol(constraint5))
    tour = make_tour(sol)
    print(tour)
    filename = "sd_" + datetime.now().strftime("%m%d%H%M%S")
    plot_tour(nodes, tour, filename)
    plot_tour(nodes, tour, "sd")
print(sol.info)