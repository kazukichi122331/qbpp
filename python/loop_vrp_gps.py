import pyqbpp as qbpp
from nodes import nodes, distance
from plot_tour import plot_edges
from itertools import chain

N = len(nodes) - 2
R = 5
Q = 2

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
                    print(f"{i}->{j} ", end="")
        print("")
def vehicle_distance():
    L = [0 for _ in range(Q)]
    for q in range(Q):
        for i in range(0, N+1):
            for j in range(1, N+2):
                if i==j: continue
                if i==0 and j==N+1: continue
                L[q] += x[i][j][1][q]*distance(i,j,nodes)
    return L

x = qbpp.var("x", shape=(N+2, N+2, R, Q))
a = qbpp.var("a", shape=(N+2, N+2))
D = qbpp.var("D", between=(0,1000))
L = vehicle_distance()

objective = D
constraint01 = qbpp.expr()
constraint02 = qbpp.expr()
constraint03 = qbpp.expr()
constraint04 = qbpp.expr()
constraint05 = qbpp.expr()
constraint06 = qbpp.expr()
constraint07 = qbpp.expr()
constraint08 = qbpp.expr()
constraint09 = qbpp.expr()
constraint10 = qbpp.expr()

# constraint01: rは5状態のうち1つを選ぶ
for i in range(0, N+1):
    for j in range(1, N+2):
        for q in range(Q):
            if i == j:
                continue
            if i == 0 and j == N+1:
                continue
            c01 = 0
            for r in range(R):
                c01 += x[i][j][r][q]
            constraint01 += qbpp.constrain(c01, equal=1)
#constraint02 始点を出る
for q in range(Q):
    c02 = 0
    for j in range(1, N+2):
        if j==N+1: continue
        c02 += x[0][j][1][q]
    constraint02 += qbpp.constrain(c02, equal=1)
#constraint03 終点に行く
for q in range(Q):
    c03 = 0
    for i in range(1, N+1):
        c03 += x[i][N+1][1][q]
    constraint03 += qbpp.constrain(c03, equal=1)
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
#constraint06 どの車両から見ても訪問順序は同じ
for i in range(1, N+1):
    for j in range(1, N+1):
        if i==j: continue
        c06 = 0
        for q in range(Q):
            c06 += x[i][j][0][q] + x[i][j][1][q] + x[i][j][3][q]
        constraint06 += qbpp.constrain(c06- a[i][j]*Q, equal=0)
#constraint07 都市iから都市jに行ったら都市jは他の都市kに行かなければならない
for q in range(Q):
    for i in range(0, N+1):
        for j in range(1, N+1):
            if i==j: continue
            if i==0 and j==N+1: continue
            sum_k = 0
            for k in range(1, N+2):
                if j==k: continue
                sum_k += x[j][k][1][q]
            c07 = x[i][j][1][q]*(1-sum_k)
            constraint07 += qbpp.constrain(c07, equal=0)
#constraint08 訪問順序はi->jかj->iのいずれか
for i in range(0, N+1):
    for j in range(1, N+1):
        if i>=j: continue
        for q in range(Q):
            c_08 = (
                x[i][j][0][q]
                + x[i][j][1][q]
                + x[i][j][3][q]
                + x[j][i][0][q]
                + x[j][i][1][q]
                + x[j][i][3][q]
            )
            constraint08 += qbpp.constrain(c_08, equal=1)
#constraint09 部分巡回路はあってはいけない
for i in range(1, N+1):
    for j in range(1, N+1):
        for k in range(1, N+1):
            if i==j or j==k or k==i: continue
            constraint09 += a[i][j]*a[j][k] - a[i][j]*a[i][k] - a[j][k]*a[i][k] + a[i][k]
#constraint10 LqはD以下
for q in range(Q):
    constraint10 += qbpp.constrain(L[q] - D, between=(None, 0))

constraint = (
    constraint01
    + constraint02
    + constraint03
    + constraint04
    + constraint05
    + constraint06
    + constraint07
    + constraint08
    + constraint09
    + constraint10
)

P = 1000
f =  D + P*constraint

fixed_zero_vars = chain(
    # a のダミー部・対角
    (a[0][j] for j in range(N + 2)),
    (a[N + 1][j] for j in range(N + 2)),
    (a[i][0] for i in range(N + 2)),
    (a[i][N + 1] for i in range(N + 2)),
    (a[i][i] for i in range(N + 2)),

    # x の self-loop
    (x[i][i][r][q] for i in range(N + 2) for r in range(R) for q in range(Q)),

    # 始点に戻る辺は禁止
    (x[i][0][r][q] for i in range(N + 2) for r in range(R) for q in range(Q)),

    # 終点から出る辺は禁止
    (x[N + 1][j][r][q] for j in range(N + 2) for r in range(R) for q in range(Q)),

    # 0 -> N+1 を使わないなら禁止
    (x[0][N + 1][r][q] for r in range(R) for q in range(Q)),
)
ml = {}
ml.update({var: 0 for var in fixed_zero_vars})

g = qbpp.replace(f, ml)

f.simplify_as_binary()
g.simplify_as_binary()

solver = qbpp.ABS3Solver(g)

best_energy = 100000
best_sol = None
for loop in range(10):
    print(f"solve{loop+1}: ", end="")
    sol = solver.search(time_limit=1.0)
    solg = sol(g)
    print(f"energy={solg}")

    if solg < best_energy:
        best_energy = solg
        best_sol = sol

print(f"energy = {best_sol(g)}")
print(f"constraint = {best_sol(constraint)}")
for q in range(Q):
    print(f"L{q} = {best_sol(L[q])}")
print(f"var_count: {sol.info['var_count']}")
print(f"term_count: {sol.info['term_count']}")
print("")

edges = make_edges(best_sol)
plot_edges(nodes, edges, "minimax_gps")
print_edges(best_sol)