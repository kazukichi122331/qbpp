import pyqbpp as qbpp
from datetime import datetime
from dist_matrix import N, c, L, E
from tsptw_plot_no_e import plot_tour, recover_coordinates

TIME = 60.0
LOOP = 1

x = qbpp.var("x", shape=(N,N))

w = qbpp.var("w", shape=N, between=(0, 100))

a = qbpp.var("a", shape=N, between=(0,500))


row_constraint = qbpp.expr()
for i in range(N):
    row = qbpp.expr()
    for u in range(N):
        row += x[i][u]
    row_constraint += qbpp.cons(row == 1)

col_constraint = qbpp.expr()
for u in range(N):
    col = qbpp.expr()
    for i in range(N):
        col += x[i][u]
    col_constraint += qbpp.cons(col == 1)

M = 1000
arrival_constraint = qbpp.expr()
for i in range(N-1):
    for u in range(N):
        for v in range(N):
            if u!=v:
                arrival_constraint += qbpp.cons(
                    a[v] - (a[u] + w[u] + c[u][v] - M*(1 - x[i][u] - x[i+1][v]))
                    , between=(0, None)
                )

time_constraint = qbpp.expr()
for u in range(1, N):
    time_constraint += qbpp.cons(a[u] + w[u], between=(E[u], None))
    time_constraint += qbpp.cons(a[u] + w[u], between=(None, L[u]))

objective = qbpp.expr()
for i in range(N):
    next_i = (i+1)%N
    for u in range(N):
        for v in range(N):
            if u!=v:
                objective += x[i][u]*x[next_i][v]*c[u][v]

ASSIGN_P = 1000
ARRIVAL_P = 1000
TIME_P = 100
f = (
    objective
    + ASSIGN_P * row_constraint
    + ASSIGN_P * col_constraint
    + ARRIVAL_P * arrival_constraint
    + TIME_P * time_constraint
)

ml = {}
ml.update({x[0][0]: 1})
ml.update({x[0][u]: 0 for u in range(1, N)})
ml.update({x[i][0]: 0 for i in range(1, N)})

g = qbpp.replace(f, ml)

f = qbpp.simplify_as_binary(f)
g = qbpp.simplify_as_binary(g)

solver = qbpp.ABS3Solver(g)
print(f"solve now...({TIME} sec)")
sol = solver.search(time_limit=TIME)
full_sol = qbpp.Sol(f).set(sol, ml)
print("")

print(f"----------result({TIME} sec)----------")

print("energy = ", full_sol(f))
print("objective = ", full_sol(objective))
print("constarint = ", f.cons(full_sol))
print("row_constraint = ", full_sol(row_constraint))
print("col_constraint = ", full_sol(col_constraint))
print("time_constraint = ", full_sol(time_constraint))

tour = []

for i in range(N):
    for u in range(N):
        if full_sol(x[i][u]) == 1:
            tour.append(u)
            break

tour.append(0)

filename = "tsptw_no_e_" + datetime.now().strftime("%m%d%H%M")

nodes = recover_coordinates(c)

arrival_times = [0] * N
for u in tour[:-1]:
    arrival_times[u] = full_sol(a[u])

due_times = L
travel_time = c

plot_tour(
    nodes,
    tour,
    arrival_times,
    due_times,
    travel_time,
    filename
)

for i in range(N):
    visit = 0
    for u in range(N):
        if full_sol(x[i][u]) == 1:
            visit = 1

            arrival = full_sol(a[u])
            wait = full_sol(w[u])
            service_start = arrival + wait

            print(
                f"tour{i:2d}: {u:2d}, "
                f"arrived={arrival:3d}, "
                f"wait={wait:3d}, "
                f"visit={service_start:3d}, "
                f"[{E[u]:3d}, {L[u]:3d}] ",
                end=""
            )

            if service_start > L[u] or service_start < E[u]:
                print("VIOLATION!")
            else:
                print("")

            break

    if visit == 0:
        print(f"tour{i:2d}: None VIOLATION!")

print("tour:", tour)

var_count = sol.info["var_count"]
term_count = sol.info["term_count"]
print("var_count = ", var_count)
print("term_count = ", term_count)