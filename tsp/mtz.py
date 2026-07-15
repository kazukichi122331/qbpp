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

x = qbpp.var("x", shape=(N, N))
y = qbpp.var("y", shape=N-1, between=(1, N-1))

row_constraint = qbpp.sum(qbpp.vector_sum(x, axis=0) == 1)
col_constraint = qbpp.sum(qbpp.vector_sum(x, axis=1) == 1)

mtz_constraint = qbpp.sum({y[i-1]-y[j-1] + (N-1)*x[i][j] <= N-2
                           for i in range(1,N)
                           for j in range(1,N)
                           if i!=j})

objective = qbpp.sum({x[i][j]*distance(i, j, nodes) for i in range(N) for j in range(N)})

P = 1000

f = objective + P*(row_constraint
                   + col_constraint
                   + mtz_constraint)
f.simplify_as_binary()

ml = {x[i][i]: 0 for i in range(N)}
g = qbpp.replace(f, ml)

sol = qbpp.ABS3Solver(g).search(time_limit=1.0)

print("\nconsなし")
print(f"energy = {sol(g)}")
print("violated constraints =", sol(row_constraint+col_constraint+mtz_constraint))
tour = make_tour(sol)
print(tour)
plot_tour(nodes, tour, "mtz_no_cons")
print("")

f_cons = objective + P*qbpp.cons(row_constraint
                            + col_constraint
                            + mtz_constraint)
f_cons.simplify_as_binary()

ml = {x[i][i]: 0 for i in range(N)}
g_cons = qbpp.replace(f_cons, ml)

sol_cons = qbpp.ABS3Solver(g_cons).search(time_limit=30.0)

print("consあり")
print(f"cons_energy = {sol_cons(g_cons)}")
print("violated constraints =", g_cons.cons(sol_cons))
tour = make_tour(sol_cons)
print(tour)
plot_tour(nodes, tour, "mtz_cons")
