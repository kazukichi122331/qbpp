# order_tsptw_no_e.py コピー済み 20260828

import pyqbpp as qbpp
from datetime import datetime
from dist_matrix import N, c, L
from tsptw_plot_no_e import plot_tour, recover_coordinates

TIME = 60.0
LOOP = 1

x = qbpp.var("x", shape=(N,N))
print("Created x")

t = [qbpp.expr()] #i番目の顧客への到着時刻
for i in range(1, N):
    next_t = qbpp.copy(t[i-1])
    for u in range(N):
        for v in range(N):
            if u!=v:
                next_t += x[i-1][u]*x[i][v]*c[u][v]
    t.append(next_t)
print("Created t")

row_constraint = qbpp.sum(qbpp.vector_sum(x, axis=1) == 1)
print("Created row_constraint")

col_constraint = qbpp.sum(qbpp.vector_sum(x, axis=0) == 1)
print("Created col_constraint")

time_constraint = qbpp.expr()
for i in range(1, N):
    for u in range(1, N):
        time_constraint += qbpp.cons(x[i][u]*(t[i] - L[u]), between=(None, 0))
print("Created time_constraint")

objective = qbpp.expr()
for i in range(N):
    next_i = (i+1)%(N)
    for u in range(N):
        for v in range(N):
            if u!=v:
                objective += x[i][u]*x[next_i][v]*c[u][v]
print("Created objective")

TOUR_P = 1000
TIME_P = 100
f = objective + TOUR_P*qbpp.cons(row_constraint + col_constraint) + TIME_P*(time_constraint)
f.simplify_as_binary()
print("Created f")

ml = {}
ml.update({x[0][0]: 1})
ml.update({x[0][u]: 0 for u in range(1, N)})
ml.update({x[i][0]: 0 for i in range(1, N)})
print("Created ml")

g = qbpp.replace(f, ml)
g.simplify_as_binary()
print("Created g")

solver = qbpp.ABS3Solver(g)
print("Created ABS3Solver")
print(f"solve now...({TIME} sec)")
sol = solver.search(time_limit=TIME)
print("Created sol")
full_sol = qbpp.Sol(f).set(sol, ml)
print("Created full_sol")
print("")

print("----------result----------")

print("energy = ", full_sol(f))
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
for i, u in enumerate(tour[:-1]):
    arrival_times[u] = full_sol(t[i])
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

for i in range(1, N):
    visit = 0
    for u in range(1, N):
        if full_sol(x[i][u]) == 1:
            visit = 1
            print(
                f"i={i:2d}, u={u:2d}, "
                f"x={full_sol(x[i][u])}, "
                f"t[i]={full_sol(t[i]):3d}, "
                f"L[u]={L[u]:3d} "
                , end=""
            )
            if full_sol(t[i]) - L[u] > 0:
                print("VIOLATION!")
            else:
                print("")
    if visit == 0:
        print(f"i={i:2d}, u=None VIOLATION!")

var_count = sol.info["var_count"]
term_count = sol.info["term_count"]

print("var_count = ", var_count)
print("term_count = ", term_count)