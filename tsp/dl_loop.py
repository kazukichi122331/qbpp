import pyqbpp as qbpp
from nodes import ran_nodes, distance
from plot_tour import plot_tour


def make_tour(sol):
    tour = [0]
    current = 0
    visited = {0}

    for _ in range(N):
        next_city = None

        for j in range(N):
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
N = len(nodes)
LOOP = 10

x = qbpp.var("x", shape=(N, N))
y = qbpp.var("y", shape=N-1, between=(1, N-1))

row_constraint = qbpp.sum(qbpp.vector_sum(x, axis=0) == 1)
col_constraint = qbpp.sum(qbpp.vector_sum(x, axis=1) == 1)

dl_constraint = qbpp.sum({y[i-1]-y[j-1] + (N-1)*x[i][j] + (N-3)*x[j][i] <= N-2
                           for i in range(1,N)
                           for j in range(1,N)
                           if i!=j})

objective = qbpp.sum({x[i][j]*distance(i, j, nodes) for i in range(N) for j in range(N)})

P = 1000

f = objective + P*(row_constraint
                   + col_constraint
                   + dl_constraint)
f.simplify_as_binary()

ml = {x[i][i]: 0 for i in range(N)}
g = qbpp.replace(f, ml)

solver = qbpp.ABS3Solver(g)

saved_energy = []
saved_violation = []
print("\n---consなし---")
for loop in range(LOOP):
    sol = solver.search(time_limit=1.0)
    solg = sol(g)
    violation = sol(row_constraint+col_constraint+dl_constraint)
    print(f"solve{loop+1}:")
    print(f"energy = {solg}, ", end="")
    print("violated constraints =", violation)
    saved_energy.append(solg)
    saved_violation.append(violation)
    tour = make_tour(sol)
    print(tour)
    print("")

f_cons = objective + P*qbpp.cons(row_constraint
                                 + col_constraint
                                 + dl_constraint)
f_cons.simplify_as_binary()

g_cons = qbpp.replace(f_cons, ml)
solver_cons = qbpp.ABS3Solver(g_cons)

saved_cons_energy = []
saved_cons_violation = []
print("---consあり---")
for loop in range(LOOP):
    sol_cons = solver.search(time_limit=1.0)
    cons_solg = sol_cons(g_cons)
    cons_violation = g_cons.cons(sol_cons)
    print(f"solve{loop+1}:")
    print(f"cons_energy = {sol_cons(g_cons)}, ", end="")
    print("violated constraints =", g_cons.cons(sol_cons))
    saved_cons_energy.append(cons_solg)
    saved_cons_violation.append(cons_violation)
    tour = make_tour(sol_cons)
    print(tour)
    print("")

print("consなし")
print(saved_energy)
print(saved_violation)

print("consあり")
print(saved_cons_energy)
print(saved_cons_violation)