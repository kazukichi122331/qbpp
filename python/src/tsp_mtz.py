import pyqbpp as qbpp
import matplotlib.pyplot as plt
import math

nodes = [(10, 12),  (33, 125),  (12, 226),
         (121, 11), (108, 142), (111, 243),
         (220, 4),  (210, 113), (211, 233)]

def distance(i, j):
    dx = nodes[i][0] - nodes[j][0]
    dy = nodes[i][1] - nodes[j][1]

    return round(math.sqrt(dx*dx + dy*dy))

n = len(nodes)
x = qbpp.var("x", shape=(n, n))
y = qbpp.var("y", shape=n-1, between=(1, n-1)) # y[i]は都市i+1の訪問順を表す

constraint1 = qbpp.sum(qbpp.constrain(qbpp.vector_sum(x, axis=1), equal=1)) + \
              qbpp.sum(qbpp.constrain(qbpp.vector_sum(x, axis=0), equal=1))


constraint2 = qbpp.sum([
    qbpp.constrain(y[i-1] - y[j-1] + n * x[i][j], between=(None, n-1))
    for i in range(n)
    for j in range(n)
    if i != 0 and j != 0 and i != j
])

constraint = 1000*(100*constraint1 + 10*constraint2)

obj = qbpp.sum([
    distance(i, j) * x[i][j]
    for i in range(n)
    for j in range(n)
    if i != j
])

f = obj + constraint

ml = {x[i][i]: 0 for i in range(n)}

g = qbpp.replace(f, ml)
g.simplify_as_binary()

solver = qbpp.EasySolver(g)
sol = solver.search(time_limit=300.0)

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