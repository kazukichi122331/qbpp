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
TIME = 1.0

x = qbpp.var("x", shape=(N, N))
y = qbpp.var("y", shape=N-1, between=(1, N-1))

row_constraint = qbpp.sum(qbpp.vector_sum(x, axis=0) == 1)
col_constraint = qbpp.sum(qbpp.vector_sum(x, axis=1) == 1)

mtz_constraint = qbpp.sum({y[i-1]-y[j-1] + (N-1)*x[i][j] <= N-2
                           for i in range(1,N)
                           for j in range(1,N)
                           if i!=j})

dl_constraint = qbpp.sum({y[i-1]-y[j-1] + (N-1)*x[i][j] + (N-3)*x[j][i] <= N-2
                           for i in range(1,N)
                           for j in range(1,N)
                           if i!=j})

objective = qbpp.sum({x[i][j]*distance(i, j, nodes) for i in range(N) for j in range(N)})

P = 1000
ml = {x[i][i]: 0 for i in range(N)}

f_mtz = objective + P*qbpp.cons(row_constraint
                                + col_constraint
                                + mtz_constraint)

f_dl =  objective + P*qbpp.cons(row_constraint
                                + col_constraint
                                +dl_constraint)
f_mtz.simplify_as_binary()
f_dl.simplify_as_binary()

g_mtz = qbpp.replace(f_mtz, ml)
g_dl = qbpp.replace(f_dl, ml)

solver_mtz = qbpp.ABS3Solver(g_mtz)
solver_dl = qbpp.ABS3Solver(g_dl)

saved_energy_mtz = []
saved_violation_mtz = []
print("\n---MTZ---")
for loop in range(LOOP):
    sol_mtz = solver_mtz.search(time_limit=TIME)
    energy = sol_mtz(g_mtz)
    violation = g_mtz.cons(sol_mtz)
    saved_energy_mtz.append(energy)
    saved_violation_mtz.append(violation)

    print("energy = ", energy)
    print("violated constraints =", violation)
    tour = make_tour(sol_mtz)
    print(tour)
    plot_tour(nodes, tour, "mtz")

saved_energy_dl = []
saved_violation_dl = []
print("\n---DL---")
for loop in range(LOOP):
    sol_dl = solver_dl.search(time_limit=TIME)
    energy = sol_dl(g_dl)
    violation = g_dl.cons(sol_dl)
    saved_energy_dl.append(energy)
    saved_violation_dl.append(violation)

    print("energy = ", energy)
    print("violated constraints =", violation)
    tour = make_tour(sol_dl)
    print(tour)
    plot_tour(nodes, tour, "dl")

print("\nMTZ")
print(saved_energy_mtz)
print(saved_violation_mtz)
print("DL")
print(saved_energy_dl)
print(saved_violation_dl)
print("")