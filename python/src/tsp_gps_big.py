import pyqbpp as qbpp
import matplotlib.pyplot as plt
import math
import random

def make_random_nodes(n, x_min=0, x_max=250, y_min=0, y_max=250, seed=None):
    if seed is not None:
        random.seed(seed)

    nodes = []
    for _ in range(n):
        x = random.randint(x_min, x_max)
        y = random.randint(y_min, y_max)
        nodes.append((x, y))

    return nodes

def distance(i, j):
    dx = nodes[i][0] - nodes[j][0]
    dy = nodes[i][1] - nodes[j][1]

    return round(math.sqrt(dx*dx + dy*dy))

n = 20
nodes = make_random_nodes(n, seed=1)
r = 3
x = qbpp.var("x", shape=(n, n, r))
# r=0  都市iから都市jの順だがi->jは使わない
# r=1  都市iから都市jの順でi->jを使う
# r=2  都市jから都市iの順だがi->jは使わない

constraint1 = qbpp.sum([
    qbpp.constrain(
        qbpp.vector_sum(x, axis=2)[i][j],
        equal=1
    )
    for i in range(n)
    for j in range(n)
    if i != j
])

constraint2 = qbpp.sum(
    qbpp.constrain(qbpp.vector_sum(x[:, :, 1], axis=1), equal=1)
)

constraint3 = qbpp.sum(
    qbpp.constrain(qbpp.vector_sum(x[:, :, 1], axis=0), equal=1)
)

constraint4 = qbpp.sum([
    qbpp.constrain(x[i][j][2] + x[j][i][2], equal=1)
    for i in range(n)
    for j in range(n)
    if i < j
])

constraint5 = qbpp.sum([
    x[j][i][2] * x[k][j][2] - x[j][i][2] * x[k][i][2] - x[k][j][2] * x[k][i][2] + x[k][i][2]
    for i in range(n)
    for j in range(n)
    for k in range(n)
    if i != j and j != k and k != i
])

obj = qbpp.sum([
    distance(i, j)*x[i][j][1]
    for i in range(n)
    for j in range(n)
    if i != j
])

A = 1000
f = obj + A*(constraint1 + constraint2 + constraint3 + constraint4 + constraint5)

ml = {
    x[i][i][k]: 0
    for i in range(n)
    for k in range(r)
}
g = qbpp.replace(f, ml)
g.simplify_as_binary()

solver = qbpp.ABS3Solver(g)
sol = solver.search(time_limit=1.0)


# 標準出力
next_city = {}

for i in range(n):
    for j in range(n):
        if i != j and sol(x[i][j][1]) == 1:
            next_city[i] = j

tour = [0]
current = 0

while True:
    current = next_city[current]
    tour.append(current)

    if current == 0:
        break

print("->".join(map(str, tour)))

# 画像を保存
selected_edges = []

# GPSでは r=1 が「辺 i->j を使う」
for i in range(n):
    for j in range(n):
        if i != j and sol(x[i][j][1]) == 1:
            selected_edges.append((i, j))

plt.figure()

# 都市を黒で描画
for i, (px, py) in enumerate(nodes):
    plt.scatter(px, py, color="black")
    plt.text(px + 3, py + 3, str(i), color="black")

# 経路を赤矢印で描画
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

plt.title("TSP with GPS Formulation")
plt.xlabel("x")
plt.ylabel("y")
plt.axis("equal")

# 画像保存
plt.savefig("gps_big.png")
plt.close()