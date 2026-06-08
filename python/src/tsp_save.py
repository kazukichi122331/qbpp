import pyqbpp as qbpp
import matplotlib.pyplot as plt
import math
import os

nodes = [(10, 12),  (33, 125),  (12, 226),
         (121, 11), (108, 142), (111, 243),
         (220, 4),  (210, 113), (211, 233)]

#nodes = [(10, 12),  (33, 125),  (12, 226), (121, 11), (108, 142), (111, 243)]

def distance(i, j):
    dx = nodes[i][0] - nodes[j][0]
    dy = nodes[i][1] - nodes[j][1]

    return round(math.sqrt(dx*dx + dy*dy))

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
                objective += distance(j, k) * x[i][j] * x[next_i][k]

f = objective + constraint * 1000
f.simplify_as_binary()

# フォルダ作成
os.makedirs("results", exist_ok=True)

for trial in range(10):

    print(f"\n=== Trial {trial} ===")

    solver = qbpp.EasySolver(f)
    sol = solver.search(time_limit=1.0)

    # 経路復元
    tour = []

    for i in range(n):
        for j in range(n):
            if sol(x[i][j]) == 1:
                tour.append(j)
                break

    tour.append(tour[0])

    print("Tour:", " -> ".join(map(str, tour)))

    # 描画用
    selected_edges = []

    for i in range(n):
        a = tour[i]
        b = tour[i + 1]
        selected_edges.append((a, b))

    # 新しい図を作成
    plt.figure()

    # 都市を描画
    for i, (px, py) in enumerate(nodes):
        plt.scatter(px, py, color="black")
        plt.text(px + 3, py + 3, str(i), color="black")

    # 辺を描画
    for i, j in selected_edges:
        x1, y1 = nodes[i]
        x2, y2 = nodes[j]

        dx = x2 - x1
        dy = y2 - y1

        plt.arrow(
            x1, y1,
            dx, dy,
            color="red",
            length_includes_head=True,
            head_width=5,
            head_length=8
        )

    plt.title(f"TSP Trial {trial}")
    plt.xlabel("x")
    plt.ylabel("y")

    # 保存
    plt.savefig(f"results/tsp_{trial}.png")

    # メモリ解放
    plt.close()