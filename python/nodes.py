import math
import random

n = 10
R = 100  # 半径
cx, cy = 125, 125  # 中心座標
nodes = []

for i in range(n):
    theta = 2 * math.pi * i / n
    x = round(cx + R * math.cos(theta))
    y = round(cy + R * math.sin(theta))
    nodes.append((x, y))
nodes.append(nodes[0])

def distance(i, j, nodes):
    dx = nodes[i][0] - nodes[j][0]
    dy = nodes[i][1] - nodes[j][1]
    return round(math.sqrt(dx * dx + dy * dy))