import matplotlib.pyplot as plt

def plot_tour(nodes, tour, filename):
    """
    巡回順序tourを矢印付きで描画する。

    tourが最後に始点を含んでいない場合だけ、
    始点を追加して巡回路を閉じる。
    """
    if not tour:
        print("Tour is empty.")
        return

    if tour[-1] == tour[0]:
        closed_tour = tour
    else:
        closed_tour = tour + [tour[0]]

    plt.figure(figsize=(8, 8))

    # 都市を白丸で描画
    xs_nodes = [p[0] for p in nodes]
    ys_nodes = [p[1] for p in nodes]

    plt.scatter(
        xs_nodes,
        ys_nodes,
        s=250,
        facecolors="white",
        edgecolors="black",
        zorder=3
    )

    # すべての都市番号を表示
    for i, (px, py) in enumerate(nodes):
        plt.text(
            px,
            py,
            str(i),
            fontsize=12,
            ha="center",
            va="center",
            zorder=4
        )

    # 赤い矢印で巡回路を描画
    for a, b in zip(closed_tour[:-1], closed_tour[1:]):
        x1, y1 = nodes[a]
        x2, y2 = nodes[b]

        plt.annotate(
            "",
            xy=(x2, y2),
            xytext=(x1, y1),
            arrowprops=dict(
                arrowstyle="->",
                color="red",
                lw=2,
                shrinkA=15,
                shrinkB=15
            ),
            zorder=2
        )

    plt.title(filename)
    plt.grid(True)
    plt.axis("equal")

    # 軸の目盛りを消す
    plt.xticks([])
    plt.yticks([])

    plt.tight_layout()
    plt.savefig(
        f"results/{filename}.png",
        dpi=150,
        bbox_inches="tight"
    )
    plt.close()

def plot_edges(nodes, edges, filename):
    plt.figure(figsize=(8, 8))

    plot_nodes = nodes[:-1]
    # ノードを白丸で描画
    xs_nodes = [p[0] for p in plot_nodes]
    ys_nodes = [p[1] for p in plot_nodes]

    plt.scatter(
        xs_nodes,
        ys_nodes,
        s=250,
        facecolors="white",
        edgecolors="black",
        zorder=3
    )

    # 都市番号をノードの真ん中に表示
    for i, (x, y) in enumerate(plot_nodes):
        plt.text(
            x, y, str(i),
            fontsize=12,
            ha="center",
            va="center",
            zorder=4
        )

    # 選ばれた辺を全部描画
    for i, j in edges:
        x1, y1 = nodes[i]
        x2, y2 = nodes[j]

        plt.annotate(
            "",
            xy=(x2, y2),
            xytext=(x1, y1),
            arrowprops=dict(
                arrowstyle="->",
                color="red",
                lw=2,
                shrinkA=15,
                shrinkB=15
            ),
            zorder=2
        )

    plt.title(f"{filename}")
    plt.xlabel("")
    plt.ylabel("")
    plt.grid(True)
    plt.axis("equal")

    # 軸の目盛りを消す
    plt.xticks([])
    plt.yticks([])

    plt.savefig(f"results/{filename}.png")
    plt.close()


def plot_order_edges(nodes, edges, filename):
    plt.figure(figsize=(8, 8))

    plot_nodes = nodes
    # ノードを白丸で描画
    xs_nodes = [p[0] for p in plot_nodes]
    ys_nodes = [p[1] for p in plot_nodes]

    plt.scatter(
        xs_nodes,
        ys_nodes,
        s=250,
        facecolors="white",
        edgecolors="black",
        zorder=3
    )

    # 都市番号をノードの真ん中に表示
    for i, (x, y) in enumerate(plot_nodes):
        plt.text(
            x, y, str(i),
            fontsize=12,
            ha="center",
            va="center",
            zorder=4
        )

    # 選ばれた辺を全部描画
    for i, j in edges:
        x1, y1 = nodes[i]
        x2, y2 = nodes[j]

        plt.annotate(
            "",
            xy=(x2, y2),
            xytext=(x1, y1),
            arrowprops=dict(
                arrowstyle="->",
                color="red",
                lw=2,
                shrinkA=15,
                shrinkB=15
            ),
            zorder=2
        )

    plt.title(f"{filename}")
    plt.xlabel("")
    plt.ylabel("")
    plt.grid(True)
    plt.axis("equal")

    # 軸の目盛りを消す
    plt.xticks([])
    plt.yticks([])

    plt.savefig(f"results/{filename}.png")
    plt.close()