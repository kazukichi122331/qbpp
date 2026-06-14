import pyqbpp as qbpp
from nodes import nodes, distance
from plot_tour import plot_edges

def make_edges(full_sol):
    edges = []
    for i in range(0, n+1):
        for j in range(1, n+2):
            if i == j:
                continue
            if full_sol(x[i][j]) == 1:
                edges.append((i, j))
                print(f"({i}, {j})")
    return edges

def make_constraint(sol):
    constraint = qbpp.expr()
    for i in range(0, n+1):
        for j in range(1, n+2):
            if sol(x[i][j]) == 1:
                constraint += x[i][j]
    return qbpp.constrain(constraint, between=(None, n-1))

def print_mtz_violations(full_sol):
    count = 0
    for i in range(1, n+1):
        for j in range(1, n+1):
            if i == j:
                continue
            if full_sol(x[i][j]) == 1:
                lhs = full_sol(y[i-1]) - full_sol(y[j-1]) + n
                ok = lhs <= n - 1
                if not ok:
                    print(
                        f"   MTZ violation: {i}->{j}, "
                        f"y[{i}]={full_sol(y[i-1])}, "
                        f"y[{j}]={full_sol(y[j-1])}, "
                        f"lhs={lhs}"
                    )
                    count += 1
    print(f"   MTZ violations = {count}")

n = len(nodes)-2

x = qbpp.var("x", shape=(n+2, n+2))
y = qbpp.var("y", shape=n, between=(1, n))

constraint1 = \
    qbpp.sum([
        qbpp.constrain(qbpp.sum([x[i][j] for j in range(1, n+2)]), equal=1)
        for i in range(0, n+1)
    ]) + \
    qbpp.sum([
        qbpp.constrain(qbpp.sum([x[i][j] for i in range(0, n+1)]), equal=1)
        for j in range(1, n+2)
    ])

constraint2 = qbpp.sum([
    qbpp.constrain(y[i-1] - y[j-1] + n * x[i][j], between=(None, n-1))
    for i in range(1, n+1)
    for j in range(1, n+1)
])

P = 1000
constraint = P*(10*constraint1 + constraint2)

objective = qbpp.sum([
    distance(i, j, nodes) * x[i][j]
    for i in range(0, n+1)
    for j in range(1, n+2)
])

f = objective + constraint
new_f = qbpp.copy(f)

ml = {x[0][n+1]: 0}
ml.update({x[i][i]: 0 for i in range(1, n+1)})

for i in range(10):
    g = qbpp.replace(new_f, ml)
    g.simplify_as_binary()

    solver = qbpp.ABS3Solver(g)
    sol = solver.search(time_limit=30.0)

    full_sol = qbpp.Sol(new_f).set(sol, ml)

    print(
        f"{i+1}: energy = {full_sol(f)}, "
        f"objective = {full_sol(objective)}, "
        f"constraint1 = {full_sol(constraint1)}, "
        f"constraint2 = {full_sol(constraint2)}"
    )

    new_f += P * make_constraint(full_sol)
    print_mtz_violations(full_sol)

print(f"energy = {full_sol(f)}")
print(f"constraint1 = {full_sol(constraint1)}")
print(f"constraint2 = {full_sol(constraint2)}")
plot_edges(nodes, make_edges(full_sol), "mtz")