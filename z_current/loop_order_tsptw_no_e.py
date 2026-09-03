import pyqbpp as qbpp
import time
from datetime import datetime
from dist_matrix import N, c, L, dumas
from tsptw_plot_no_e import plot_tour, recover_coordinates

TIME = 1.0
LOOP = 1

start = time.perf_counter()
x = qbpp.var("x", shape=(N,N))

t = [qbpp.expr()] # i番目の顧客への到着時刻
for i in range(1, N):
    next_t = qbpp.copy(t[i-1])
    for u in range(N):
        for v in range(N):
            if u!=v:
                next_t += x[i-1][u]*x[i][v]*c[u][v]
    t.append(next_t)

row_constraint = qbpp.sum(qbpp.vector_sum(x, axis=1) == 1)

col_constraint = qbpp.sum(qbpp.vector_sum(x, axis=0) == 1)

time_constraint = qbpp.expr()
# 顧客ごと
#for i in range(1, N):
#    for u in range(1, N):
#        time_constraint += qbpp.cons(x[i][u]*(t[i] - L[u]), between=(None, 0))
# 訪問順
for i in range(N):
    sum_L = qbpp.expr()
    for u in range(N):
        sum_L += x[i][u]*L[u]
    time_constraint += qbpp.cons(t[i] - sum_L, between=(None, 0))

objective = qbpp.expr()
for i in range(N):
    next_i = (i+1)%(N)
    for u in range(N):
        for v in range(N):
            if u!=v:
                objective += x[i][u]*x[next_i][v]*c[u][v]

TOUR_P = 1000
TIME_P = 100
f = objective + TOUR_P*qbpp.cons(row_constraint + col_constraint) + TIME_P*(time_constraint)
end = time.perf_counter()
f.simplify_as_binary()

ml = {}
ml.update({x[0][0]: 1})
ml.update({x[0][u]: 0 for u in range(1, N)})
ml.update({x[i][0]: 0 for i in range(1, N)})

g = qbpp.replace(f, ml)
g.simplify_as_binary()
saved_energy = []
print(f"定式化時間: {end-start:3f} sec")
print(dumas)
#for loop in range(LOOP):
#    solver = qbpp.ABS3Solver(g)
#    sol = solver.search(time_limit=TIME)
#    full_sol = qbpp.Sol(f).set(sol, ml)
#    print("")
#    print(f"----------result {loop+1}({TIME} sec)----------")
#    energy = full_sol(f)
#    saved_energy.append(energy)
#    print("energy = ", energy)
#    print("constarint = ", f.cons(full_sol))
#
#    tour = []
#    for i in range(N):
#        for u in range(N):
#            if full_sol(x[i][u]) == 1:
#                tour.append(u)
#                break
#    tour.append(0)
#    filename = "tsptw_no_e_" + datetime.now().strftime("%m%d%H%M")
#    nodes = recover_coordinates(c)
#    arrival_times = [0] * N
#    for i, u in enumerate(tour[:-1]):
#        arrival_times[u] = full_sol(t[i])
#    due_times = L
#    travel_time = c
#
#    plot_tour(
#        nodes,
#        tour,
#        arrival_times,
#        due_times,
#        travel_time,
#        filename
#    )
#    print("tour:", tour)
#print(saved_energy)
#var_count = sol.info["var_count"]
#term_count = sol.info["term_count"]
#print("var_count = ", var_count)
#print("term_count = ", term_count)