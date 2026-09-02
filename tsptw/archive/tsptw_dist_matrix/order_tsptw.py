import pyqbpp as qbpp
from datetime import datetime
from dist_matrix import N, c, L, E
from tsptw_plot_no_e import plot_tour, recover_coordinates

TIME = 10.0
LOOP = 1

x = qbpp.var("x", shape=(N,N))
print("Created x")

w = qbpp.var("w", shape=N, between=(0, 100))
print("Created w")

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
    next_tw = t[i] + sum(w[j] for j in range(1, i))
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

objective = tw[N-1] + w[N-1] + qbpp.sum(x[N-1][u]*c[u][0] for u in range(1, N))
print("Created objective")

TOUR_P = 1000
TIME_P = 100
f = objective + TOUR_P*qbpp.cons(row_constraint + col_constraint) + TIME_P*(time_constraint)
f.simplify_as_binary()
print("Created f")


known_tour = [
    0,
    9, 11, 2, 15, 16, 4, 8, 1, 5, 6,
    10, 14, 18, 13, 7, 3, 17, 12, 20, 19
]

known_w = [0] * N

known_w[4] = 12
known_w[13] = 13
known_w[15] = 53

# ============================================================
# Known solution verification
# ============================================================

known_tour = [
    0,
    9, 11, 2, 15, 16, 4, 8, 1, 5, 6,
    10, 14, 18, 13, 7, 3, 17, 12, 20, 19
]

known_w = [0] * N

known_w[4] = 12
known_w[13] = 13
known_w[15] = 53


# ------------------------------------------------------------
# t[i] = cumulative travel time
# ------------------------------------------------------------

known_t = [0] * N

for i in range(1, N):
    u = known_tour[i - 1]
    v = known_tour[i]

    known_t[i] = known_t[i - 1] + c[u][v]


# ------------------------------------------------------------
# tw[i] = total elapsed time before waiting at i
# ------------------------------------------------------------

known_tw = [0] * N

for i in range(1, N):
    known_tw[i] = (
        known_t[i]
        + sum(known_w[j] for j in range(1, i))
    )


# ------------------------------------------------------------
# Check time windows
# ------------------------------------------------------------

print("")
print("========== Known Solution Check ==========")

time_violation = False

for i in range(1, N):
    u = known_tour[i]

    service_start = known_tw[i] + known_w[i]

    print(
        f"i={i:2d}, "
        f"u={u:2d}, "
        f"t={known_t[i]:3d}, "
        f"tw={known_tw[i]:3d}, "
        f"w={known_w[i]:3d}, "
        f"service={service_start:3d}, "
        f"[{E[u]:3d}, {L[u]:3d}]",
        end=""
    )

    if service_start < E[u] or service_start > L[u]:
        print("  VIOLATION")
        time_violation = True
    else:
        print("  OK")

print("")
print("time violation =", time_violation)