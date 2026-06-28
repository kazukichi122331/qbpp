#energy = 6823
#objective(D) = 823
#constraint = 6
#constraint01    = 0
#constraint02_1  = 1
#constraint02_2  = 0
#constraint03_1  = 1
#constraint03_2  = 0
#constraint04    = 0
#constraint05    = 0
#constraint06    = 2
#constraint07    = 2
#constraint08    = 0
#constraint09    = 0
#constraint10    = 0
#var_count: 930
#term_count: 24989
#q=0:
#0->8
#1->6
#3->5
#4->7
#5->1
#7->4
#8->3
#
#q=1:
#2->10
#6->9
#9->2

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

#constraint02_1 すべての車両は始点を出発する
for q in range(Q):
    c02_1 = 0
    for j in range(1, N+2):
        if j==N+1: continue
        c02_1 += x[0][j][1][q]
    constraint02_1 += qbpp.constrain(c02_1, equal=1)

#constraint02_2 どの都市からも始点に出発できない
#i,jの範囲を変えることで実現

#constraint03_1 すべての車両は終点に到達する
for q in range(Q):
    c03_1 = 0
    for i in range(1, N+1):
        c03_1 += x[i][N+1][1][q]
    constraint03_1 += qbpp.constrain(c03_1, equal=1)

#constraint03_2 終点からはどの都市にも出発しない
#i,jの範囲を変えることで実現

#constraint04 すべての都市において出発できるのは一回だけ
for i in range(1, N+1):
    c04 = 0
    for q in range(Q):
        for j in range(1, N+2):
            if i==j: continue
            c04 += x[i][j][1][q]
    constraint04 += qbpp.constrain(c04, equal=1)

#constraint05 すべての都市において訪問できるのは一回だけ
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
        if i==0 and j==N+1: continue
        for q in range(Q-1):
            c06 = (
                (x[i][j][0][q]+x[i][j][1][q]+x[i][j][3][q])
                - (x[i][j][0][q+1]+x[i][j][1][q+1]+x[i][j][3][q+1])
            )
            constraint06 += qbpp.constrain(c06, equal=0)

#constraint07 都市iから都市jに行ったら都市jは他の都市kに行かなければならない
#for i in range(0, N+1):
#    for j in range(1, N+2):
#        if i==j: continue
#        if i==0 and j==N+1: continue
#        for q in range(Q):
#            sum_k = 0
#            for k in range(1, N+2):
#                if j==k: continue
#                sum_k += x[j][k][1][q]
#            c07 = x[i][j][1][q]*(1-sum_k)
#            constraint07 += qbpp.constrain(c07, equal=0)
for q in range(Q):
    for j in range(1, N+1):      # 顧客のみ
        incoming = 0
        outgoing = 0

        # jに入る辺
        for i in range(0, N+1):
            if i == j:
                continue
            incoming += x[i][j][1][q]

        # jから出る辺
        for k in range(1, N+2):
            if k == j:
                continue
            outgoing += x[j][k][1][q]

        constraint07 += qbpp.constrain(
            incoming - outgoing,
            equal=0
        )

#constraint08 訪問順序はi->jかj->iのいずれか
for i in range(1, N+1):
    for j in range(i+1, N+1):
        c_08 = (
            x[i][j][0][1]
            + x[i][j][1][1]
            + x[i][j][3][1]
            + x[j][i][0][1]
            + x[j][i][1][1]
            + x[j][i][3][1]
        )
        constraint08 += qbpp.constrain(c_08, equal=1)

#constraint09 部分巡回路はあってはいけない
for i in range(1, N+1):
    for j in range(1, N+1):
        for k in range(1, N+1):
            if i==j and j==k and k==i: continue
            a_ij = x[i][j][0][1] + x[i][j][1][1] + x[i][j][3][1]
            a_jk = x[j][k][0][1] + x[j][k][1][1] + x[j][k][3][1]
            a_ik = x[i][k][0][1] + x[i][k][1][1] + x[i][k][3][1]
            constraint09 += a_ij*a_jk - a_ij*a_ik - a_jk*a_ik + a_ik*a_ik

#constraint10 LqはD以下
for q in range(Q):
    constraint10 += qbpp.constrain(L[q] - D, between=(None, 0))

constraint = (
    10*constraint01
    + constraint02_1
    + constraint02_2
    + constraint03_1
    + constraint03_2
    + 10*constraint04
    + 10*constraint05
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
sol = solver.search(time_limit=100.0)
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