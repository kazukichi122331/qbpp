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
u = qbpp.var("u", shape=(N), between=(1, N-1))

row_constraint = qbpp.sum(qbpp.vector_sum(x, axis=0) == 1)
col_constraint = qbpp.sum(qbpp.vector_sum(x, axis=1) == 1)

mtz_eq_constraint = 0
for i in range(1, N):
    for j in range(1, N):
        if i != j:
            mtz_eq_constraint += (x[i][j]*(u[i]-u[j]+1) == 0)

objective = 0
for i in range(N):
    for j in range(N):
        if i != j:
            objective += x[i][j]*distance(i, j, nodes)

P=1000
f = objective + P*qbpp.cons(row_constraint + col_constraint + mtz_eq_constraint)
f.simplify_as_binary()

ml = {x[i][i]: 0 for i in range(N)}
g = qbpp.replace(f, ml)
g.simplify_as_binary()

solver = qbpp.ABS3Solver(g)
sol = solver.search(time_limit=30.0)

print("energy = ", sol(g))
print("row constraint = ", sol(row_constraint))
print("col constraint = ", sol(col_constraint))
print("mtz constraint = ", sol(mtz_eq_constraint))

for i in range(N):
    for j in range(N):
        if sol(x[i][j]) == 1:
            print(f"{i}->{j}")
tour = make_tour(sol)
print("tour = ", tour)
plot_tour(nodes, tour, "mtz_eq")