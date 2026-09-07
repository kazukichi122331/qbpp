import pyqbpp as qbpp
from datetime import datetime
from dist_matrix import N, c, L, E
from tsptw_plot_no_e import plot_tour, recover_coordinates

TIME = 1.0
LOOP = 100

x = qbpp.var("x", shape=(N,N))

w = qbpp.var("w", shape=N, between=(0, 100))

t = [qbpp.expr()] #累積移動時間
for i in range(1, N):
    next_t = qbpp.copy(t[i-1])
    for u in range(N):
        for v in range(N):
            if u!=v:
                next_t += x[i-1][u]*x[i][v]*c[u][v]
    t.append(next_t)


tw = [qbpp.expr()] #合計時間
for i in range(1, N):
    next_tw = t[i] + sum(w[j] for j in range(1, i))
    tw.append(next_tw)

row_constraint = qbpp.sum(qbpp.vector_sum(x, axis=1) == 1)

col_constraint = qbpp.sum(qbpp.vector_sum(x, axis=0) == 1)

time_constraint = qbpp.expr()
# 顧客ごと
#for i in range(1, N):
#    for u in range(1, N):
#        service_start = tw[i] + w[i]
#        time_constraint += qbpp.cons(x[i][u]*service_start - L[u], between=(None, 0))
#        time_constraint += qbpp.cons(x[i][u]*service_start - E[u], between=(0, None))
# 訪問順
for i in range(1, N):
    service_start = tw[i] + w[i]
    sum_L = qbpp.expr()
    sum_E = qbpp.expr()
    for u in range(1, N):
        sum_L += x[i][u]*L[u]
        sum_E += x[i][u]*E[u]
    time_constraint += qbpp.cons(service_start - sum_L, between=(None, 0))
    time_constraint += qbpp.cons(service_start - sum_E, between=(0, None))

none_penalty = qbpp.expr()

for i in range(1, N):
    row_sum = qbpp.sum(x[i][u] for u in range(1, N))
    none_penalty += (1 - row_sum) * (1 - row_sum)

#移動時間のみ
objective = t[N-1] + qbpp.sum(x[N-1][u]*c[u][0] for u in range(1, N))

#合計時間
#objective = tw[N-1] + w[N-1] + qbpp.sum(x[N-1][u]*c[u][0] for u in range(1, N))

ROW_P = 1000
COL_P = 1000
TIME_P = 10
NONE_P = 1000
f = objective + ROW_P*qbpp.cons(row_constraint) + COL_P*qbpp.cons(col_constraint) + TIME_P*time_constraint + NONE_P*none_penalty


ml = {}
ml.update({x[0][0]: 1})
ml.update({x[0][u]: 0 for u in range(1, N)})
ml.update({x[i][0]: 0 for i in range(1, N)})

g = qbpp.replace(f, ml)

f = qbpp.simplify_as_binary(f)
g = qbpp.simplify_as_binary(g)

solver = qbpp.ABS3Solver(g)
print(f"N={N} solve now...({TIME} sec)")
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
for i, u in enumerate(tour[:-1]):
    arrival_times[u] = full_sol(tw[i])
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
            print(
                f"tour{i:2d}: {u:2d}, "
                f"arrived={full_sol(tw[i]):3d}, "
                f"wait={full_sol(w[i]):3d}, "
                f"visit={full_sol(tw[i]) + full_sol(w[i]):3d}, "
                f"[{E[u]:3d}, {L[u]:3d}] "
                , end=""
            )
            if full_sol(tw[i] + w[i]) - L[u] > 0 or full_sol(tw[i] + w[i]) - E[u] < 0:
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

