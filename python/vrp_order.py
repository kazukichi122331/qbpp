#目的関数が四次になって項数爆発(項数数280万)が起こる
import pyqbpp as qbpp
from nodes import nodes, distance 
from plot_tour import plot_tour

n = len(nodes)-2
V = 3
x = qbpp.var("x", shape=(V, n+2, n+2))

objective = qbpp.expr()
for t in range(n+1):
    for i in range(n+2):
        for j in range(n+2):
            if i == j: continue
            objective += distance(i, j, nodes)*x[0][t][i]*x[0][t+1][j]

L0 = objective

constraint1 = qbpp.expr()
for v in range(1, V):
    c1 = qbpp.expr()

    for t in range(n+1):
        for i in range(n+2):
            for j in range(n+2):
                if i == j: continue
                c1 += distance(i, j, nodes)*x[v][t][i]*x[v][t+1][j]
    constraint1 += qbpp.constrain(c1 - L0, between=(None, 0))

constraint2 = qbpp.sum(qbpp.vector_sum(x) == 1)

constraint3 = qbpp.expr()
for v in range(V):
    for t in range(1, n+1):
        constraint3 += x[v][t][n+1] * (1 - x[v][t+1][n+1])

constraint4 = 0
for i in range(1, n+1):
    visit_count = qbpp.expr()
    for v in range(V):
        for t in range(1, n+1):
            visit_count += x[v][t][i]
    constraint4 += qbpp.constrain(visit_count, equal=1)

P = 2000
f = objective + P*(constraint1 + constraint2 + constraint3 + constraint4)


ml = {}

for v in range(V):
    ml[x[v][0][0]] = 1          # 時刻0: 開始デポ
    ml[x[v][n+1][n+1]] = 1  # 最終時刻: 終了デポ

    for t in range(1, n+2):
        ml[x[v][t][0]] = 0      # 開始デポへは戻らない

g = qbpp.replace(f, ml)
f.simplify_as_binary()
g.simplify_as_binary()
solver = qbpp.ABS3Solver(g)

sol = solver.search(time_limit=30.0)

full_sol = qbpp.Sol(f).set(sol, ml)

print(f"energy = {full_sol(f)}")
print(f"mini max = {full_sol(objective)}")
print(f"constraint1 = {full_sol(constraint1)}")
print(f"constraint2 = {full_sol(constraint2)}")
print(f"constraint3 = {full_sol(constraint3)}")
print(f"constraint4 = {full_sol(constraint4)}")
print(f"max_degree = {g.max_degree}")
print(f"term_count = {g.term_count()}")

for v in range(V):
    route = []

    for t in range(n + 2):
        for i in range(n + 2):
            if full_sol(x[v][t][i]) == 1:
                route.append(i)
                break

        if route[-1] == n + 1:
            break

    print(f"Vehicle {v}: ", end="")
    print(" -> ".join(map(str, route)))
    print()