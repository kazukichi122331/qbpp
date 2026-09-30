#!/usr/bin/env bash
# =============================================================================
# time_occupancy.py を制限時間 300 秒で計測し直す（30 秒で届かなかった条件だけ）。
#
#   2026-09-28 夜の計測（docs/archive/time_a100_results_0928_rerun.md）では、occupancy 型は
#   30 秒だと n100 以降・n60w60 以降で既知最良値に届かないことが多かった。
#   そこで target_energy を既知最良値にしたまま、制限時間だけを 300 秒に延ばす。
#   到達すればそこで打ち切られるので、届く実行は 300 秒待たずに終わる。
#
#   1. 顧客数スイープ   n = 100/150/200、w = 20
#   2. 時間窓スイープ   n = 60、w = 60/80/100
#
#   実体は scripts/sh/occupancy.sh。ここは SIZES / WIDTHS /
#   TIME_LIMIT / TARGET / OUTDIR を差し替えて 2 回呼ぶだけ。出力の形式も同じ。
#   RUNS・COOLDOWN・seed（1〜10）・GPU（既定 7）は 30 秒の計測と揃えてある。
#
#   所要時間の目安: 6 インスタンス × 10 回 × 最大 300 秒 ≒ 最大 5 時間
#   （＋モデル構築・COOLDOWN）。
#
# 使い方（リモート機に ssh したあと、リポジトリのルートで）:
#
#   CUDA_VISIBLE_DEVICES=7 nohup bash scripts/sh/occupancy_long.sh > run_long.out 2>&1 &
#
# 環境変数:
#   TIME_LIMIT   1 回のソルバ制限時間（秒）   (既定 300)
#   TARGET       target_energy の決め方        (既定 best = 既知最良値)
#   SIZE_SWEEP   顧客数スイープの n の並び     (既定 "100 150 200")
#   WIDTH_SWEEP  時間窓スイープの w の並び     (既定 "60 80 100")
#   GAP          2 本の間の待ち（秒）          (既定 60)
#   NTFY_TOPIC   ntfy.sh の通知先トピック。未設定なら ~/.ntfy_topic の 1 行目を読む。
#                どちらも無ければ通知しない。トピック名は実質パスワードなので
#                リポジトリには書かない
#   NTFY_SERVER  ntfy のサーバ                 (既定 https://ntfy.sh)
#   OUT_ROOT     出力先の親ディレクトリ        (既定 lab_results)
#   それ以外（CUDA_VISIBLE_DEVICES / RUNS / COOLDOWN / RUN_TIMEOUT ...）は
#   そのまま本体に引き継がれる。
#
# 出力先:
#   lab_results/<日時>_occupancy_nsweep_t300/   （n = 100/150/200、w20）
#   lab_results/<日時>_occupancy_wsweep_t300/   （n60、w = 60/80/100）
# =============================================================================
set -u

HERE=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)

export TIME_LIMIT=${TIME_LIMIT:-300}
export TARGET=${TARGET:-best}
SIZE_SWEEP=${SIZE_SWEEP:-"100 150 200"}
WIDTH_SWEEP=${WIDTH_SWEEP:-"60 80 100"}
GAP=${GAP:-60}
OUT_ROOT=${OUT_ROOT:-lab_results}
source "$HERE/common.sh"

interrupted=0
trap 'interrupted=1; echo; echo "[$(date "+%F %T")] 中断されました"' INT TERM

log() { echo "[$(date '+%F %T')] $*"; }

# --- 通知（ntfy.sh）。失敗しても計測は止めない ---
NTFY_SERVER=${NTFY_SERVER:-https://ntfy.sh}
if [[ -z ${NTFY_TOPIC:-} && -f ~/.ntfy_topic ]]; then
    NTFY_TOPIC=$(head -n 1 ~/.ntfy_topic | tr -d '[:space:]')
fi
NTFY_TOPIC=${NTFY_TOPIC:-}
if [[ -n $NTFY_TOPIC ]]; then
    log "通知: 有効 ($NTFY_SERVER)"
else
    log "通知: 無効（NTFY_TOPIC も ~/.ntfy_topic も無い）"
fi

notify() {                      # notify <title(ASCII)> <本文> [tags]
    [[ -z $NTFY_TOPIC ]] && return 0
    curl -fsS -m 15 -o /dev/null \
        -H "Title: $1" -H "Tags: ${3:-bar_chart}" \
        --data-binary "$2" "$NTFY_SERVER/$NTFY_TOPIC" \
        || log "通知の送信に失敗しました（計測は続けます）"
}

# summary.csv を「n100w20.001 到達 3/10 最良 738 実行可能 10」の行に直す
summary_text() {                # summary_text <summary.csv>
    [[ -f $1 ]] || { echo "(summary.csv なし)"; return; }
    awk -F',' 'NR > 1 {
        printf "%s 到達 %s/%s 最良 %s 実行可能 %s\n", $2, ($5 == "" ? "-" : $5), $3,
               ($20 == "" ? "-" : $20), ($14 == "" ? "-" : $14)
    }' "$1"
}

# run_sweep <sizes> <widths>
run_sweep() {
    local sizes=$1 widths=$2
    local tag="n$(echo "$sizes" | tr ' ' '-')_w$(echo "$widths" | tr ' ' '-')_t${TIME_LIMIT%.*}"
    local outdir
    outdir=$(result_dir occupancy "$(sweep_tag "$sizes" "$widths")" "$(time_tag "$TIME_LIMIT" 30)")
    log "開始 occupancy $tag"
    SIZES=$sizes WIDTHS=$widths OUTDIR=$outdir \
        bash "$HERE/occupancy.sh"
    local rc=$?
    log "終了 occupancy $tag (rc=$rc)"
    if (( interrupted )); then
        notify "a100 occupancy interrupted" "中断: $tag
$(summary_text "$outdir/summary.csv")" warning
    else
        notify "a100 occupancy $tag done" "完了 (rc=$rc): $outdir
$(summary_text "$outdir/summary.csv")"
    fi
}

run_sweep "$SIZE_SWEEP" "20"
(( interrupted )) && exit 130

log "次のスイープまで ${GAP} 秒待ちます"
sleep "$GAP"
(( interrupted )) && exit 130

run_sweep "60" "$WIDTH_SWEEP"
(( interrupted )) && exit 130
notify "a100 occupancy all done" "${TIME_LIMIT} 秒の計測がすべて終わりました" white_check_mark
exit 0
