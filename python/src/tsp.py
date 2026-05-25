import math
import pyqbpp as qbpp
import matplotlib.pyplot as plt

nodes = [(10, 12),  (33, 125),  (12, 226),
         (121, 11), (108, 142), (111, 243),
         (220, 4),  (210, 113), (211, 233)]

def dist(i, j):
    dx = nodes[i][0] - nodes[j][0]
    dy = nodes[i][1] - nodes[j][1]
    return round(math.sqrt(dx * dx + dy * dy))

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
                objective += dist(j, k) * x[i][j] * x[next_i][k]

f = objective + constraint * 1000
f.simplify_as_binary()

solver = qbpp.EasySolver(f)
sol = solver.search(time_limit=1.0)

# 置換行列から巡回路（頂点番号のリスト）を抽出
tour = []
for i in range(n):
    for j in range(n):
        if sol(x[i][j]) == 1:
            tour.append(j)
            break
print(f"Tour: {tour}")

# 巡回路を画像として保存
plt.figure(figsize=(6, 6))

# 都市を描画
xs = [p[0] for p in nodes]
ys = [p[1] for p in nodes]
plt.scatter(xs, ys)

# 都市番号を表示
for i, (x_pos, y_pos) in enumerate(nodes):
    plt.text(x_pos + 3, y_pos + 3, str(i), fontsize=12)

# 経路を描画
for i in range(n):
    a = tour[i]
    b = tour[(i + 1) % n]

    x_values = [nodes[a][0], nodes[b][0]]
    y_values = [nodes[a][1], nodes[b][1]]

    plt.plot(x_values, y_values, color="blue")

plt.title(f"TSP Tour: {tour}")
plt.xlabel("x")
plt.ylabel("y")
plt.grid(True)
plt.axis("equal")

plt.savefig("tsp_result.png", dpi=300, bbox_inches="tight")