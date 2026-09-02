import pyqbpp as qbpp
from datetime import datetime
from dist_matrix import N, c, L, E
from tsptw_plot_no_e import plot_tour, recover_coordinates

TIME = 600.0
LOOP = 1

x = qbpp.var("x", shape=(N,N))
print("Created x")

w = [qbpp.expr()]*N

t = [qbpp.expr()] #累積移動時間
for i in range(1, N):
    next_t = qbpp.copy(t[i-1])
    for u in range(N):
        for v in range(N):
            if u!=v:
                next_t += x[i-1][u]*x[i][v]*c[u][v]
    t.append(next_t)
print("Created t")

tw = [qbpp.expr()] #合計時間
for i in range(1, N):
    next_tw = t[i] + sum(qbpp.max(0, E[j] - tw[j]) for j in range(1, i))
    tw.append(next_tw)

row_constraint = qbpp.sum(qbpp.vector_sum(x, axis=1) == 1)
print("Created row_constraint")

col_constraint = qbpp.sum(qbpp.vector_sum(x, axis=0) == 1)
print("Created col_constraint")

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
print("Created time_constraint")

objective = t[N-1] + qbpp.sum(x[N-1][u]*c[u][0] for u in range(1, N))
print("Created objective")

TOUR_P = 1000
TIME_P = 300
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
print("")

print(f"----------result({TIME} sec)----------")

print("energy = ", sol(g))
print("objective = ", sol(objective))
print("constarint = ", g.cons(sol))
print("row_constraint = ", sol(row_constraint))
print("col_constraint = ", sol(col_constraint))
print("time_constraint = ", sol(time_constraint))

tour = [0]
for i in range(1, N):
    for u in range(1, N):
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

for i in range(1, N):
    visit = 0
    for u in range(1, N):
        if sol(x[i][u]) == 1:
            visit = 1
            print(
                f"i={i:2d}, u={u:2d}, "
                f"tw[{i:02d}]={sol(tw[i]):3d}, "
                f"w[{i:02d}]={sol(w[i]):3d}, "
                f"[{E[u]:3d}, {L[u]:3d}] "
                , end=""
            )
            if sol(tw[i] + w[i]) - L[u] > 0 or sol(tw[i] + w[i]) - E[u] < 0:
                print("VIOLATION!")
            else:
                print("")
            break
    if visit == 0:
        print(f"i={i:2d}, u=None VIOLATION!")

var_count = sol.info["var_count"]
term_count = sol.info["term_count"]
cpu = sol.info["cpu"]
gpu = sol.info["gpu"]

print("var_count = ", var_count)
print("term_count = ", term_count)
print("cpu: ", cpu)
print("gpu: ", gpu)

visited = []

for i in range(1, N):
    for u in range(1, N):
        if sol(x[i][u]) == 1:
            visited.append(u)

print("visited =", visited)
print("duplicates =", [u for u in set(visited) if visited.count(u) > 1])
print("missing =", [u for u in range(1, N) if u not in visited])