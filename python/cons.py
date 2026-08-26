import pyqbpp as qbpp

x = qbpp.var("x")
y = qbpp.var("y")
z = qbpp.var("z")

f = x + y
g = y + z

one_cons = qbpp.cons(f + g == 2)
two_cons = qbpp.cons(f == 1) + qbpp.cons(g == 1)

bad_sol = qbpp.Sol(x + y + z).set({
    x: 1,
    y: 1,
    z: 0,
})

print("x =", bad_sol[x])
print("y =", bad_sol[y])
print("z =", bad_sol[z])

print()
print("=== one_cons ===")
print("energy =", bad_sol(one_cons))
print("cons =", one_cons.cons(bad_sol))
print("violations =", one_cons.violations(bad_sol))

print()
print("=== two_cons ===")
print("energy =", bad_sol(two_cons))
print("cons =", two_cons.cons(bad_sol))
print("violations =", two_cons.violations(bad_sol))