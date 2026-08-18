import math
from nodes import ran_nodes, distance
import pyqbpp as qbpp

tw_nodes = [
    (5, 5, 0, 100),   # デポ
    (2, 8, 4, 12),
    (7, 2, 8, 16),
    (9, 7, 13, 22),
    (3, 3, 18, 27),
    (6, 9, 23, 32),
    (1, 6, 28, 37),
    (8, 4, 33, 42),
    (4, 1, 38, 47),
    (2, 2, 43, 52),
    (8, 9, 48, 57)
]
nodes = []
for x, y, _, _ in tw_nodes:
    nodes.append((x, y))

TIME = 10.0
n = len(nodes)
x = qbpp.var("x", shape=(n, n))

constraint = qbpp.sum(qbpp.vector_sum(x, axis=1) == 1) + \
             qbpp.sum(qbpp.vector_sum(x, axis=0) == 1)

objective = qbpp.expr()
for i in range(n):
    next_i = (i + 1) % n
    for j in range(n):
        for k in range(n):
            if k != j:
                objective += distance(j, k, nodes) * x[i][j] * x[next_i][k]

f = objective + constraint * 1000
f.simplify_as_binary()

ml = {x[0][0]: 1}
ml.update({x[i][0]: 0 for i in range(1, n)})
ml.update({x[0][i]: 0 for i in range(1, n)})

g = qbpp.replace(f, ml)
g.simplify_as_binary()

solver = qbpp.EasySolver(g)
sol = solver.search(time_limit=TIME)

full_sol = qbpp.Sol(f).set(sol, ml)

print(full_sol(f))
# 置換行列から巡回路（頂点番号のリスト）を抽出
tour = []
for i in range(n):
    for j in range(n):
        if full_sol(x[i][j]) == 1:
            tour.append(j)
            break
print(f"Tour: {tour}")

