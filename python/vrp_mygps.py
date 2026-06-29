import pyqbpp as qbpp
from nodes import nodes, distance 
from plot_tour import plot_edges

N = len(nodes)-2
R = 5
Q = 2

def vehicle_distance():
    L = [0 for _ in range(Q)]
    for q in range(Q):
        for i in range(0, N+1):
            for j in range(1, N+2):
                if i==j: continue
                if i==0 and j==N+1: continue
                L[q] += x[i][j][1][q]*distance(i,j,nodes)
    return L

def make_edges(sol):
    edges = []
    for q in range(Q):
        for i in range(0, N+1):
            for j in range(1, N+2):
                if i==j: continue
                if i==0 and j==N+1: continue
                if sol(x[i][j][1][q]) == 1:
                    edges.append((i, j))
    return edges

def print_edges(sol):
    for q in range(Q):
        print(f"q={q}:")
        for i in range(0, N+1):
            for j in range(1, N+2):
                if i==j: continue
                if i==0 and j==N+1: continue
                if sol(x[i][j][1][q]) == 1:
                    print(f"{i}->{j}")
        print("")

x = qbpp.var("x", shape=(N+2, N+2, R, Q))
D = qbpp.var("D", between=(0,1000))
L = vehicle_distance()

objective = D

constraint01   = qbpp.expr()
constraint02_1 = qbpp.expr()
constraint02_2 = qbpp.expr()
constraint03_1 = qbpp.expr()
constraint03_2 = qbpp.expr()
constraint04   = qbpp.expr()
constraint05   = qbpp.expr()
constraint06   = qbpp.expr()
constraint07   = qbpp.expr()
constraint08   = qbpp.expr()
constraint09   = qbpp.expr()
constraint10   = qbpp.expr()

ml = {}

# constraint01 rは5状態のうち1つを選ぶ
for i in range(0, N+1):
    for j in range(1, N+2):
        for q in range(Q):
            if i==j: continue
            if i==0 and j==N+1: continue
            c01 = 0
            for r in range(R):
                c01 += x[i][j][r][q]
            constraint01 += qbpp.constrain(c01, equal=1)

#constraint02_1 始点を出る
for q in range(Q):
    c02_1 = 0
    for j in range(1, N+2):
        if j==N+1: continue
        c02_1 += x[0][j][1][q]
    constraint02_1 += qbpp.constrain(c02_1, equal=1)

#constraint02_2　始点に戻れない
#i,jの範囲を変えることで実現

#constraint03_1 終点に行く
for q in range(Q):
    c03_1 = 0
    for i in range(1, N+1):
        c03_1 += x[i][N+1][1][q]
    constraint03_1 += qbpp.constrain(c03_1, equal=1)

#constraint03_2 終点を出ない
#i,jの範囲を変えることで実現

#constraint04 出次数1
for i in range(1, N+1):
    c04 = 0
    for q in range(Q):
        for j in range(1, N+2):
            if i==j: continue
            c04 += x[i][j][1][q]
    constraint04 += qbpp.constrain(c04, equal=1)

#constraint05 入次数1
for j in range(1, N+1):
    c05 = 0
    for q in range(Q):
        for i in range(0, N+1):
            if i==j: continue
            if i==0 and j==N+1: continue
            c05 += x[i][j][1][q]
    constraint05 += qbpp.constrain(c05, equal=1)

constraint = (
    constraint01
    + constraint02_1
    + constraint02_2
    + constraint03_1
    + constraint03_2
    + constraint04
    + constraint05
    + constraint06
    + constraint07
    + constraint08
    + constraint09
    + constraint10
)

P = 1000

self_loop = qbpp.sum(
    [
        x[i][i][r][q]
        for i in range(N+2)
        for r in range(R)
        for q in range(Q)
    ]
)

f = objective + P*constraint + self_loop

ml.update(
    {
        x[i][i][r][q]: 0
        for i in range(N+2)
        for r in range(R)
        for q in range(Q)
    }
)


g = qbpp.replace(f, ml)

f.simplify_as_binary()
g.simplify_as_binary()

solver = qbpp.ABS3Solver(g)
sol = solver.search(time_limit=30.0)
full_sol = qbpp.Sol(f).set(sol, ml)

print(f"energy = {full_sol(f)}")
print(f"objective(D) = {full_sol(D)}")
print(f"constraint = {full_sol(constraint)}")


constraints = {
    "constraint01": constraint01,
    "constraint02_1": constraint02_1,
    "constraint02_2": constraint02_2,
    "constraint03_1": constraint03_1,
    "constraint03_2": constraint03_2,
    "constraint04": constraint04,
    "constraint05": constraint05,
    "constraint06": constraint06,
    "constraint07": constraint07,
    "constraint08": constraint08,
    "constraint09": constraint09,
    "constraint10": constraint10,
}

for name, expr in constraints.items():
    print(f"{name:15} = {full_sol(expr)}")
print(f"var_count: {sol.info['var_count']}")
print(f"term_count: {sol.info['term_count']}")

edges = make_edges(full_sol)
plot_edges(nodes, edges, "vrp_gps")
print_edges(full_sol)