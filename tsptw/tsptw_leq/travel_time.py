import math

def travel_time(u, v, nodes):
    dx = nodes[u][0] - nodes[v][0]
    dy = nodes[u][1] - nodes[v][1]
    return round(math.sqrt(dx * dx + dy * dy))