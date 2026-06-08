import pyqbpp as qbpp
import math

nodes = [(10, 12),  (33, 125),  (12, 226),
         (121, 11), (108, 142), (111, 243)]

#nodes = [(10, 12),  (33, 125),  (12, 226),
#         (121, 11), (108, 142), (111, 243),
#         (220, 4),  (210, 113), (211, 233)]

N = len(nodes)-1 # nodes[1]~nodes[N]を訪問都市にしたいから-1する

nodes += [nodes[0]] # 出発点 = 終点

#nodes[0]：出発点(倉庫)
#nodes[1]~nodes[N]：訪問都市
#nodes[N+1]：終点(倉庫)

def distance(u,v):    
    dx = nodes[u][0] - nodes[v][0]
    dy = nodes[u][1] - nodes[v][1]

    return round(math.sqrt(dx*dx + dy*dy))


x = qbpp.var("x", shape=(N+2, N+2, N+1))

# 目的関数
obj = qbpp.sum([
    distance(u, v) * x[u][v][t]
    for u in range(0, N + 2)
    for v in range(0, N + 2)
    for t in range(0, N + 1)
])


#制約条件1　各都市から一回だけ出発する
constraint1 = qbpp.sum(
    qbpp.constrain(
        qbpp.vector_sum(
            qbpp.vector_sum(x[:N+1, 1:N+2, :], axis=2),
            axis=1
        ),
        equal=1
    )
)

#制約条件2　各都市に一回だけ訪問する
constraint2 = qbpp.sum(
    qbpp.constrain(
        qbpp.vector_sum(
            qbpp.vector_sum(x[:N+1, 1:N+2, :], axis=2),
            axis=0
        ),
        equal=1
    )
)

#制約条件3-1　一度出発した都市には戻らない
constraint3 = qbpp.sum([
    x[u][v][t] * x[w][u][j]
    for u in range(1, N + 2)
    for v in range(N + 2)
    for t in range(N + 1)
    for w in range(N + 2)
    for j in range(t + 1, N + 1)
])

P = 1000

f = obj + P*(constraint1 + constraint2 + constraint3)

ml = {}

for u in range(N + 2):
    for v in range(N + 2):
        for t in range(N + 1):
            if (
                u == N + 1      # 終点からは出ない
                or v == 0       # 出発点には入らない
                or u == v       # 自己ループ禁止
            ):
                ml[x[u][v][t]] = 0

g = qbpp.replace(f, ml)
g.simplify_as_binary()

solver = qbpp.ABS3Solver(g)
sol = solver.search(time_limit=60.0)

selected_edges = []

for t in range(0, N + 1):
    for u in range(0, N + 1):
        for v in range(1, N + 2):
            if u != v and sol(x[u][v][t]) == 1:
                selected_edges.append((t, u, v))
                print(f"t={t}: {u}->{v}")

selected_edges.sort()

tour = [0]
for t, u, v in selected_edges:
    tour.append(v)

print("Tour:", "->".join(map(str, tour)))
print("Distance:", sum(distance(tour[i], tour[i+1]) for i in range(len(tour)-1)))