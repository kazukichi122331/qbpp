#!/usr/bin/env bash
# =============================================================================
# A100 用の時間展開型 TSPTW 計測 4 本を順番に流す。
#
#   1. run_time_makespan_a100.sh         (makespan・顧客数スイープ)
#   2. run_time_makespan_width_a100.sh   (makespan・時間窓スイープ)
#   3. run_time_occupancy_a100.sh        (occupancy・顧客数スイープ)
#   4. run_time_occupancy_width_a100.sh  (occupancy・時間窓スイープ)
#
#   1 本終わるごとに GAP 秒あけて次へ進む。終了コードが 0 でなければ
#   RETRY_WAIT 秒待ってその 1 本を最初からやり直す（出力先は日時つきで別になる）。
#   各スクリプトが非 0 で終わるのは起動前チェック（python がない等）で落ちたとき。
#   個々の python 実行の失敗は各スクリプトが runs.csv に error(rc) と記録して
#   先へ進むので、ここでは再実行の対象にならない。
#
# 使い方（リモート機に ssh したあと、リポジトリのルートで）:
#
#   bash scripts/run_all_time_a100.sh
#   CUDA_VISIBLE_DEVICES=3 bash scripts/run_all_time_a100.sh   # 別の GPU を使う
#   nohup bash scripts/run_all_time_a100.sh > run_all.out 2>&1 &   # 放置する場合
#
# 環境変数:
#   GAP          1 本終わってから次を始めるまでの待ち（秒）   (既定 60)
#   RETRY_WAIT   失敗したとき再実行までの待ち（秒）           (既定 60)
#   MAX_RETRIES  1 本あたりの再実行回数の上限。0 で無制限     (既定 0)
#   それ以外（CUDA_VISIBLE_DEVICES / RUNS / TIME_LIMIT / TARGET ...）は
#   そのまま各スクリプトに引き継がれる。
# =============================================================================
set -u

HERE=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)

GAP=${GAP:-60}
RETRY_WAIT=${RETRY_WAIT:-60}
MAX_RETRIES=${MAX_RETRIES:-0}

JOBS=(
    run_time_makespan_a100.sh
    run_time_makespan_width_a100.sh
    run_time_occupancy_a100.sh
    run_time_occupancy_width_a100.sh
)

# Ctrl-C / kill で止めたら次のスクリプトに進まず終わる
# （子スクリプトは中断されても終了コード 0 で抜けるため、ここで拾う）。
interrupted=0
trap 'interrupted=1; echo; echo "[$(date "+%F %T")] 中断されました"' INT TERM

log() { echo "[$(date '+%F %T')] $*"; }

results=()
for i in "${!JOBS[@]}"; do
    (( interrupted )) && break
    job=${JOBS[$i]}

    if (( i > 0 )); then
        log "次のスクリプトまで ${GAP} 秒待ちます"
        sleep "$GAP"
        (( interrupted )) && break
    fi

    attempt=1
    while :; do
        log "開始 ($((i + 1))/${#JOBS[@]}) $job  試行 $attempt"
        bash "$HERE/$job"
        rc=$?
        (( interrupted )) && break 2

        if [[ $rc -eq 0 ]]; then
            log "完了 $job"
            results+=("ok      $job (試行 $attempt)")
            break
        fi
        if (( MAX_RETRIES > 0 && attempt > MAX_RETRIES )); then
            log "失敗 $job (rc=$rc)。再実行の上限 ${MAX_RETRIES} 回に達したので次へ進みます"
            results+=("failed  $job (rc=$rc, 試行 $attempt)")
            break
        fi
        log "失敗 $job (rc=$rc)。${RETRY_WAIT} 秒後に再実行します"
        sleep "$RETRY_WAIT"
        (( interrupted )) && break 2
        attempt=$((attempt + 1))
    done
done

echo
log "まとめ"
for r in "${results[@]}"; do echo "  $r"; done
(( interrupted )) && exit 130
exit 0
