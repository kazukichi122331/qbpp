import random

from plot_tour import plot_tour

n = 40
random.seed(1)

ran_nodes = ([(random.randint(0, 1000), random.randint(0, 1000)) for _ in range(n//4)]
             + [(random.randint(0, 1000), random.randint(1100, 2000)) for _ in range(n//4)]
             + [(random.randint(1100, 2000), random.randint(0, 1000)) for _ in range(n//4)]
             + [(random.randint(1100, 2000), random.randint(1100, 2000)) for _ in range(n//4)])

plot_tour(ran_nodes, [(0, 0)], "big_nodes")