import os
import numpy as np
import matplotlib.pyplot as plt
from scipy.optimize import least_squares


def recover_coordinates(c):
    N = len(c)

    coords = np.zeros((N, 2))

    # デポを (0, 0) に固定
    coords[0] = [0.0, 0.0]

    # 顧客1を x 軸上に固定
    coords[1] = [float(c[0][1]), 0.0]

    # 初期値
    for u in range(2, N):
        r = c[0][u]
        theta = 2 * np.pi * (u - 2) / (N - 2)

        coords[u] = [
            r * np.cos(theta),
            r * np.sin(theta)
        ]

    # 距離行列に合うように座標を調整
    def residual(z):
        xy = coords.copy()
        xy[2:] = z.reshape(-1, 2)

        errors = []

        for i in range(N):
            for j in range(i + 1, N):
                distance = np.linalg.norm(xy[i] - xy[j])
                errors.append(distance - c[i][j])

        return errors

    result = least_squares(
        residual,
        coords[2:].reshape(-1)
    )

    coords[2:] = result.x.reshape(-1, 2)

    return coords

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

    # その他の都市
    for i, (px, py) in enumerate(nodes):
        if arrival_times[i] - due_times[i] > 0:
            plt.scatter(
                px,
                py,
                s=250,
                facecolors="red",
                edgecolors="black",
                zorder=3
            )
        else:
            plt.scatter(
                px,
                py,
                s=250,
                facecolors="white",
                edgecolors="black",
                zorder=3
            )

    # デポ(都市0)
    plt.scatter(
        nodes[0][0],
        nodes[0][1],
        s=250,
        facecolors="lightgreen",  # 好きな色
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
        if arrival_times[i] - due_times[i] > 0:
            plt.text(
                px,
                py - 2.0,
                f"{arrival_times[i]}\n[0, {due_times[i]}]",
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
        else:
            plt.text(
                px,
                py - 2.0,
                f"{arrival_times[i]}",
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
            fontsize=10,
            color="black",
            ha="center",
            va="center",
            bbox=dict(
                facecolor="none",
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