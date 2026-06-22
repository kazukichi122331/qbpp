#目的関数が四次になって項数爆発(項数数280万)が起こる
import pyqbpp as qbpp
from nodes import nodes, distance 
from plot_tour import plot_tour

n = len(nodes)-2
V = 3
x = qbpp.var("x", shape=(n+2, n+2, n+2, V))

objective = qbpp.expr()
for t in range(n+2):
    for i in range(n+2):
        for j in range(n+2):
            if i == j: continue
            objective += distance(i, j, nodes)*x[i][j][t][0]

L0 = objective

constraint1 = qbpp.expr()
for v in range(1, V):
    c1 = qbpp.expr()

    for t in range(n+2):
        for i in range(n+2):
            for j in range(n+2):
                if i == j: continue
                c1 += distance(i, j, nodes)*x[i][j][t][v]
    constraint1 += qbpp.constrain(c1 - L0, between=(None, 0))

constraint2 = qbpp.expr()

for v in range(V):
    for t in range(n + 1):
        edge_count = qbpp.expr()

        for i in range(n + 2):
            for j in range(n + 2):
                if i == j and i != n + 1:
                    continue
                edge_count += x[i][j][t][v]

        constraint2 += qbpp.constrain(edge_count, equal=1)

constraint3 = qbpp.expr()

for v in range(V):
    for t in range(n):
        for i in range(n + 2):
            if i == n + 1:
                continue

            constraint3 += (
                x[i][n + 1][t][v]
                * (1 - x[n + 1][n + 1][t + 1][v])
            )

constraint4 = qbpp.expr()

for j in range(1, n + 1):  # 顧客だけ
    visit_count = qbpp.expr()

    for v in range(V):
        for t in range(n + 1):
            for i in range(n + 2):
                if i == j:
                    continue
                visit_count += x[i][j][t][v]

    constraint4 += qbpp.constrain(visit_count, equal=1)

P = 1000
f = objective + P*(constraint1 + constraint2 + constraint3 + constraint4)
f.simplify_as_binary()

solver = qbpp.ABS3Solver(f)
sol = solver.search(time_limit=10.0)

print(f"energy = {sol(f)}")
print(f"constraint1 = {sol(constraint1)}")
print(f"constraint2 = {sol(constraint2)}")
print(f"constraint3 = {sol(constraint3)}")
print(f"constraint4 = {sol(constraint4)}")
