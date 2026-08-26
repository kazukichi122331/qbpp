import pyqbpp as qbpp
from datetime import datetime
from tsptw.archive.tsptw_leq.travel_time import travel_time
from tsptw.archive.tsptw_leq.tsptw_plot import plot_tour
from tsptw.archive.tsptw_leq.time_nodes import time_nodes_10, time_nodes_15, time_nodes_20

TIME = 30.0 #ソルバーの実行時間
LOOP = 10  #実行回数

nodes = time_nodes_20 #(x座標, y座標, 開始時刻, 締切時刻)
N = len(nodes) - 1 #デポ:0 顧客:1~N

x = qbpp.var("x", shape=(N+1,N+1)) #x[i][u]=1: i番目に顧客uに訪れる
w = qbpp.var("w", shape=N+1, between=(0,50)) #w[i]: i番目の顧客の待ち時間

c = [[travel_time(u, v, nodes) for v in range(N+1)] for u in range(N+1)] #c[u][v]: 顧客uから顧客vの移動時間

row_constraint = qbpp.sum(qbpp.vector_sum(x, axis=0) == 1) #\sum_i x = 1 ∀u
col_constraint = qbpp.sum(qbpp.vector_sum(x, axis=1) == 1) #\sum_u x = 1 ∀i



f = 0
f.simplify_as_binary()

ml = {}
ml.update({x[0][0]: 1})
ml.update({x[0][u]: 0 for u in range(1, N+1)})
ml.update({x[i][0]: 0 for i in range(1, N+1)})
g = qbpp.replace(f, ml)
g.simplify_as_binary()

solver = qbpp.ABS3Solver(g)
sol = solver.search(time_limit=TIME)

print("energy = ", sol(g))
print("constarint = ", g.cons(sol))

plot_nodes = [(x, y) for x, y, _, _ in nodes]

tour = [0] 
for i in range(N+1):
    for u in range(N+1):
        if sol(x[i][u]) == 1:
            tour.append(u)

arrival_times = [0] * (N + 1)
wait_times = [0] * (N + 1)

if len(tour) == N + 1:
    current_time = 0

    for i in range(1, N + 1):
        u = tour[i - 1]
        v = tour[i]

        # u -> v の移動時間
        current_time += c[u][v]

        # vへの到着時刻
        arrival_times[v] = current_time

        # vでの待ち時間
        wait_times[v] = sol(w[i])

        # 待ち時間を経過時間に加える
        current_time += wait_times[v]

    ready_times = [nodes[v][2] for v in range(N + 1)]
    due_times = [nodes[v][3] for v in range(N + 1)]

    filename = "tsptw_" + datetime.now().strftime("%m%d%H%M")

    tour.append(0)

    plot_tour(
        plot_nodes,
        tour,
        ready_times,
        wait_times,
        arrival_times,
        due_times,
        c,
        filename
    )

    print("\n--- ツアー順の時間 ---")
    print("pos : ", list(range(len(tour) - 1)))
    print("node: ", tour[:-1])
    print("arr : ", [arrival_times[v] for v in tour[:-1]])
    print("wait: ", [wait_times[v] for v in tour[:-1]])
    print("start: ", [arrival_times[v] + wait_times[v] for v in tour[:-1]])
    print("rdy : ", [ready_times[v] for v in tour[:-1]])
    print("due : ", [due_times[v] for v in tour[:-1]])
else:
    print("ツアー制約違反")

    for i in range(N + 1):
        visit = 0

        # i=0 は x[0][0] が replace で消えているので除外
        if i == 0:
            print(f"pos {i}: 0")
            continue

        for u in range(N + 1):
            if sol(x[i][u]) == 1:
                print(f"pos {i}: {u}")
                visit = 1
                break

        if visit == 0:
            print(f"pos {i}: None")

var_count = sol.info["var_count"]
term_count = sol.info["term_count"]

print("var_count = ", var_count)
print("term_count = ", term_count)