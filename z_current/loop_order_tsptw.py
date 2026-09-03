import pyqbpp as qbpp
from datetime import datetime
from dist_matrix import N, c, L, E, dumas
from tsptw_plot import plot_tour, recover_coordinates

TIME = 60.0
LOOP = 10

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

#移動時間のみ
objective = t[N-1] + qbpp.sum(x[N-1][u]*c[u][0] for u in range(1, N))

#合計時間
#objective = tw[N-1] + w[N-1] + qbpp.sum(x[N-1][u]*c[u][0] for u in range(1, N))

ASSIGN_P = 50000
TIME_P = 10
f = objective + ASSIGN_P*(qbpp.cons(row_constraint) + qbpp.cons(col_constraint)) + TIME_P*time_constraint

ml = {}
ml.update({x[0][0]: 1})
ml.update({x[0][u]: 0 for u in range(1, N)})
ml.update({x[i][0]: 0 for i in range(1, N)})

g = qbpp.replace(f, ml)

f = qbpp.simplify_as_binary(f)
g = qbpp.simplify_as_binary(g)

saved_energy = []
for loop in range(LOOP):
    print(f"----------solve {loop+1}----------")
    filename = "tsptw_" + datetime.now().strftime("%m%d%H%M")
    print(f"{dumas} {filename}")
    solver = qbpp.ABS3Solver(g)
    sol = solver.search(time_limit=TIME)
    full_sol = qbpp.Sol(f).set(sol, ml)

    energy = full_sol(f)
    saved_energy.append(energy)
    print("energy = ", energy)
    print("objective = ", full_sol(objective))
    print("constraint = ", f.cons(full_sol))
    for i in range(N):
        visit = 0
        for u in range(N):
            if full_sol(x[i][u]) == 1:
                visit = 1
                break
        if visit == 0:
            print(f"tour{i:2d}: None VIOLATION!")

    nodes = recover_coordinates(c)
    tour = []
    for i in range(N):
        for u in range(N):
            if full_sol(x[i][u]) == 1:
                tour.append(u)
                break
    tour.append(0)
    if len(tour) != N+1:
        print("cannot plot!")
        continue

    arrival_times = [0] * N
    wait_times = [0] * N

    # 訪問順 → 顧客番号に変換
    for i in range(N):
        u = tour[i]

        arrival_times[u] = full_sol(tw[i])
        wait_times[u] = full_sol(w[i])
    ready_times = E
    due_times = L
    travel_time = c

    plot_tour(
        nodes,
        tour,
        ready_times,
        wait_times,
        arrival_times,
        due_times,
        travel_time,
        filename
    )

    for i in range(N):
        print(f"{tour[i]:3d} ", end="")
    print("")
    for i in range(N):
        print(f"{full_sol(tw[i]):3d} ", end="")
    print("")
    for i in range(N):
        print(f"{full_sol(w[i]):3d} ", end="")
    print("")

print(saved_energy)