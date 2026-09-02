import pyqbpp as qbpp

x = qbpp.var("x", shape=(5, 5))
y = qbpp.var("y", shape=5, between=(0,10))

constraint = qbpp.expr()
for i in range(5):
    sum_row = 0
    for j in range(5):
        sum_row += x[i][j]
    constraint += (sum_row - y[i] == 0)

f = constraint

ml = {x[i][i]: 0 for i in range(5)}
g = qbpp.replace(f, ml)
f = qbpp.simplify_as_binary(f)
g = qbpp.simplify_as_binary(g)

solver = qbpp.EasySolver(g)
sol = solver.search()

full_sol = qbpp.Sol(f).set(sol, ml)
full_sol.comp_energy()

print(full_sol(f))