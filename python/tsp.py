import pyqbpp as qbpp
from itertools import permutations
from tsp_data import locations, dist

N = len(locations)
x = qbpp.var("x", shape=(N, N))

def print_edge(sol):
    i = 0
    print(f"{i} -> ", end="")
    while True:
        next_node = None
        for j in range(N):
            if sol(x[i][j]) == 1:
                next_node = j
                break
        if next_node == 0:
            print(f"{next_node}", end="")
            break
        print(f"{next_node} -> ", end="")
        
        i = next_node
    print()

def selected_edge(sol):
    selected_edge = [0]
    i = 0
    while True:
        next_node = None
        for j in range(N):
            if sol(x[i][j]) == 1:
                next_node = j
                break
        if next_node is None:
            break
        selected_edge.append(next_node)
        if next_node == 0:
            break
        i = next_node
    return selected_edge

def forbid_cycle_permutations(cycle):
    constraints = 0

    inner = cycle[1:-1]  # 0を除く

    for perm in permutations(inner):
        route = [0] + list(perm) + [0]

        expr = 1
        for i in range(len(route) - 1):
            expr *= x[route[i]][route[i+1]]

        constraints += (expr == 0)

    return constraints

row_constraint = qbpp.sum(qbpp.vector_sum(x, axis=0) == 1)
col_constraint = qbpp.sum(qbpp.vector_sum(x, axis=1) == 1)

objective = 0
for i in range(N):
    for j in range(N):
        objective += x[i][j]*dist(i, j)

P = 1000
f = objective + P*qbpp.cons(row_constraint + col_constraint)
f.simplify_as_binary()

ml = {x[i][i]: 0 for i in range(N)}
g = qbpp.replace(f, ml)

new_constraint = qbpp.expr()
for loop in range(100):
    g += P*qbpp.cons(new_constraint)
    g.simplify_as_binary()
    sol = qbpp.ABS3Solver(g).search(time_limit=1.0)

    print_edge(sol)

    edge = selected_edge(sol)
    if len(edge) < N:
        new_constraint = forbid_cycle_permutations(edge)
    else:
        break

print(f"f = {sol(g)}")
print(f"violated constraint = {g.cons(sol)}")
print_edge(sol)