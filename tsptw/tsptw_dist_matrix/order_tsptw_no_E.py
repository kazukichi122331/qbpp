import pyqbpp as qbpp
from datetime import datetime
from dist_matrix import N, c, L

TIME = 30.0
LOOP = 1

x = qbpp.var("x", shape=(N,N))

a = [qbpp.expr()] #a[i]: i番目の顧客までの移動時間
for i in range(1, N):
    dist = qbpp.sum(x[i-1][u]*x[i][v]*c[u][v] for u in range(N) for v in range(N))
    next_a = a[i-1] + dist
    a.append(next_a)

T = [qbpp.expr()]
for u in range(N):
    for i in range(1, N):
        for v in range(N):
            vu_dist = x[i-1][v]*x[i][u]*c[u][v]
        current_dist = a[i-1]*x[i][u]
    T.append(current_dist + vu_dist)

row_constraint = qbpp.expr()
for u in range(N):
    rw_sum = qbpp.expr()
    for i in range(N):
        rw_sum += x[i][u]
    row_constraint += qbpp.cons(rw_sum == 1)

col_constraint = qbpp.expr()
for i in range(N):
    cl_sum = qbpp.expr()
    for u in range(N):
        cl_sum += x[i][u]
    col_constraint += qbpp.cons(cl_sum == 1)

time_constraint = qbpp.expr()
for i in range(N):
    time_constraint += qbpp.cons(a[i] - L[i] <= 0)


objective = qbpp.expr()
for i in range(N):
    next_i = (i+1)%(N)
    for u in range(N):
        for v in range(N):
            objective += x[i][u]*x[next_i][v]*c[u][v]

tour_P = 1000
time_P = 10
f = objective + tour_P*(row_constraint + col_constraint) + time_P*time_constraint
f.simplify_as_binary()

ml = {}
ml.update({x[0][0]: 1})
ml.update({x[0][u]: 0 for u in range(1, N)})
ml.update({x[i][0]: 0 for i in range(1, N)})

g = qbpp.replace(f, ml)
g.simplify_as_binary()

solver = qbpp.ABS3Solver(g)
sol = solver.search(time_limit=TIME)

full_sol = qbpp.Sol(f).set(sol, ml)

print("energy = ", full_sol(f))
print("constarint = ", f.cons(full_sol))