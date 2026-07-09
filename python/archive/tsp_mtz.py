import pyqbpp as qbpp
from nodes import nodes, distance
from plot_tour import plot_edges

def make_edges(full_sol):
    edges = []
    for i in range(0, n+1):
        for j in range(1, n+2):
            if i == j:
                continue
            if full_sol(x[i][j]) == 1:
                edges.append((i, j))
    return edges

def make_tour(sol):
    tour = [0]
    current = 0
    visited = {0}

    while True:
        found = False

        for j in range(n+2):
            if sol(x[current][j]) == 1:
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

x = qbpp.var("x", shape=(n+2, n+2))
y = qbpp.var("y", shape=n, between=(1, n))

constraint1 = \
    qbpp.sum([
        qbpp.constrain(qbpp.sum([x[i][j] for j in range(1, n+2)]), equal=1)
        for i in range(0, n+1)
    ]) + \
    qbpp.sum([
        qbpp.constrain(qbpp.sum([x[i][j] for i in range(0, n+1)]), equal=1)
        for j in range(1, n+2)
    ])

constraint2 = qbpp.sum([
    qbpp.constrain(y[i-1] - y[j-1] + n * x[i][j], between=(None, n-1))
    for i in range(1, n+1)
    for j in range(1, n+1)
    if i != j
])

P = 1000
constraint = P*(10*constraint1 + constraint2)

objective = qbpp.sum([
    distance(i, j, nodes) * x[i][j]
    for i in range(0, n+1)
    for j in range(1, n+2)
])

f = objective + constraint
ml = {x[0][n+1]: 0}
ml.update({x[i][i]: 0 for i in range(1, n+1)})

g = qbpp.replace(f, ml)
g.simplify_as_binary()

solver = qbpp.ABS3Solver(g)
sol = solver.search(time_limit=1.0)

full_sol = qbpp.Sol(f).set(sol, ml)

tour = make_tour(full_sol)
edges = make_edges(full_sol)

#print(f"Tour: {tour}")
#print(f"energy = {full_sol(f)}")
#print(f"constraint1 = {full_sol(constraint1)}")
#print(f"constraint2 = {full_sol(constraint2)}")
print("mtz")
print(f"var_count: {sol.info['var_count']}")
print(f"term_count: {sol.info['term_count']}")

#plot_edges(nodes, edges, "tsp_mtz")