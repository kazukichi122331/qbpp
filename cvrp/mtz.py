import pyqbpp as qbpp
import random
import math
from plot_tour import extract_routes, plot_routes

V = 10
K = 2
Q = 30
P = 1000
TIME = 10.0
random.seed(1)

n_lower_left = (V - 1) // 2
n_upper_right = (V - 1) - n_lower_left

nodes = ([(125, 125)]
    + [(random.randint(0, 124),random.randint(0, 124)) for _ in range(n_lower_left)]
    + [(random.randint(126, 250),random.randint(126, 250)) for _ in range(n_upper_right)])

q = [0] + [
    random.randint(1, 5)
    for _ in range(V - 1)
]

if any(q[i] > Q for i in range(1, V)):
    raise ValueError("顧客需要が車両容量を超えています。")

if sum(q) > K * Q:
    raise ValueError("総需要が全車両の総容量を超えています。")

c = [
    [0 for _ in range(V)]
    for _ in range(V)
]

for i in range(V):
    xi, yi = nodes[i]

    for j in range(V):
        if i != j:
            xj, yj = nodes[j]

            c[i][j] = round(
                math.sqrt(
                    (xi - xj) ** 2
                    + (yi - yj) ** 2
                )
            )

x = qbpp.var(
    "x",
    shape=(V, V)
)

u = qbpp.var(
    "u",
    shape=V - 1,
    between=(0, Q)
)

objective = 0

for i in range(V):
    for j in range(V):
        if i != j:
            objective += c[i][j] * x[i][j]

customer_out_cons = 0

for i in range(1, V):
    customer_out_cons += (
        sum(
            x[i][j]
            for j in range(V)
            if i != j
        ) == 1
    )

customer_in_cons = 0

for j in range(1, V):
    customer_in_cons += (
        sum(
            x[i][j]
            for i in range(V)
            if i != j
        ) == 1
    )

depot_out_cons = (
    sum(
        x[0][j]
        for j in range(1, V)
    ) == K
)

depot_in_cons = (
    sum(
        x[i][0]
        for i in range(1, V)
    ) == K
)

load_bound_cons = 0

for i in range(1, V):
    load_bound_cons += (
        u[i - 1] >= q[i]
    )

mtz_cons = 0

for i in range(1, V):
    for j in range(1, V):
        if i != j:
            mtz_cons += (
                u[i - 1]
                - u[j - 1]
                + Q * x[i][j]
                <= Q - q[j]
            )

constraints = (
    customer_out_cons
    + customer_in_cons
    + depot_out_cons
    + depot_in_cons
    + load_bound_cons
    + mtz_cons
)

f_mtz = objective + P * qbpp.cons(constraints)

f_mtz.simplify_as_binary()

fixed_values = {
    x[i][i]:0
    for i in range(V)
}

g_mtz = qbpp.replace(
    f_mtz,
    fixed_values
)

g_mtz.simplify_as_binary()

solver = qbpp.ABS3Solver(g_mtz)
sol = solver.search(time_limit=TIME)

edges = []

for i in range(V):
    for j in range(V):
        if i != j and sol[x[i][j]] == 1:
            edges.append((i, j))

routes = extract_routes(edges)

plot_routes(nodes,routes,"mtz_cvrp")

print("energy = ", sol(g_mtz))
print("violation = ", g_mtz.cons(sol))

for i in range(V):
    for j in range(V):
        if sol(x[i][j]) == 1:
            print(f"{i}->{j}")