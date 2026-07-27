import pyqbpp as qbpp
from nodes import ran_nodes, distance
from plot_tour import plot_tour

def find_subtours(sol):
    tours = []

    unvisited = set(range(N))

    while unvisited:
        start = next(iter(unvisited))

        tour = [start]
        current = start

        while True:
            next_city = None

            for j in range(N):
                if round(sol(x[current][j])) == 1:
                    next_city = j
                    break

            if next_city is None:
                break

            if next_city == start:
                tour.append(start)
                break

            tour.append(next_city)
            current = next_city

        tours.append(tour)

        for v in set(tour[:-1]):
            unvisited.discard(v)

    return tours

def make_dfj(tour):
    S = set(tour[:-1])
    dfj_sum = 0
    for i in S:
        for j in S:
            if i!=j:
                dfj_sum += x[i][j]
    dfj_constraint = (dfj_sum <= len(S)-1)
    return dfj_constraint

nodes = ran_nodes
N = len(nodes)
LOOP = 10

x = qbpp.var("x", shape=(N, N))

rowconstraint = qbpp.sum(qbpp.vector_sum(x, axis=0) == 1)
colconstraint = qbpp.sum(qbpp.vector_sum(x, axis=1) == 1)

objective = qbpp.sum({x[i][j]*distance(i, j, nodes) for i in range(N) for j in range(N)})

P = 1000
ml = {x[i][i]: 0 for i in range(N)}

f = objective + P*qbpp.cons(rowconstraint
                            + colconstraint)
f.simplify_as_binary()

ml = {x[i][i]: 0 for i in range(N)}
g = qbpp.replace(f, ml)

added = set()
num_dfj = 0

best_sol = None
best_energy = 10000
while True:
    sol = qbpp.ABS3Solver(g).search(time_limit=1.0)

    tours = find_subtours(sol)

    print(tours)

    if len(tours) == 1 and len(set(tours[0][:-1])) == N:
        best_sol = sol
        best_energy = sol(g)
        best_tours = tours
        for loop in range(LOOP):
            sol = qbpp.ABS3Solver(g).search(time_limit=10.0)
            ene_g = sol(g)
            if best_energy > ene_g:
                best_sol = sol
                best_energy = ene_g
                best_tours = find_subtours(best_sol)
        break

    constraints = 0

    for subtour in tours:
        S = frozenset(subtour[:-1])

        if S in added:
            continue

        added.add(S)
        constraints += make_dfj(subtour)
        num_dfj += 1

    g += P * qbpp.cons(constraints)
    g.simplify_as_binary()

if best_sol == None:
    print("best_sol = None")
else:
    print("energy = ", best_sol(g))
    print("add constraint count", num_dfj)
    plot_tour(nodes, best_tours[0], "dfj")