#!/usr/bin/env bash
# =============================================================================
# time_occupancy.py を、各インスタンスで既知最良値に届く（検算で reached = 1、
# つまり feasible かつ総移動時間 <= 既知最良値）まで seed を 1, 2, ... と変えて
# 回し続ける。期限（DEADLINE）が来たら
# 実行中の 1 回も打ち切って終了する。
#
#   インスタンスは交互に回す（seed 1 を全インスタンス → seed 2 を ...）。
#   既知最良値に届いたインスタンスはそこで外す（実行可能解が出ただけでは外さない）。全部出るか期限で終わる。
#   target_energy は既知最良値（到達すればその時点で打ち切られる）。
#
# 使い方（リポジトリのルートで）:
#   DEADLINE="14:00" nohup bash scripts/sh/occupancy_target.sh > run_target.out 2>&1 &
#
# 環境変数:
#   INSTS       インスタンス名の並び   (既定 "n200w20.001 n60w100.001")
#   TIME_LIMIT  1 回の制限時間（秒）   (既定 300)
#   DEADLINE    打ち切り時刻（date -d に渡る文字列） (既定 "14:00")
#   PYTHON / BEST_FILE / OUTDIR        occupancy.sh と同じ
#
# 出力: $OUTDIR/runs.csv（occupancy.sh と同じ列）/ logs/ / env.txt
# =============================================================================
set -u -o pipefail

PYTHON=${PYTHON:-.venv/bin/python}
INSTS=${INSTS:-"n200w20.001 n60w100.001"}
TIME_LIMIT=${TIME_LIMIT:-300}
DEADLINE=${DEADLINE:-"14:00"}
BEST_FILE=${BEST_FILE:-instances/Dumas/Dumas-best-known-traveltime.txt}
SCRIPT=src/tsptw/time_occupancy.py
DEADLINE_EPOCH=$(date -d "$DEADLINE" +%s)
# 出力先の名前は common.sh の result_dir で決める（例 0929-1203_occupancy_until_target_wsl）
source "$(dirname "${BASH_SOURCE[0]}")/common.sh"
OUTDIR=${OUTDIR:-$(result_dir occupancy_until_target "$(time_tag "$TIME_LIMIT" 300)")}

mkdir -p "$OUTDIR/logs"
RUNS_CSV=$OUTDIR/runs.csv
{
    echo "date        = $(date '+%F %T')"
    echo "host        = $(hostname)"
    echo "python      = $($PYTHON -V 2>&1)  ($PYTHON)"
    echo "git commit  = $(git rev-parse --short HEAD 2>/dev/null || echo '-')"
    echo "script      = $SCRIPT"
    echo "insts       = $INSTS"
    echo "time_limit  = ${TIME_LIMIT}s   deadline = $(date -d @"$DEADLINE_EPOCH" '+%F %T')"
    echo "stop rule   = reached = 1（feasible かつ value <= 既知最良値）が出たインスタンスから外す"
    echo "--- nvidia-smi ---"
    nvidia-smi 2>&1 || echo "(nvidia-smi なし)"
} > "$OUTDIR/env.txt"
echo "n,instance,run,seed,status,target_energy,energy,reached,tts,objective,violated_cons,tw_violations,feasible,var_count,term_count,build_sec,wall_sec,value,energy_reached" > "$RUNS_CSV"
echo "出力先: $OUTDIR   期限: $(date -d @"$DEADLINE_EPOCH" '+%T')"

field() {
    awk -v key="$2" 'index($0, key) == 1 { sub(/^[^=]*=[ \t]*/, "", $0); print $1; exit }' "$1"
}

pending=($INSTS)
seed=0
while (( ${#pending[@]} > 0 )); do
    seed=$((seed + 1))
    next=()
    for inst_name in "${pending[@]}"; do
        remain=$(( DEADLINE_EPOCH - $(date +%s) ))
        if (( remain <= 30 )); then
            echo "期限に達したので終了（未完: ${pending[*]}）"
            break 2
        fi
        n=${inst_name#n}; n=${n%%w*}
        target=$(awk -v name="$inst_name.txt" '$1 == name { print $2; exit }' "$BEST_FILE")
        log="$OUTDIR/logs/${inst_name}_run$(printf '%02d' "$seed").log"
        t0=$(date +%s.%N)
        # 期限を越えそうなら実行ごと kill する（-k で SIGTERM 後 10 秒で SIGKILL）
        timeout -k 10 "$remain" "$PYTHON" "$SCRIPT" "$TIME_LIMIT" -i "instances/Dumas/$inst_name.txt" \
            --seed "$seed" --target-energy "$target" --no-plot -q > "$log" 2>&1
        rc=$?
        t1=$(date +%s.%N)
        wall=$(awk -v a="$t0" -v b="$t1" 'BEGIN { printf "%.2f", b - a }')
        if [[ $rc -eq 0 ]]; then status=ok
        elif [[ $rc -eq 124 || $rc -eq 137 ]]; then status=deadline
        else status="error($rc)"
        fi
        energy=$(field "$log" "energy"); objective=$(field "$log" "objective")
        vcons=$(field "$log" "violated cons"); twv=$(field "$log" "tw violations")
        feasible=$(field "$log" "feasible"); vars=$(field "$log" "var_count")
        terms=$(field "$log" "term_count"); build=$(field "$log" "build")
        tts=$(field "$log" "TTS"); value=$(field "$log" "travel time")
        reached=""; energy_reached=""
        if [[ -n $energy ]]; then
            energy_reached=$(awk -v e="$energy" -v t="$target" 'BEGIN { print (e + 0 <= t + 0) ? 1 : 0 }')
            reached=$(awk -v f="$feasible" -v x="$value" -v t="$target" \
                'BEGIN { print (f == "True" && x != "" && x + 0 <= t + 0) ? 1 : 0 }')
        fi
        echo "$n,$inst_name,$seed,$seed,$status,$target,$energy,$reached,$tts,$objective,$vcons,$twv,$feasible,$vars,$terms,$build,$wall,$value,$energy_reached" >> "$RUNS_CSV"
        printf '[%s] %-12s seed %2d  %-8s energy=%-6s value=%-6s reached=%-2s feasible=%-5s violated=%-3s tw=%-3s tts=%-8s wall=%ss\n' \
            "$(date +%T)" "$inst_name" "$seed" "$status" "${energy:--}" "${value:--}" "${reached:--}" "${feasible:--}" \
            "${vcons:--}" "${twv:--}" "${tts:--}" "$wall"
        if [[ $reached == 1 ]]; then
            echo "  -> $inst_name: 既知最良値に到達（seed $seed, 移動時間 $value, 目標 $target, TTS $tts 秒）"
        else
            next+=("$inst_name")
        fi
        [[ $status == deadline ]] && { echo "期限に達したので終了"; break 2; }
    done
    pending=("${next[@]}")
done
(( ${#pending[@]} == 0 )) && echo "全インスタンスで既知最良値に到達したので終了"
echo "完了: $RUNS_CSV"
