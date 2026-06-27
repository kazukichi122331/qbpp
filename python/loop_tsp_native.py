import pyqbpp as qbpp
from nodes import nodes, distance 
from plot_tour import plot_tour

def make_tour(sol):
    tour = []
    for t in range(n+1):
        found = False
        for i in range(n+2):
            for j in range(n+2):
                if sol(x[i][j][t]) == 1:
                    if t == 0: tour.append(i)
                    tour.append(j)
                    found = True
                    break
            if found: break
    return tour


n = len(nodes)-2
x = qbpp.var("x", shape=(n+2, n+2, n+1))

objective = qbpp.expr()

for u in range(n+2):
    for v in range(n+2):
        if u == v: continue
        for t in range(n+1):
            objective += x[u][v][t]*distance(u,v, nodes)

constraint1 = qbpp.expr()

for u in range(n+1):
    constraint = qbpp.expr()
    for v in range(1, n+2):
        if u == v: continue
        for t in range(n+1):
            constraint += x[u][v][t]
    constraint1 += qbpp.constrain(constraint, equal=1)

constraint2 = qbpp.expr()

for v in range(1, n+2):
    constraint = qbpp.expr()
    for u in range(n+1):
        if u == v: continue
        for t in range(n+1):
            constraint += x[u][v][t]
    constraint2 += qbpp.constrain(constraint, equal=1)

constraint3 = qbpp.expr()

for u in range(1, n+2):
    for v in range(n+2):
        if u == v: continue
        for t in range(n+1):
            for w in range(n+2):
                if u == w: continue
                for j in range(t+1, n+1):
                    constraint3 += x[u][v][t] * x[w][u][j]

# 論文では制約1~3だけだったけどtについてもone-hotって言わないと大変なことになる
constraint4 = qbpp.expr()

for t in range(n+1):
    constraint = qbpp.expr()
    for u in range(n+1):
        for v in range(1, n+2):
            if u == v: continue
            constraint += x[u][v][t]
    constraint4 += qbpp.constrain(constraint, equal=1)

P = 500

f = objective + P*(constraint1 + constraint2 + constraint3 + constraint4)
f.simplify_as_binary()

ml = {

}

solver = qbpp.ABS3Solver(f)

best_sol = None
for loop in range(5):
    sol = solver.search(time_limit=30.0)
    energy = sol(f)
    print(f"{loop+1}: energy = {energy}")
    if best_sol is None or energy < best_sol(f):
        best_sol = sol

tour = make_tour(best_sol)

print(f"Tour: {tour}")
print(f"energy: {sol(f)}")
print(f"constraint1: {sol(constraint1)}")
print(f"constraint2: {sol(constraint2)}")
print(f"constraint3: {sol(constraint3)}")
print(f"constraint4: {sol(constraint4)}")
print(f"var_count: {sol.info['var_count']}")
print(f"term_count: {sol.info['term_count']}")

plot_tour(nodes, tour, "tsp_native")