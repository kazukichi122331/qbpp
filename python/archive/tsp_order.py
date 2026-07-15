import pyqbpp as qbpp
from tsp.nodes import nodes, distance 
from tsp.plot_tour import plot_tour

def make_tour(full_sol):
    tour = []
    for i in range(n+2):
        for j in range(n+2):
            if full_sol(x[i][j]) == 1:
                tour.append(j)
                break
    return tour

n = len(nodes)-2
x = qbpp.var("x", shape=(n+2, n+2))

constraint = qbpp.sum(qbpp.vector_sum(x, axis=1) == 1) + \
             qbpp.sum(qbpp.vector_sum(x, axis=0) == 1)

objective = qbpp.expr()
for i in range(n+1):
    next_i = i + 1
    for j in range(n+2):
        for k in range(n+2):
            if k != j:
                objective += distance(j, k, nodes) * x[i][j] * x[next_i][k]

P = 1000
f = objective + P*constraint 

start = 0
end = n + 1
ml = {}
# 位置0には都市0だけ
ml[x[start][start]] = 1
ml.update({x[i][start]: 0 for i in range(n+2) if i != start})
ml.update({x[start][j]: 0 for j in range(n+2) if j != start})
# 位置n+1には都市n+1だけ
ml[x[end][end]] = 1
ml.update({x[i][end]: 0 for i in range(n+2) if i != end})
ml.update({x[end][j]: 0 for j in range(n+2) if j != end})

g = qbpp.replace(f, ml)
g.simplify_as_binary()

solver = qbpp.ABS3Solver(g)
sol = solver.search(time_limit=30.0)

full_sol = qbpp.Sol(f).set(sol, ml)

tour = make_tour(full_sol)

print(f"Tour: {tour}")
print(f"energy: {full_sol(f)}")
print(f"constraint: {full_sol(constraint)}")
print(f"var_count: {sol.info['var_count']}")
print(f"term_count: {sol.info['term_count']}")

plot_tour(nodes, tour, "tsp_order")