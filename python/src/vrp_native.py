import pyqbpp as qbpp
from nodes import nodes, distance 
from plot_tour import plot_tour

n = len(nodes)-2
V = 3
T = n+1
x = qbpp.var("x", shape=(n+2, n+2, T, V))

def print_tour(full_sol):
    for v in range(V):
        route = []

        for t in range(T):
            for i in range(n+2):
                found = False

                for j in range(n+2):
                    if full_sol(x[i][j][t][v]) == 1:
                        if t == 0:
                            route.append(i)

                        route.append(j)
                        found = True
                        break

                if found:
                    break

        print(f"Vehicle {v}: {' -> '.join(map(str, route))}")

def v_tour_length(v):
    Lv = 0
    for i in range(n+2):
        for j in range(n+2):
            if i == j: continue
            for t in range(T):
                Lv += distance(i, j, nodes)*x[i][j][t][v]
    return Lv

i_constraint = qbpp.expr()
for i in range(1, n+1):
    ic = 0
    for j in range(0, n+2):
        if i == j: continue
        for t in range(T):
            for v in range(V):
                ic += x[i][j][t][v]
    i_constraint += qbpp.constrain(ic, equal=1)

j_constraint = qbpp.expr()
for j in range(1, n+1):
    jc = 0
    for i in range(0, n+2):
        if i == j: continue
        for t in range(T):
            for v in range(V):
                jc += x[i][j][t][v]
    j_constraint += qbpp.constrain(jc, equal=1)

v_constraint1 = qbpp.expr()
for v in range(V):
    vc1 = 0
    for j in range(1, n+1):
        vc1 += x[0][j][0][v]
    v_constraint1 += qbpp.constrain(vc1, equal=1)

v_constraint2 = qbpp.expr()
for v in range(V):
    vc2 = 0
    for i in range(n+1):
        for t in range(T):
            vc2 += x[i][n+1][t][v]
    v_constraint2 += qbpp.constrain(vc2, equal=1)

t_constraint = qbpp.expr()
for v in range(V):
    for t in range(T):
        tc = 0
        for i in range(n+2):
            for j in range(n+2):
                tc += x[i][j][t][v]
        t_constraint += qbpp.constrain(tc, equal=1)


route_constraint = qbpp.expr()

for v in range(V):
    for t in range(T - 1):
        for j in range(n + 2):
            arrive = 0
            depart = 0

            for i in range(n + 2):
                arrive += x[i][j][t][v]

            for k in range(n + 2):
                depart += x[j][k][t + 1][v]

            route_constraint += qbpp.constrain(arrive - depart, equal=0)

L0 = v_tour_length(0)

objective = L0

minimax_constraint = qbpp.expr()
for v in range(1, V):
    minimax_constraint += qbpp.constrain(v_tour_length(v) - L0, between=(None, 0))

P = 100000
f = objective + P * (
    i_constraint
    + j_constraint
    + v_constraint1
    + v_constraint2
    + t_constraint
    + route_constraint
    + minimax_constraint
)

ml = {}

for q in range(V):
    for t in range(T):

        # 自己ループ禁止
        for i in range(n+1):
            ml[x[i][i][t][q]] = 0

        # 終点から出発禁止
        for j in range(n+1):
            ml[x[n+1][j][t][q]] = 0

        # 始点への到着禁止
        for i in range(1, n+2):
            ml[x[i][0][t][q]] = 0

    # 時刻0はデポからしか出発できない
    for i in range(1, n+2):
        for j in range(n+2):
            ml[x[i][j][0][q]] = 0

    # 最終時刻は終点へ行く辺だけ許可
    for i in range(n+1):
        for j in range(n+1):
            ml[x[i][j][T-1][q]] = 0

g = qbpp.replace(f, ml)
f.simplify_as_binary()
g.simplify_as_binary()

solver = qbpp.ABS3Solver(g)
sol = solver.search(time_limit=60.0)

full_sol = qbpp.Sol(f).set(sol, ml)

print(f"energy = {full_sol(f)}")
print(f"i_constraint = {full_sol(i_constraint)}")
print(f"j_constraint = {full_sol(j_constraint)}")
print(f"t_constraint = {full_sol(t_constraint)}")
print(f"v_constraint1 = {full_sol(v_constraint1)}")
print(f"v_constraint2 = {full_sol(v_constraint2)}")
print(f"route_constraint = {full_sol(route_constraint)}")
print(f"minimax_constraint = {full_sol(minimax_constraint)}")
print(f"var_count: {sol.info['var_count']}")
print(f"term_count: {sol.info['term_count']}")
print(f"gpu_flip: {sol.info['gpu_flip_count']}")
print_tour(full_sol)

for v in range(V):
    Lv = full_sol(v_tour_length(v))
    print(f"L{v} = {Lv}")

for v in range(1,V):
    diff = full_sol(v_tour_length(v)-L0)
    print(f"diff{v} = {diff}")