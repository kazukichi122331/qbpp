import pyqbpp as qbpp
from datetime import datetime
from dist_matrix import N, c, L, E
from tsptw_plot_no_e import plot_tour, recover_coordinates

TIME = 60.0
LOOP = 1

x = qbpp.var("x", shape=(N,N))

w = qbpp.var("w", shape=N, between=(0, 60))

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

row_constraint = qbpp.cons(qbpp.sum(qbpp.vector_sum(x, axis=1) == 1))

col_constraint = qbpp.cons(qbpp.sum(qbpp.vector_sum(x, axis=0) == 1))

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

fix_constraint = qbpp.expr()
fix_constraint += qbpp.cons(x[0][0] == 1)
for u in range(1, N):
    fix_constraint += qbpp.cons(x[0][u] == 0)
for i in range(1, N):
    fix_constraint += qbpp.cons(x[i][0] == 0)

objective = t[N-1] + qbpp.sum(x[N-1][u]*c[u][0] for u in range(1, N))

TOUR_P = 1000
TIME_P = 300
f = objective + TOUR_P*(row_constraint + col_constraint + fix_constraint) + TIME_P*(time_constraint)

f.simplify_as_binary()

solver = qbpp.ABS3Solver(f)
print(f"solve now...({TIME} sec)")
sol = solver.search(time_limit=TIME)
print("")

print(f"----------result({TIME} sec)----------")

print("energy = ", sol(f))
print("objective = ", sol(objective))
print("constarint = ", f.cons(sol))
print("row_constraint = ", sol(row_constraint))
print("col_constraint = ", sol(col_constraint))
print("time_constraint = ", sol(time_constraint))

tour = []
for i in range(N):
    for u in range(N):
        if sol(x[i][u]) == 1:
            tour.append(u)
            break
tour.append(0)
filename = "tsptw_no_e_" + datetime.now().strftime("%m%d%H%M")
nodes = recover_coordinates(c)
arrival_times = [0] * N
for i, u in enumerate(tour[:-1]):
    arrival_times[u] = sol(tw[i])
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

pre_u = 0
for i in range(N):
    visit = 0
    for u in range(N):
        if sol(x[i][u]) == 1:
            visit = 1
            print(
                f"x[{i:02d}][{u:02d}]=1: "
                f"arrv={sol(tw[i]):3d}, "
                f"wait={sol(w[i]):3d}, "
                f"dist={c[pre_u][u]:2d}, "
                f"[{E[u]:3d}, {L[u]:3d}] "
                , end=""
            )
            if sol(tw[i] + w[i]) - L[u] > 0 or sol(tw[i] + w[i]) - E[u] < 0:
                print("VIOLATION!")
            else:
                print("")
            pre_u = u
            break
    if visit == 0:
        print(f"i={i:2d}, u=None VIOLATION!")

visited = []

for i in range(N):
    for u in range(N):
        if sol(x[i][u]) == 1:
            visited.append(u)

print("visited =", visited)
print("duplicates =", [u for u in set(visited) if visited.count(u) > 1])
print("missing =", [u for u in range(N) if u not in visited])

var_count = sol.info["var_count"]
term_count = sol.info["term_count"]

print("var_count = ", var_count)
print("term_count = ", term_count)