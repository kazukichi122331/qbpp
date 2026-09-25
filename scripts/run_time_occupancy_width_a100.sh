#!/usr/bin/env bash
# =============================================================================
# time_occupancy.py (時間展開型・在圏変数版 TSPTW) の「時間窓スイープ」。
#
#   顧客数 n = 60 を固定し、時間枠幅 w = 20/40/60/80/100 を各 10 回 × 30 秒。
#   在圏変数は待機スロットも含めて Σ_v |在圏域| なので、w を広げると変数数・項数が
#   まっすぐ効く。その効き方をエネルギー・制約違反と並べて見るための掃引。
#
#   実体は scripts/run_time_occupancy_a100.sh（顧客数スイープと同じ中身）。
#   ここは SIZES / WIDTHS を差し替えて呼ぶだけ。出力の形式も同じ。
#
# 使い方（リモート機に ssh したあと、リポジトリのルートで）:
#
#   bash scripts/run_time_occupancy_width_a100.sh                        # GPU 7 を使う（既定）
#   CUDA_VISIBLE_DEVICES=3 bash scripts/run_time_occupancy_width_a100.sh  # 別の GPU を使う
#   nohup bash scripts/run_time_occupancy_width_a100.sh > /dev/null 2>&1 &
#
# 本体と同じ環境変数（RUNS / TIME_LIMIT / COOLDOWN / INST_ID / OUTDIR ...）が
# そのまま効く。SIZES / WIDTHS も前置きすれば上書きできる。
# =============================================================================
set -u

HERE=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)

SIZES=${SIZES:-"60"} \
WIDTHS=${WIDTHS:-"20 40 60 80 100"} \
exec bash "$HERE/run_time_occupancy_a100.sh"
