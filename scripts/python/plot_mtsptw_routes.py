"""mTSPTW の計測ログ 1 本からルート図とタイムラインを描く。

    左: 距離行列から復元した座標上の各車両のルート
    右: 横軸 = 時刻、縦軸 = 各車両の訪問順。灰色の縦棒が時間枠、点がサービス開始時刻。
        Z の下界 z_lo と帰着の上限 L[N+1] を縦線で示す。

使い方:
    python scripts/plot_mtsptw_routes.py <log> -i instances/Dumas/n200w20.001.txt -o out.png
"""
import argparse
import ast
import os
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path[:0] = [os.path.join(_ROOT, "src"), os.path.join(_ROOT, "src", "mtsptw")]

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

from mtsptwlib import load_minstance, simulate
from tsptwlib.plot import recover_coordinates

from matplotlib import font_manager

_JP_FONT = "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc"
if os.path.exists(_JP_FONT):
    font_manager.fontManager.addfont(_JP_FONT)
    plt.rcParams["font.family"] = font_manager.FontProperties(fname=_JP_FONT).get_name()

COLORS = ["#2a78d6", "#eb6834", "#1baf7a"]     # 車両 0, 1, 2
INK, MUTED, GRID = "#0b0b0b", "#52514e", "#e4e3df"


def read_routes(log):
    routes = []
    with open(log, encoding="utf-8") as f:
        for line in f:
            if line.startswith("route["):
                routes.append(ast.literal_eval(line.split("=", 1)[1].strip()))
    return routes


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("log")
    ap.add_argument("-i", "--instance", required=True)
    ap.add_argument("-o", "--out", required=True)
    args = ap.parse_args()

    inst = load_minstance(args.instance)
    routes = read_routes(args.log)
    end = inst.end
    scheds = [simulate(inst, r) for r in routes]

    # z_lo = max_i (lo[i] + c[i][N+1])、lo[i] = max(E[i], c[0][i])（Dumas はサービス時間 0）
    reach = {i: max(inst.E[i], inst.c[0][i]) + inst.c[i][end]
             for i in range(1, inst.N + 1)}
    key = max(reach, key=reach.get)
    z_lo, limit = reach[key], inst.L[end]

    xy = recover_coordinates(inst.base.c)       # 頂点 0..N（N+1 はデポ 0 と同じ位置）
    pos = lambda v: xy[0] if v == end else xy[v]

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(13, 6),
                                   gridspec_kw={"width_ratios": [1, 1.25]})

    # --- 左: ルート ---
    for k, r in enumerate(routes):
        pts = [pos(v) for v in r]
        ax1.plot([p[0] for p in pts], [p[1] for p in pts], color=COLORS[k],
                 lw=1.4, zorder=2,
                 label=f"車両 {k}（{len(r) - 2} 顧客, 帰着 {scheds[k].ret}）")
        ax1.scatter([p[0] for p in pts[1:-1]], [p[1] for p in pts[1:-1]],
                    s=12, color=COLORS[k], edgecolor="white", lw=0.6, zorder=3)
    ax1.scatter(*xy[0], marker="s", s=70, color=INK, zorder=4, label="デポ")
    ax1.scatter(*xy[key], s=110, facecolor="none", edgecolor=INK, lw=1.5, zorder=4,
                label=f"顧客 {key}（z_lo を決める）")
    ax1.set_aspect("equal")
    ax1.set_xticks([]); ax1.set_yticks([])
    for s in ax1.spines.values():
        s.set_color(GRID)
    ax1.legend(loc="upper left", bbox_to_anchor=(0, -0.01), ncol=2, fontsize=9, frameon=False)
    ax1.set_title("ルート（距離行列から復元した座標）", fontsize=11, color=INK, loc="left")

    # --- 右: タイムライン ---
    for k, r in enumerate(routes):
        cust = r[1:-1]
        ys = list(range(1, len(cust) + 1))
        ax2.hlines(ys, [inst.E[i] for i in cust], [inst.L[i] for i in cust],
                   color=COLORS[k], alpha=0.25, lw=3)
        starts = [scheds[k].start[i] for i in cust]
        ax2.plot([0] + starts + [scheds[k].ret], [0] + ys + [len(cust) + 1],
                 color=COLORS[k], lw=1.4, marker="o", ms=2.5,
                 label=f"車両 {k}  帰着 {scheds[k].ret}")
        if key in cust:
            y = cust.index(key) + 1
            ax2.scatter(scheds[k].start[key], y, s=110, facecolor="none",
                        edgecolor=INK, lw=1.5, zorder=4)
            ax2.annotate(f"顧客 {key}", (scheds[k].start[key], y), xytext=(-60, 8),
                         textcoords="offset points", fontsize=9, color=INK)
    ax2.axvline(z_lo, color=INK, lw=1, ls="--")
    ax2.axvline(limit, color=MUTED, lw=1, ls=":")
    top = max(len(r) for r in routes)
    ax2.text(z_lo - 6, top * 0.03, f"z_lo = {z_lo}", ha="right", fontsize=9, color=INK)
    ax2.text(limit + 6, top * 0.03, f"L[N+1] = {limit}", ha="left", fontsize=9,
             color=MUTED, rotation=90, va="bottom")
    ax2.set_xlim(0, limit * 1.04)
    ax2.set_ylim(0, top + 2)
    ax2.set_xlabel("時刻", color=MUTED)
    ax2.set_ylabel("訪問順", color=MUTED)
    ax2.grid(color=GRID, lw=0.6)
    ax2.set_axisbelow(True)
    for s in ("top", "right"):
        ax2.spines[s].set_visible(False)
    for s in ("left", "bottom"):
        ax2.spines[s].set_color(MUTED)
    ax2.tick_params(colors=MUTED)
    ax2.legend(loc="upper left", fontsize=9, frameon=False)
    ax2.set_title("サービス開始時刻（線）と時間枠（淡い帯）", fontsize=11, color=INK, loc="left")

    fig.suptitle(f"{inst.name}  {len(routes)} 台・min-max（leq 版）: 最大帰着 {max(s.ret for s in scheds)}"
                 f" = 下界 z_lo", fontsize=13, color=INK, x=0.01, ha="left")
    fig.tight_layout()
    fig.savefig(args.out, dpi=150, facecolor="white")
    print("saved", args.out, " key customer", key, " z_lo", z_lo)


if __name__ == "__main__":
    main()
