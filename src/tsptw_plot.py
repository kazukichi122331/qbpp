import os
import shutil

import numpy as np
import matplotlib.pyplot as plt
from scipy.optimize import least_squares
from scipy.sparse import csr_matrix

# 出力先（呼び出し側が results/<filename>.png を前提にしている）
RESULTS_DIR = "results"
LATEST_NAME = "tsptw"

# 描画パラメータ（都市数 20 を基準サイズとする）
BASE_N = 20
MIN_SCALE = 0.30
MARKER_SIZE = 250.0     # scatter の s（面積, pt^2）
NODE_FONTSIZE = 12.0    # 都市番号
INFO_FONTSIZE = 10.0    # 到着時刻・時間枠
COST_FONTSIZE = 10.0    # 辺の移動時間
ARROW_SHRINK = 15.0     # 矢印の始点/終点をマーカー分だけ縮める量(pt)


def _draw_scale(n):
    """都市数に応じた描画倍率。n<=BASE_N なら 1.0（従来の見た目）。"""
    if n <= BASE_N:
        return 1.0

    return max(MIN_SCALE, np.sqrt(BASE_N / n))


def recover_coordinates(c):
    """距離行列 c から 2 次元座標 (N, 2) を復元する。

    デポを (0, 0)、顧客 1 を x 軸上に固定し、残りの点を最小二乗で当てはめる。
    初期値には古典的 MDS を使う（ユークリッド距離行列なら厳密解になる）。
    """
    d = np.asarray(c, dtype=float)
    n = d.shape[0] if d.ndim == 2 else 0

    if n == 0:
        return np.zeros((0, 2))

    # 数値誤差・非対称性を除いておく
    d = 0.5 * (d + d.T)
    np.fill_diagonal(d, 0.0)

    coords = np.zeros((n, 2))

    if n == 1:
        return coords

    # デポを (0, 0)、顧客 1 を x 軸上に固定
    coords[1] = [d[0, 1], 0.0]

    if n == 2:
        return coords

    # 初期値: 古典的 MDS（Gram 行列の上位 2 固有ベクトル）
    coords[2:] = _classical_mds(d)[2:]

    # 上三角の全ペア（residual の並びは従来と同じ i<j の行優先）
    iu, ju = np.triu_indices(n, k=1)
    target = d[iu, ju]

    # 未知パラメータは coords[2:] のみ。ヤコビアンの非零位置を先に作る
    idx_i = np.flatnonzero(iu >= 2)
    idx_j = np.flatnonzero(ju >= 2)

    col_i = 2 * (iu[idx_i] - 2)
    col_j = 2 * (ju[idx_j] - 2)

    rows = np.concatenate([np.repeat(idx_i, 2), np.repeat(idx_j, 2)])
    cols = np.concatenate([
        np.stack([col_i, col_i + 1], axis=1).ravel(),
        np.stack([col_j, col_j + 1], axis=1).ravel(),
    ])

    shape = (target.size, 2 * (n - 2))

    # 作業用配列は使い回す（残差評価ごとに確保しない）
    xy = coords.copy()

    def _distances(z):
        xy[2:] = z.reshape(-1, 2)
        diff = xy[iu] - xy[ju]

        return diff, np.sqrt(np.einsum("ij,ij->i", diff, diff))

    def residual(z):
        return _distances(z)[1] - target

    def jacobian(z):
        diff, dist = _distances(z)

        # 同一点に重なった場合のゼロ除算を避ける
        unit = diff / np.maximum(dist, 1e-12)[:, None]

        data = np.concatenate([unit[idx_i].ravel(), -unit[idx_j].ravel()])

        return csr_matrix((data, (rows, cols)), shape=shape)

    result = least_squares(
        residual,
        coords[2:].reshape(-1),
        jac=jacobian,
        tr_solver="lsmr"
    )

    coords[2:] = result.x.reshape(-1, 2)

    return coords


def _classical_mds(d):
    """距離行列 d の古典的 MDS 配置を、デポ原点・顧客 1 を +x 軸上に正規化して返す。"""
    n = d.shape[0]

    # 二重中心化した Gram 行列
    sq = d ** 2
    b = -0.5 * (
        sq
        - sq.mean(axis=0, keepdims=True)
        - sq.mean(axis=1, keepdims=True)
        + sq.mean()
    )

    values, vectors = np.linalg.eigh(b)

    # 大きい方から 2 つ（負の固有値は 0 に丸める）
    top = np.argsort(values)[::-1][:2]
    xy = vectors[:, top] * np.sqrt(np.maximum(values[top], 0.0))

    # デポを原点へ
    xy = xy - xy[0]

    # 顧客 1 を +x 軸上へ回転
    length = np.hypot(*xy[1])
    if length > 0:
        cos, sin = xy[1] / length
        rotation = np.array([[cos, sin], [-sin, cos]])
        xy = xy @ rotation.T

    # 鏡像の自由度は残るので、結果が再現するように符号を固定
    if xy[2:, 1].sum() < 0:
        xy[:, 1] = -xy[:, 1]

    return xy


def plot_tour(
    nodes,
    tour,
    ready_times,
    wait_times,
    arrival_times,
    due_times,
    travel_time,
    filename
):
    """巡回路を描画して results/<filename>.png と results/tsptw.png に保存する。"""
    nodes = np.asarray(nodes, dtype=float).reshape(-1, 2)
    n = len(nodes)

    # 保存先が存在しない場合は作成
    os.makedirs(RESULTS_DIR, exist_ok=True)

    fig, ax = plt.subplots(figsize=(8, 8))

    scale = _draw_scale(n)

    marker_size = MARKER_SIZE * scale ** 2
    node_fontsize = NODE_FONTSIZE * scale
    info_fontsize = INFO_FONTSIZE * scale
    cost_fontsize = COST_FONTSIZE * scale

    # マーカー半径(pt)。テキストや矢印のオフセットをこれに合わせる
    marker_radius = np.sqrt(marker_size / np.pi)

    if n:
        # 時間枠違反（締切より遅い到着）を赤で塗る
        violated = np.array([
            arrival_times[i] > due_times[i] for i in range(n)
        ])

        for mask, color in ((~violated, "white"), (violated, "red")):
            if mask.any():
                ax.scatter(
                    nodes[mask, 0],
                    nodes[mask, 1],
                    s=marker_size,
                    facecolors=color,
                    edgecolors="black",
                    zorder=3
                )

        # デポ(都市0)は上書きして色を変える
        ax.scatter(
            nodes[0, 0],
            nodes[0, 1],
            s=marker_size,
            facecolors="lightgreen",
            edgecolors="black",
            zorder=3
        )

    # すべての都市番号、到着時刻、締切時刻を表示
    for i, (px, py) in enumerate(nodes):
        # 都市番号
        ax.text(
            px,
            py,
            str(i),
            fontsize=node_fontsize,
            ha="center",
            va="center",
            zorder=4
        )

        # 到着時刻と締切時刻（座標のスケールに依存しない pt 単位でずらす）
        ax.annotate(
            f"{arrival_times[i]}+{wait_times[i]}\n[{ready_times[i]}, {due_times[i]}]",
            xy=(px, py),
            xytext=(0, -(marker_radius + 3.0)),
            textcoords="offset points",
            fontsize=info_fontsize,
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

        # 辺の法線方向へずらして、矢印と重ならないようにする
        # （a->b と b->a が両方ある場合も互いに反対側へ逃げる）
        dx, dy = x2 - x1, y2 - y1
        length = np.hypot(dx, dy)

        if length > 0:
            offset = (-dy / length, dx / length)
        else:
            offset = (0.0, 1.0)

        # 移動時間を表示
        ax.annotate(
            str(cost),
            xy=(mx, my),
            xytext=(offset[0] * 8.0, offset[1] * 8.0),
            textcoords="offset points",
            fontsize=cost_fontsize,
            color="black",
            ha="center",
            va="center",
            bbox=dict(
                facecolor="white",
                alpha=0.75,
                edgecolor="none",
                pad=1.0
            ),
            zorder=5
        )

        # 巡回方向を矢印で表示
        ax.annotate(
            "",
            xy=(x2, y2),
            xytext=(x1, y1),
            arrowprops=dict(
                arrowstyle="->",
                color="red",
                lw=2 * max(scale, 0.5),
                shrinkA=marker_radius + 4.0,
                shrinkB=marker_radius + 4.0
            ),
            zorder=2
        )

    # 総移動時間と違反数を見出しに出す
    total = sum(travel_time[a][b] for a, b in zip(tour[:-1], tour[1:]))
    violations = sum(
        1 for i in range(n) if arrival_times[i] > due_times[i]
    )

    ax.set_title(
        f"travel time = {total}   violations = {violations}",
        fontsize=12
    )

    ax.set_aspect("equal")

    # 軸の目盛りを消す
    ax.set_xticks([])
    ax.set_yticks([])

    # 個別ファイルとして保存
    path = os.path.join(RESULTS_DIR, f"{filename}.png")
    fig.savefig(path, dpi=150, bbox_inches="tight")

    # 最新結果として固定名でも保存（再描画せずコピーする）
    shutil.copyfile(path, os.path.join(RESULTS_DIR, f"{LATEST_NAME}.png"))

    plt.close(fig)
