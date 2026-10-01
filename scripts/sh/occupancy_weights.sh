#!/usr/bin/env bash
# =============================================================================
# 在圏型の制約B の係数の付け方 (src/tsptw/time_occupancy_weights.py の
# --scheme など) を、同じインスタンス・同じ条件で並べて比べる。
#
#   CONFIGS の 1 行 = 1 設定（"<名前> <追加引数...>"）。設定ごとに
#   occupancy.sh を 1 回呼び、$OUTDIR/<名前>/ に runs.csv / summary.csv を残す。
#   最後に全設定の summary を $OUTDIR/compare.csv にまとめる。
#
#   既定は n60w20.001・10 回 × 30 秒・target = 既知最良値。GPU 1 枚の手元機
#   (WSL) で回す前提で COOLDOWN 0、CUDA_VISIBLE_DEVICES 0、nice -n 19。
#
# 使い方（リポジトリのルートで）:
#   bash scripts/sh/occupancy_weights.sh
#   ONLY="uniform delta" bash scripts/sh/occupancy_weights.sh   # 一部だけ
#
# 環境変数: SIZES WIDTHS INST_ID RUNS TIME_LIMIT は occupancy.sh と同じ。
#   SET      1 = 第 1 弾 CONFIGS（既定）、2 = 第 2 弾 CONFIGS2、3 = 確認用 CONFIGS3、4 = 大規模用 CONFIGS4、5 = 大規模・長時間用 CONFIGS5、6 = 学習の改良 CONFIGS6、7 = 時刻の詰め CONFIGS7
#   ONLY     CONFIGS のうち実行する名前の並び (既定 全部)
#   OUTDIR   出力先 (既定 result_dir occupancy_weights <n?w?>)
# =============================================================================
set -u -o pipefail

export SIZES=${SIZES:-60} WIDTHS=${WIDTHS:-20} RUNS=${RUNS:-10}
export TIME_LIMIT=${TIME_LIMIT:-30} COOLDOWN=${COOLDOWN:-0}
export CUDA_VISIBLE_DEVICES=${CUDA_VISIBLE_DEVICES:-0}
export SCRIPT=src/tsptw/time_occupancy_weights.py
ONLY=${ONLY:-}

CONFIGS=(
    "uniform      --scheme uniform"
    "scale0.5     --scale 0.5"
    "scale2       --scale 2"
    "delta        --scheme delta"
    "pair         --scheme pair"
    "waitsrc0.5   --scheme waitsrc --wait-factor 0.5"
    "degree       --scheme degree"
    "rev4         --rev-factor 4"
    "cust0.5      --cust-scale 0.5"
    "cust2        --cust-scale 2"
    "learn3       --rounds 3 --grow 4"
    "learn6       --rounds 6 --grow 2"
)
# 第 2 弾（SET=2）: 第 1 弾で効いた rev / degree / learn を組み合わせる
CONFIGS2=(
    "rev8             --rev-factor 8"
    "forced2          --forced-factor 2"
    "forced2_rev2     --forced-factor 2 --rev-factor 2"
    "degree_rev4      --scheme degree --rev-factor 4"
    "scale2_cust2     --scale 2 --cust-scale 2"
    "learn6cap2       --rounds 6 --grow 2 --cap 2"
    "learn6restart    --rounds 6 --grow 2 --restart"
    "rev4_learn6cap2  --rev-factor 4 --rounds 6 --grow 2 --cap 2"
)
# 第 3 弾（SET=3）: 上位を回数を増やして確かめる（RUNS=20 で使う）
CONFIGS3=(
    "uniform          --scheme uniform"
    "forced2_rev2     --forced-factor 2 --rev-factor 2"
    "forced2_rev4     --forced-factor 2 --rev-factor 4"
    "learn6cap2       --rounds 6 --grow 2 --cap 2"
    "rev4_learn6cap2  --rev-factor 4 --rounds 6 --grow 2 --cap 2"
)
# 第 4 弾（SET=4）: 大きいインスタンス (n200w20, n60w100) 用の探り
CONFIGS4=(
    "uniform          --scheme uniform"
    "rev4             --rev-factor 4"
    "f2r4_c1.1        --forced-factor 2 --rev-factor 4 --cust-scale 1.1"
    "f2r4_half        --forced-factor 2 --rev-factor 4 --scale 0.5 --cust-scale 0.5"
    "learn6cap2       --rounds 6 --grow 2 --cap 2"
    "rev4_learn6cap2  --rev-factor 4 --rounds 6 --grow 2 --cap 2"
    "f2r4_swap        --forced-factor 2 --rev-factor 4 --auto-swap"
)
# 第 5 弾（SET=5）: 大きいインスタンスを長めに（TIME_LIMIT=300 で使う）
CONFIGS5=(
    "f2r4             --forced-factor 2 --rev-factor 4"
    "learnA           --rounds 10 --grow 2 --cap 4 --learn-cust"
    "rev4_learnA      --rev-factor 4 --rounds 10 --grow 2 --cap 4 --learn-cust"
)
# 第 6 弾（SET=6）: 学習に減衰と最良再開を足す（TIME_LIMIT=300 で使う）
CONFIGS6=(
    "learnA_decay     --rounds 10 --grow 2 --cap 4 --learn-cust --decay 0.7"
    "learnA_best      --rounds 10 --grow 2 --cap 4 --learn-cust --hint-best"
    "learnA_decay_best --rounds 10 --grow 2 --cap 4 --learn-cust --decay 0.7 --hint-best"
)
# 第 7 弾（SET=7）: 実行可能解の時刻が詰め切れていない対策（TIME_LIMIT=300 で使う）
CONFIGS7=(
    "learnA_swap      --rounds 10 --grow 2 --cap 4 --learn-cust --auto-swap"
    "learnA_half      --rounds 10 --grow 2 --cap 4 --learn-cust --scale 0.5 --cust-scale 0.5"
)
[[ ${SET:-1} == 7 ]] && CONFIGS=("${CONFIGS7[@]}")
[[ ${SET:-1} == 6 ]] && CONFIGS=("${CONFIGS6[@]}")
[[ ${SET:-1} == 2 ]] && CONFIGS=("${CONFIGS2[@]}")
[[ ${SET:-1} == 5 ]] && CONFIGS=("${CONFIGS5[@]}")
[[ ${SET:-1} == 4 ]] && CONFIGS=("${CONFIGS4[@]}")
[[ ${SET:-1} == 3 ]] && CONFIGS=("${CONFIGS3[@]}")

source "$(dirname "${BASH_SOURCE[0]}")/common.sh"
OUTDIR=${OUTDIR:-$(result_dir occupancy_weights "$(sweep_tag "$SIZES" "$WIDTHS")" \
    "$(time_tag "$TIME_LIMIT" 30)" "$([[ ${SET:-1} != 1 ]] && echo "set$SET")")}
mkdir -p "$OUTDIR"
echo "出力先: $OUTDIR"

for line in "${CONFIGS[@]}"; do
    read -r name args <<< "$line"
    if [[ -n $ONLY && " $ONLY " != *" $name "* ]]; then
        continue
    fi
    echo "################ $name : $args ################"
    EXTRA_ARGS=$args OUTDIR=$OUTDIR/$name \
        nice -n 19 bash "$(dirname "${BASH_SOURCE[0]}")/occupancy.sh" || exit 1
done

# 設定名を先頭列に足して 1 つの表にまとめる
{
    echo "config,$(head -1 "$(ls "$OUTDIR"/*/summary.csv | head -1)")"
    for f in "$OUTDIR"/*/summary.csv; do
        name=$(basename "$(dirname "$f")")
        tail -n +2 "$f" | sed "s/^/$name,/"
    done
} > "$OUTDIR/compare.csv"
column -s, -t "$OUTDIR/compare.csv" | cut -c1-200
