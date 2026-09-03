import pyqbpp as qbpp
from datetime import datetime
import time
from dist_matrix import N, c, L, dumas
from tsptw_plot_no_e import plot_tour, recover_coordinates

TIME = 1.0
LOOP = 1
start = time.perf_counter()
x = qbpp.var("x", shape=(N,N))

t = [qbpp.expr()] #i番目までの累積移動時間
for i in range(1, N):
    next_t = qbpp.copy(t[i-1])
    for u in range(N):
        for v in range(N):
            if u!=v:
                next_t += x[i-1][u]*x[i][v]*c[u][v]
    t.append(next_t)

A = [qbpp.expr()]
for u in range(1, N):
    next_A = qbpp.expr()
    for i in range(1, N):
        next_A += x[i][u] * t[i]
    A.append(next_A)

row_constraint = qbpp.sum(qbpp.vector_sum(x, axis=1) == 1)

col_constraint = qbpp.sum(qbpp.vector_sum(x, axis=0) == 1)

time_constraint = qbpp.expr()
#顧客ごと
for u in range(1, N):
    time_constraint += qbpp.cons(A[u] - L[u], between=(None, 0))
#移動時間のみ
objective = t[N-1] + qbpp.sum(x[N-1][u]*c[u][0] for u in range(1, N))

#合計時間
#objective = tw[N-1] + w[N-1] + qbpp.sum(x[N-1][u]*c[u][0] for u in range(1, N))


ROW_P = 1000
COL_P = 1000
TIME_P = 100
f = objective + ROW_P*qbpp.cons(row_constraint) + COL_P*qbpp.cons(col_constraint) + TIME_P*time_constraint
end = time.perf_counter()

ml = {}
ml.update({x[0][0]: 1})
ml.update({x[0][u]: 0 for u in range(1, N)})
ml.update({x[i][0]: 0 for i in range(1, N)})

g = qbpp.replace(f, ml)

f = qbpp.simplify_as_binary(f)
g = qbpp.simplify_as_binary(g)
#solver = qbpp.ABS3Solver(g)
print(f"定式化時間: {end-start:3f} sec")
print(dumas)
#for loop in range(LOOP):
#    sol = solver.search(time_limit=TIME)
#    full_sol = qbpp.Sol(f).set(sol, ml)
#    print(f"----------result {loop+1}({TIME} sec)----------")
#
#    print("energy = ", full_sol(f))
#    print("objective = ", full_sol(objective))
#    print("constarint = ", f.cons(full_sol))
#
#    nodes = recover_coordinates(c)
#    tour = []
#    for i in range(N):
#        for u in range(N):
#            if full_sol(x[i][u]) == 1:
#                tour.append(u)
#                break
#    tour.append(0)
#
#    arrival_times = [0] * N
#    for i, u in enumerate(tour[:-1]):
#        arrival_times[u] = full_sol(t[i])
#    due_times = L
#    travel_time = c
#    filename = "tsptw_no_e_" + datetime.now().strftime("%m%d%H%M")
#    plot_tour(nodes, tour, arrival_times, due_times, travel_time, filename)
#
#var_count = sol.info["var_count"]
#term_count = sol.info["term_count"]
#print("var_count = ", var_count)
#print("term_count = ", term_count)