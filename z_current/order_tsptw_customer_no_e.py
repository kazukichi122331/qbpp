import pyqbpp as qbpp
from datetime import datetime
from dist_matrix import N, c, L, dumas
from tsptw_plot import plot_tour, recover_coordinates

TIME = 30.0

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

nodes = recover_coordinates(c)
tour = []
for i in range(N):
    for u in range(N):
        if full_sol(x[i][u]) == 1:
            tour.append(u)
            break
tour.append(0)

for i in range(N):
    for u in range(N):
        if full_sol(x[i][u]) == 1:
            print(
                f"i={i}, u={u}, A[{u}]={full_sol(A[u])}, [0, {L[u]}]"
            )