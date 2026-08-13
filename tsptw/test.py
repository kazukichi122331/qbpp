import pyqbpp as qbpp

N = 5

x = qbpp.var("x", shape=(N+1, N+1))
w = qbpp.var("w", shape=N+1, between=(0, 10))

a = []

for i in range(N+1):
    a_i = qbpp.expr()

    for j in range(i):
        a_i += w[j]

    a.append(a_i)

time_constraint = qbpp.expr()

for i in range(N+1):
    time_constraint += (w[i] >= 0)

f = qbpp.cons(time_constraint)
f.simplify_as_binary()

solver = qbpp.ABS3Solver(f)
sol = solver.search(time_limit=1)

print("var_count =", sol.info["var_count"])

full_sol = qbpp.Sol(f)
full_sol.set(sol)

for i in range(N+1):
    print("w[{}] = {}".format(i, full_sol(w[i])))