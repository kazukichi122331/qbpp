import pyqbpp as qbpp
from nodes import nodes, distance 
from plot_tour import plot_edges

N = len(nodes)-2
I = N+2
J = N+2
R = 5
Q = 2
x = qbpp.var("x", shape=(I, J, R, Q))
a = qbpp.var("a", shape=(N+2, N+2))

def make_edges(sol):
    edges = []
    for i in range(0, N+1):
        for j in range(1, N+2):
            if i == j:
                continue
            for q in range(Q):
                if sol(x[i][j][1][q]) == 1:
                    edges.append((i, j))
    return edges

vehicle_distance = []
for q in range(Q):
    dist_q = qbpp.expr()

    for i in range(I):
        for j in range(J):
            if i == j:
                continue

            dist_q += distance(i,j,nodes) * x[i][j][1][q]

    vehicle_distance.append(dist_q)

onehot_constraint = qbpp.expr()
for i in range(I):
    for j in range(J):
        if i == j: continue
        for q in range(Q):
            ohc = (
                x[i][j][0][q]
                + x[i][j][1][q]
                + x[i][j][2][q]
                + x[i][j][3][q]
                + x[i][j][4][q]
            )
            onehot_constraint += qbpp.constrain(ohc, equal=1)

startpos_constraint = qbpp.expr()
for q in range(Q):
    spc = 0
    for j in range(1, J):
        spc += x[0][j][1][q]
    startpos_constraint += qbpp.constrain(spc, equal=1)

return_constraint = qbpp.expr()
for q in range(Q):
    rc = 0
    for i in range(1, I):
        rc += x[i][0][1][q]
    return_constraint += qbpp.constrain(rc, equal=0)

finalpos_constraint = qbpp.expr()
for q in range(Q):
    fpc = 0
    for i in range(0, I-1):
        fpc += x[i][N+1][1][q]
    finalpos_constraint += qbpp.constrain(fpc, equal=1)

leave_constraint = qbpp.expr()
for q in range(Q):
    lc = 0
    for j in range(J-1):
        lc += x[N+1][j][1][q]
    leave_constraint += qbpp.constrain(lc, equal=0)

leaveonce_constraint = qbpp.expr()
for i in range(1, N+1):
    loc = 0
    for q in range(Q):
        for j in range(1, J):
            if i == j: continue
            loc += x[i][j][1][q]
    leaveonce_constraint += qbpp.constrain(loc, equal=1)

arriveonce_constraint = qbpp.expr()
for j in range(1, N+1):
    aoc = 0
    for q in range(Q):
        for i in range(0, I-1):
            if i == j: continue
            aoc += x[i][j][1][q]
    arriveonce_constraint += qbpp.constrain(aoc, equal=1)

order_constraint = qbpp.expr()
for i in range(1, I-1):
    for j in range(1, J-1):
        if i == j: continue
        oc = 0
        for q in range(Q):
            oc += x[i][j][0][q] + x[i][j][1][q] + x[i][j][3][q]
        order_constraint += qbpp.constrain(oc - Q*a[i][j], equal=0)

flow_constraint = qbpp.expr()
for i in range(0, I-1):
    for j in range(1, J-1):
        if i == j: continue
        for q in range(Q):
            flow = 0
            for k in range(1, N+2):
                if k == j: continue
                flow += x[j][k][1][q]
            fc = x[i][j][1][q]*(1-flow)
            flow_constraint += qbpp.constrain(fc, equal=0)

precedence_constraint = qbpp.expr()
for i in range(0, I-1):
    for j in range(i+1, J-1):
        for q in range(Q):
            precedence_constraint += qbpp.constrain(
                x[i][j][0][q]
                + x[i][j][1][q]
                + x[i][j][3][q]
                + x[j][i][0][q]
                + x[j][i][1][q]
                + x[j][i][3][q]
                - 1,
                equal=0
            )

transitivity_constraint = qbpp.expr()
for i in range(1, I-1):
    for j in range(1, J-1):
        if i==j: continue
        for k in range(1, N+1):
            if k == i or k == j: continue
            transitivity_constraint += (
                a[i][j]*a[j][k]
                - a[i][j]*a[i][k]
                - a[j][k]*a[i][k]
                + a[i][k]*a[i][k]
            )


distance_balance_constraint = qbpp.expr()

for q in range(1, Q):
    distance_balance_constraint += qbpp.constrain(
        vehicle_distance[q] - vehicle_distance[0],
        between=(None, 0)
    )

D = vehicle_distance[0]
objective = D

constraint = (
    onehot_constraint
    + startpos_constraint
    + return_constraint
    + finalpos_constraint
    + leave_constraint
    + leaveonce_constraint
    + arriveonce_constraint
    + order_constraint
    + flow_constraint
    + precedence_constraint
    + transitivity_constraint
    + distance_balance_constraint
)

P = 1000
f = objective + P*constraint

f.simplify_as_binary()

solver = qbpp.ABS3Solver(f)
sol = solver.search(time_limit=10.0)

print(f"energy = {sol(f)}")
print(f"objective = {sol(objective)}")
print(f"constraint = {sol(constraint)}")
print(f"onehot_constraint = {sol(onehot_constraint)}")
print(f"startpos_constraint = {sol(startpos_constraint)}")
print(f"return_constraint = {sol(return_constraint)}")
print(f"finalpos_constraint = {sol(finalpos_constraint)}")
print(f"leave_constraint = {sol(leave_constraint)}")
print(f"leaveonce_constraint = {sol(leaveonce_constraint)}")
print(f"arriveonce_constraint = {sol(arriveonce_constraint)}")
print(f"order_constraint = {sol(order_constraint)}")
print(f"flow_constraint = {sol(flow_constraint)}")
print(f"precedence_constraint = {sol(precedence_constraint)}")
print(f"transitivity_constraint = {sol(transitivity_constraint)}")
print(f"distance_balance_constraint = {sol(distance_balance_constraint)}")
print(f"var_count: {sol.info['var_count']}")
print(f"term_count: {sol.info['term_count']}")


plot_edges(nodes, make_edges(sol), "vrp_gps")