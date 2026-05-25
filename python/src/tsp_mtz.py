import pyqbpp as qbpp
import matplotlib.pyplot as plt
import math

#nodes = [(10, 12),  (33, 125),  (12, 226),
#         (121, 11), (108, 142), (111, 243),
#         (220, 4),  (210, 113), (211, 233)]

nodes = [(10, 12),  (33, 125),  (12, 226), (121, 11), (108, 142), (111, 243)]

def distance(i, j):
    dx = nodes[i][0] - nodes[j][0]
    dy = nodes[i][1] - nodes[j][1]

    return round(math.sqrt(dx*dx + dy*dy))

n = len(nodes)
x = qbpp.var("x", shape=(n, n))
y = qbpp.var("y", shape=n, between=(0, n-1))

constraint1 = qbpp.sum([
    qbpp.constrain(qbpp.sum([x[i][j] for j in range(n) if i != j]), equal=1)
    for i in range(n)
]) + \
    qbpp.sum([
    qbpp.constrain(qbpp.sum([x[i][j] for i in range(n) if i != j]), equal=1)
    for j in range(n)
])


constraint2 = qbpp.sum([
    qbpp.constrain(y[i] - y[j] + n * x[i][j], between=(None, n-1))
    for i in range(1, n)
    for j in range(1, n)
    if i != j
])

constraint = constraint1 + constraint2

obj = qbpp.sum([
    distance(i, j) * x[i][j]
    for i in range(n)
    for j in range(n)
    if i != j
])

f = obj + 1000*constraint
f.simplify_as_binary()

solver = qbpp.EasySolver(f)
sol = solver.search(time_limit=10.0)

print("energy:", sol(f))
print("min distance", sol(obj))
print("constraint  = ", sol(constraint ))
print("constraint1 = ", sol(constraint1))
print("constraint2 = ", sol(constraint2))

tour = [0]
current = 0
visited = set([0])

while True:
    next_city = None

    for j in range(n):
        if j != current and sol(x[current][j]) == 1:
            next_city = j
            break

    if next_city is None:
        print("経路復元失敗: 次の都市が見つかりません")
        break

    tour.append(next_city)

    if next_city == 0:
        break

    if next_city in visited:
        print("経路復元失敗: 部分巡回が発生しています")
        break

    visited.add(next_city)
    current = next_city

print("Tour:", " -> ".join(map(str, tour)))

selected_edges = []

for i in range(n):
    for j in range(n):
        if i != j and sol(x[i][j]) == 1:
            selected_edges.append((i, j))

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

plt.title("TSP with MTZ Constraint")
plt.xlabel("x")
plt.ylabel("y")

# 画像保存
plt.savefig("mtz.png")