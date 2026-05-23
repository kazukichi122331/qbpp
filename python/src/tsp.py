import pyqbpp as qbpp
import matplotlib.pyplot as plt
import math

nodes = [(10, 12),  (33, 125),  (12, 226),
         (121, 11), (108, 142), (111, 243),
         (220, 4),  (210, 113), (211, 233)]

def distance(i, j):
    dx = nodes[i][0] - nodes[j][0]
    dy = nodes[i][1] - nodes[j][1]

    return round(math.sqrt(dx*dx + dy*dy))

n = len(nodes)
x = qbpp.var("x", shape=(n, n))
y = qbpp.var("y", shape=n, between=(0, n-1))

constraint1 = qbpp.sum( qbpp.constrain( qbpp.vector_sum( x, axis=1 ), equal=1 ) ) + \
              qbpp.sum( qbpp.constrain( qbpp.vector_sum( x, axis=0 ), equal=1 ) )


constraint2 = qbpp.sum([
    qbpp.constrain(y[i] - y[j] + n * x[i][j], between=(None, n-1))
    for i in range(1, n) for j in range(1, n) if i != j
])

constraint3 = qbpp.sum([qbpp.constrain(x[i][i], equal=0) for i in range(n)])

constraint = 100000*(constraint1 + constraint2 + constraint3)

obj = qbpp.sum([distance(i, j) * x[i][j] for i in range(n) for j in range(n)])

f = obj + constraint
f.simplify_as_binary()


solver = qbpp.EasySolver(f)
sol = solver.search(time_limit=600.0, target_energy=959)


print("energy:", sol(f))
print("min distance", sol(obj))
print("constraint  = ", sol(constraint ))
print("constraint1 = ", sol(constraint1))
print("constraint2 = ", sol(constraint2))
print("constraint3 = ", sol(constraint3))

    # 1. グラフの土台を準備
plt.figure(figsize=(8, 8))
plt.title("TSP Result Visualizer", fontsize=14, fontweight="bold")
plt.xlabel("X Coordinate", fontsize=10)
plt.ylabel("Y Coordinate", fontsize=10)
plt.grid(True, linestyle="--", alpha=0.5)

# 2. 都市（ノード）をプロット
X_coords = [node[0] for node in nodes]
Y_coords = [node[1] for node in nodes]
plt.scatter(X_coords, Y_coords, color="red", s=150, zorder=3, label="Cities")

# 各都市に番号（0〜8）のみをラベルとして表示
for i, (x_coord, y_coord) in enumerate(nodes):
    label_text = f"City {i}"
    
    plt.text(x_coord + 4, y_coord + 4, label_text, fontsize=9, 
             fontweight="bold", bbox=dict(facecolor='white', alpha=0.7, boxstyle='round,pad=0.3'))

# 3. ソルバーが選んだエッジ（矢印）を描画
arrow_count = 0
for i in range(n):
    for j in range(n):
        if sol(x[i][j]) == 1:
            start_pos = nodes[i]
            end_pos = nodes[j]
            
            # 矢印を描画（少しだけ手前で止まるように調整して見やすくしています）
            plt.annotate(
                "", 
                xy=end_pos, 
                xytext=start_pos,
                arrowprops=dict(
                    arrowstyle="->", 
                    color="blue", 
                    lw=2.5, 
                    ls="-" if i != j else "--", # 自己ループがあれば破線（今回は0ですが一応）
                    mutation_scale=20, # 矢印の頭の大きさ
                    connectionstyle="arc3,rad=0.1" # 往復のエッジが重ならないように少し曲げる
                )
            )
            arrow_count += 1

# グラフの表示範囲を少し広げて見やすく調整
plt.xlim(min(X_coords) - 30, max(X_coords) + 40)
plt.ylim(min(Y_coords) - 30, max(Y_coords) + 40)

plt.legend(loc="upper left")
plt.savefig("tsp_result.png", dpi=300, bbox_inches="tight")
plt.close()