import pyqbpp.d as qbpp
from cvrp_data import locations, dist

vehicle_capacity = qbpp.array([200, 250, 300])
N, V = len(locations), len(vehicle_capacity)

sorted_demands = sorted(locations[i][2] for i in range(1, N)) #キャパのソート順
max_capacity = max(vehicle_capacity[v] for v in range(V))#キャパの最大値

L, acc = 0, 0
for d in sorted_demands: #一つの車両が最大で何人訪問できるか
    if acc + d > max_capacity: break #貪欲法で容量の小さい顧客を順に足す
    acc += d; L += 1

a = qbpp.var("a", shape=(V, L, N))# a[v][t][i]車両vがt番目に顧客iに訪れる

row_constraint = qbpp.sum(qbpp.vector_sum(a) == 1) #各車両vは各時刻tにただ一つの顧客iを持つ

column_sum = [0 for _ in range(N - 1)]
for v in range(V):
    for t in range(L):
        for i in range(1, N):
            column_sum[i - 1] += a[v][t][i]
column_constraint = 0 #各顧客iはただ一つの車両vと時刻tを持つ
for i in range(N - 1):
    column_constraint += (column_sum[i] == 1)

vehicle_load = [0 for _ in range(V)] #車両の積み荷
capacity_constraint = 0 #車両vは経路全体の容量がキャパを超えてはいけない
for v in range(V):
    for t in range(L):
        for i in range(1, N):
            vehicle_load[v] += a[v][t][i] * locations[i][2]
    capacity_constraint += (0 <= vehicle_load[v]) & (qbpp.same <= vehicle_capacity[v])

objective = 0.0
for v in range(V):
    for i in range(1, N):
        objective += dist(0, i) * a[v][0][i]
    for t in range(L - 1):
        for i in range(N):
            for j in range(N):
                if dist(i, j) != 0:
                    objective += dist(i, j) * a[v][t][i] * a[v][t + 1][j]
    for i in range(1, N):
        objective += dist(i, 0) * a[v][L - 1][i]

f = objective + 3000 * qbpp.cons(row_constraint 
                                 + column_constraint 
                                 + capacity_constraint)
f.simplify_as_binary()

sol = qbpp.ABS3Solver(f).search(time_limit=1.0)

print("violated constraints =", f.cons(sol))
print(f"objective = {sol(objective):.2f}")
for v in range(V):
    load = int(sol(vehicle_load[v]))
    cap = int(vehicle_capacity[v])
    route = f"Vehicle {v} : load = {load} / {cap} : 0 "
    for t in range(L):
        for i in range(1, N):
            if sol(a[v][t][i]) == 1:
                route += f"-> {i}({locations[i][2]}) "; break
    print(route + "-> 0")
