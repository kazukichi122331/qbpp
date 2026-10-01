#!/usr/bin/env bash
# =============================================================================
# 在圏型の改良版 (src/tsptw/time_occupancy_v2.py) を、Dumas の既知最良値がある
# 全インスタンス (n20〜n200 × w20〜w100 × .001〜.005、135 件) で 1 回ずつ回す。
#
#   中身は occupancy.sh を INST_ID ごとに呼ぶだけ。結果は
#   $OUTDIR/<INST_ID>/runs.csv, summary.csv, logs/ に分かれる。
#   既定は 1 回 300 秒、target = 既知最良値（検算で届いた時点で打ち切り）。
#
# 使い方（リポジトリのルートで）:
#   bash scripts/sh/occupancy_v2_all.sh                     # 手元機 (GPU 0)
#   CUDA_VISIBLE_DEVICES=7 bash scripts/sh/occupancy_v2_all.sh   # A100
#
# 環境変数: TIME_LIMIT (既定 300)、IDS (既定 "001 002 003 004 005")、
#   V2_ARGS (time_occupancy_v2.py に渡す引数)、OUTDIR (既定 result_dir occupancy_v2 all。WSL では results/ 以下)
# =============================================================================
set -u -o pipefail
# 手元 (WSL) で回した結果は results/ に置く (CLAUDE.md)。A100 では lab_results/
if grep -qi microsoft /proc/version 2> /dev/null; then
    export OUT_ROOT=${OUT_ROOT:-results}
fi
source "$(dirname "${BASH_SOURCE[0]}")/common.sh"

TIME_LIMIT=${TIME_LIMIT:-300}
IDS=${IDS:-"001 002 003 004 005"}
V2_ARGS=${V2_ARGS:-"--lns 20 --lns-init 20 --auto-swap --early -1"}
export CUDA_VISIBLE_DEVICES=${CUDA_VISIBLE_DEVICES:-0}
OUTDIR=${OUTDIR:-$(result_dir occupancy_v2 all "$(time_tag "$TIME_LIMIT" 30)")}
mkdir -p "$OUTDIR"
echo "出力先: $OUTDIR"

for id in $IDS; do
    SIZES="20 40 60 80 100 150 200" WIDTHS="20 40 60 80 100" INST_ID=$id \
    RUNS=1 TIME_LIMIT=$TIME_LIMIT COOLDOWN=0 \
    SCRIPT=src/tsptw/time_occupancy_v2.py EXTRA_ARGS="$V2_ARGS" \
    OUTDIR=$OUTDIR/$id nice -n 19 bash "$(dirname "${BASH_SOURCE[0]}")/occupancy.sh"
done
