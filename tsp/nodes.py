import math
import random

n = 15
R = 100  # 半径
cx, cy = 125, 125  # 中心座標
random.seed(1)
reg_nodes = []
ran_nodes = []

for i in range(n):
    theta = 2 * math.pi * i / n
    x = round(cx + R * math.cos(theta))
    y = round(cy + R * math.sin(theta))
    reg_nodes.append((x, y))

ran_nodes = [(random.randint(0, 250), random.randint(0, 250)) for _ in range(n)]

def distance(i, j, nodes):
    dx = nodes[i][0] - nodes[j][0]
    dy = nodes[i][1] - nodes[j][1]
    return round(math.sqrt(dx * dx + dy * dy))