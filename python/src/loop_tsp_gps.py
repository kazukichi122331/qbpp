import pyqbpp as qbpp
from nodes import nodes, distance
from plot_tour import plot_edges

def make_edges(sol):
    edges = []
    for i in range(0, n+1):
        for j in range(1, n+2):
            if i == j:
                continue
            if sol(x[i][j][1]) == 1:
                edges.append((i, j))
    return edges

def make_tour(sol):
    tour = [0]
    current = 0
    visited = {0}

    while True:
        found = False

        for j in range(n+2):
            if sol(x[current][j][1]) == 1:
                tour.append(j)
                current = j
                found = True
                break

        if not found:
            break

        if current == n+1:
            break

        if current in visited:
            print("partial cycle detected")
            break

        visited.add(current)

    return tour

n = len(nodes)-2
x = qbpp.var("x", shape=(n+2, n+2, 3))

objective = qbpp.expr()
for i in range(0, n+1):
    for j in range(1, n+2):
        if i == j: continue
        objective += distance(i, j, nodes)*x[i][j][1]

constraint1 = qbpp.expr()
for i in range(0, n+1):
    for j in range(1, n+2):
        if i == j: continue
        c_sum1 = x[i][j][0] + x[i][j][1] + x[i][j][2]
        constraint1 += qbpp.constrain(c_sum1, equal=1)


constraint2 = qbpp.expr()
for i in range(0, n+1):
    c_sum2 = qbpp.expr()
    for j in range(1, n+2):
        if i == j: continue
        c_sum2 += x[i][j][1]
    constraint2 += qbpp.constrain(c_sum2, equal=1)


constraint3 = qbpp.expr()
for j in range(1, n+2):
    c_sum3 = qbpp.expr()
    for i in range(0, n+1):
        if i == j: continue
        c_sum3 += x[i][j][1]
    constraint3 += qbpp.constrain(c_sum3, equal=1)

constraint5 = qbpp.expr()
for i in range(1, n+1):
    for j in range(1, n+1):
        for k in range(1, n+1):
            if (i != j and j != k and k != i):
                constraint5 += (
                    x[j][i][2] * x[k][j][2]
                    - x[j][i][2] * x[k][i][2]
                    - x[k][j][2] * x[k][i][2]
                    + x[k][i][2]
                )

P = 1000
constraint = constraint1 + constraint2 + constraint3 + constraint5
f = objective + P*constraint

ml = {
    x[j][i][2]: 1-x[i][j][2]
    for i in range(1, n+1)
    for j in range(i+1, n+1)
    if i != j
}

g = qbpp.replace(f, ml)
g.simplify_as_binary()

solver = qbpp.ABS3Solver(g)

best_sol = None
for loop in range(10):
    sol = solver.search(time_limit=10.0)
    energy = sol(g)
    print(f"{loop+1}: energy = {energy}")
    if best_sol is None or energy < best_sol(g):
        best_sol = sol

full_sol = qbpp.Sol(f).set(best_sol)

for i in range(1, n+1):
    for j in range(i+1, n+1):
        full_sol.set(x[j][i][2], 1 - full_sol(x[i][j][2]))

tour = make_tour(full_sol)
edges = make_edges(full_sol)

print(f"Tour: {tour}")
print(f"energy = {full_sol(f)}")
print(f"constraint = {full_sol(constraint)}")
print(f"var_count: {sol.info['var_count']}")
print(f"term_count: {sol.info['term_count']}")

plot_edges(nodes, edges, "loop_tsp_gps")