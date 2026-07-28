import os
import matplotlib.pyplot as plt


def plot_tour(
    nodes,
    tour,
    arrival_times,
    due_times,
    travel_time,
    filename
):
    # 保存先が存在しない場合は作成
    os.makedirs("results", exist_ok=True)

    plt.figure(figsize=(8, 8))

    # 都市の座標
    xs_nodes = [p[0] for p in nodes]
    ys_nodes = [p[1] for p in nodes]

    # 都市を白丸で描画
    plt.scatter(
        xs_nodes,
        ys_nodes,
        s=250,
        facecolors="white",
        edgecolors="black",
        zorder=3
    )

    # すべての都市番号、到着時刻、締切時刻を表示
    for i, (px, py) in enumerate(nodes):
        # 都市番号
        plt.text(
            px,
            py,
            str(i),
            fontsize=12,
            ha="center",
            va="center",
            zorder=4
        )

        # 到着時刻と締切時刻
        plt.text(
            px + 0.4,
            py,
            f"arr={arrival_times[i]}\ndue={due_times[i]}",
            fontsize=10,
            color="blue",
            ha="center",
            va="top",
            bbox=dict(
                facecolor="white",
                alpha=0.8,
                edgecolor="none"
            ),
            zorder=4
        )

    # 赤い矢印で巡回路を描画
    for a, b in zip(tour[:-1], tour[1:]):
        x1, y1 = nodes[a]
        x2, y2 = nodes[b]

        cost = travel_time[a][b]

        # 辺の中点
        mx = (x1 + x2) / 2
        my = (y1 + y2) / 2

        # 移動時間を表示
        plt.text(
            mx,
            my,
            str(cost),
            fontsize=15,
            color="black",
            ha="center",
            va="center",
            bbox=dict(
                facecolor="white",
                alpha=0.7,
                edgecolor="none"
            ),
            zorder=5
        )

        # 巡回方向を矢印で表示
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

    plt.grid(True)
    plt.axis("equal")

    # 軸の目盛りを消す
    plt.xticks([])
    plt.yticks([])

    plt.tight_layout()

    # 個別ファイルとして保存
    plt.savefig(
        f"results/{filename}.png",
        dpi=150,
        bbox_inches="tight"
    )

    # 最新結果として固定名でも保存
    plt.savefig(
        "results/tsptw.png",
        dpi=150,
        bbox_inches="tight"
    )

    plt.close()