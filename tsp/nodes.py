import math
import random

n = 5
R = 100  # 半径
cx, cy = 125, 125  # 中心座標
random.seed(1)

reg_nodes = []
for i in range(n):
    theta = 2 * math.pi * i / n
    x = round(cx + R * math.cos(theta))
    y = round(cy + R * math.sin(theta))
    reg_nodes.append((x, y))

ran_nodes = [(random.randint(10, 250), random.randint(10, 250)) for _ in range(n)]

candidates = [
    (x, y)
    for x in range(6)
    for y in range(6)
    if not (x == 0 and y == 0)
]
random.shuffle(candidates)
time_nodes = [(0, 0, 0, 100)]
for x, y in candidates[:n-1]:
    earliest = 0
    latest = random.randint(5, 25)
    time_nodes.append((x, y, earliest, latest))

x = [node[0] for node in time_nodes]
y = [node[1] for node in time_nodes]
tm_nodes_xy = [(x[i], y[i]) for i in range(n)]

def distance(i, j, nodes):
    dx = nodes[i][0] - nodes[j][0]
    dy = nodes[i][1] - nodes[j][1]
    return round(math.sqrt(dx * dx + dy * dy))

def travel_time(u, v, nodes):
    dx = nodes[u][0] - nodes[v][0]
    dy = nodes[u][1] - nodes[v][1]
    return round(math.sqrt(dx * dx + dy * dy))