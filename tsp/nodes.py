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

ran_nodes = [(random.randint(0, 250), random.randint(0, 250)) for _ in range(n)]

time_nodes = [(10, 10, 0, 100)]
for _ in range(n-1):
    x = random.randint(30, 250)
    y = random.randint(30, 250)
    earliest = 0
    latest = earliest + random.randint(10, 100)
    time_nodes.append((x, y, earliest, latest))

def distance(i, j, nodes):
    dx = nodes[i][0] - nodes[j][0]
    dy = nodes[i][1] - nodes[j][1]
    return round(math.sqrt(dx * dx + dy * dy))

def travel_time(u, v, nodes):
    dx = nodes[u][0] - nodes[v][0]
    dy = nodes[u][1] - nodes[v][1]
    return round(math.sqrt(dx * dx + dy * dy))