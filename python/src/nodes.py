import math
import random

n = 30
seed = 1
random.seed(seed)

nodes = [(random.randint(0, 250), random.randint(0, 250)) for _ in range(n)]
nodes.append(nodes[0])

def distance(i, j, nodes):
    dx = nodes[i][0] - nodes[j][0]
    dy = nodes[i][1] - nodes[j][1]
    return round(math.sqrt(dx * dx + dy * dy))

print(nodes)