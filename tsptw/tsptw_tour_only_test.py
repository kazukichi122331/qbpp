from tsptw.travel_time import travel_time
import pyqbpp as qbpp

time_nodes = [
    (0, 0, 0, 100),
    (2, 0, 0, 100),
    (4, 0, 0, 100),
    (0, 3, 0, 100),
    (0, 5, 0, 100),
    (1, 2, 0, 100),
    (3, 4, 0, 100),
    (5, 5, 0, 100),
    (3, 1, 0, 100),
    (2, 4, 0, 100),
]

nodes = time_nodes #(x座標, y座標, 訪問時間の開始, 訪問時間の終了)

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
                objective += travel_time(j, k, nodes) * x[i][j] * x[next_i][k]

f = objective + constraint * 1000
f.simplify_as_binary()

ml = {x[0][0]: 1}
ml.update({x[i][0]: 0 for i in range(1, n)})
ml.update({x[0][i]: 0 for i in range(1, n)})

g = qbpp.replace(f, ml)
g.simplify_as_binary()

solver = qbpp.EasySolver(g)
sol = solver.search(time_limit=10.0)

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

