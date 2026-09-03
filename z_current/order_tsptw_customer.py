import pyqbpp as qbpp
from datetime import datetime
from dist_matrix import N, c, L, E, dumas
from tsptw_plot import plot_tour, recover_coordinates

TIME = 1.0

x = qbpp.var("x", shape=(N,N))

w = qbpp.var("w", shape=N, between=(0, 100))

t = [qbpp.expr()] #i番目までの累積移動時間
for i in range(1, N):
    next_t = qbpp.copy(t[i-1])
    for u in range(N):
        for v in range(N):
            if u!=v:
                next_t += x[i-1][u]*x[i][v]*c[u][v]
    t.append(next_t)

A = [qbpp.expr()] #顧客uへの到着時刻（移動時間のみ）
for u in range(1, N):
    next_A = qbpp.expr()
    for i in range(1, N):
        next_A += x[i][u] * t[i]
    A.append(next_A)

tw = [qbpp.expr()]  #顧客uより前の顧客で発生した待ち時間の合計
for u in range(1, N):
    sum_i = qbpp.expr()
    for i in range(1, N):
        sum_jv = qbpp.expr()
        for j in range(1, i):
            for v in range(1, N):
                sum_jv += x[j][v]*w[v]
        sum_jv *= x[i][u]
        sum_i += sum_jv
    tw.append(sum_i)

row_constraint = qbpp.sum(qbpp.vector_sum(x, axis=1) == 1)

col_constraint = qbpp.sum(qbpp.vector_sum(x, axis=0) == 1)

time_constraint = qbpp.expr()

for u in range(1, N):
    service_start = A[u] + tw[u] + w[u]
    time_constraint += qbpp.cons(
        service_start - L[u],
        between=(None, 0)
    )
    time_constraint += qbpp.cons(
        service_start - E[u],
        between=(0, None)
    )

#移動時間のみ
objective = t[N-1] + qbpp.sum(x[N-1][u]*c[u][0] for u in range(1, N))

#合計時間
#objective = tw[N-1] + w[N-1] + qbpp.sum(x[N-1][u]*c[u][0] for u in range(1, N))


ROW_P = 5000
COL_P = 5000
TIME_P = 1000
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
                f"i={i}, u={u}, tw={full_sol(tw[u])}, w={full_sol(w[u])}, [{E[u]}, {L[u]}]"
            )

print("var_count:", sol.info['var_count'])
print("term_count:", sol.info['term_count'])