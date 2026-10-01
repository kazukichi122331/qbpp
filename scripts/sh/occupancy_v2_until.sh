#!/usr/bin/env bash
# =============================================================================
# time_occupancy_v2.py を、指定したインスタンスで既知最良値に届くまで回し続ける。
#
#   本命 (MAIN) を順に回し、届かなかったものは次の周で制限時間を倍にして
#   シードを変えて回し直す（1 周目 BASE 秒、2 周目 2*BASE 秒、…）。
#   1 件が全時間を使い切らないよう、周ごとに全件を一巡する。
#   本命が全部届いたら、既知最良値に原理的に届かない (NONREP: 三角不等式の破れで
#   最適ツアーを模型が表現できない) インスタンスを NONREP_TIME 秒ずつ 1 回だけ回して
#   最良値を記録する。DEADLINE を過ぎる回は始めず、各回の制限時間も残り時間で切る。
#   終わったら ntfy に通知する（トピックは ~/.claude/hooks/notify-iphone.py から読む）。
#
# 使い方（リポジトリのルートで。長時間なので tmux の detached セッションで）:
#   tmux new-session -d -s occ_until "cd ~/qbpp && bash scripts/sh/occupancy_v2_until.sh"
#
# 環境変数: MAIN, NONREP（インスタンス名の並び）、BASE (既定 3600)、NONREP_TIME (既定 7200)、
#   DEADLINE (既定 "2026-10-03 23:00")、V2_ARGS、OUTDIR、CUDA_VISIBLE_DEVICES (既定 0)、NOTIFY=0 で通知しない
# 出力: $OUTDIR/runs.csv（1 行 = 1 回）、$OUTDIR/logs/*.log、$OUTDIR/progress.log
# =============================================================================
set -u -o pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/../.."
if grep -qi microsoft /proc/version 2> /dev/null; then
    export OUT_ROOT=${OUT_ROOT:-results}     # 手元 (WSL) の結果は results/ (CLAUDE.md)
fi
source scripts/sh/common.sh

MAIN=${MAIN:-"n40w100.001 n40w100.002 n60w100.004 n80w60.002 n80w80.001 n80w80.004 n150w60.001 n150w60.002"}
NONREP=${NONREP:-"n60w80.004 n80w60.005 n150w60.003 n150w60.005"}
BASE=${BASE:-3600}
NONREP_TIME=${NONREP_TIME:-7200}
DEADLINE=${DEADLINE:-"2026-10-03 23:00"}
V2_ARGS=${V2_ARGS:-"--lns 20 --lns-init 20 --auto-swap --early -1"}
PYTHON=${PYTHON:-.venv/bin/python}
export CUDA_VISIBLE_DEVICES=${CUDA_VISIBLE_DEVICES:-0}
BEST_FILE=instances/Dumas/Dumas-best-known-traveltime.txt
OUTDIR=${OUTDIR:-$(result_dir occupancy_v2 until)}
mkdir -p "$OUTDIR/logs"
deadline_epoch=$(date -d "$DEADLINE" +%s)

{
    echo "date      = $(date '+%F %T')"
    echo "host      = $(hostname)"
    echo "git       = $(git rev-parse --short HEAD 2>/dev/null)"
    echo "args      = $V2_ARGS"
    echo "main      = $MAIN"
    echo "nonrep    = $NONREP"
    echo "base      = $BASE   nonrep_time = $NONREP_TIME   deadline = $DEADLINE"
    echo "gpu       = CUDA_VISIBLE_DEVICES=$CUDA_VISIBLE_DEVICES"
    nvidia-smi -i "$CUDA_VISIBLE_DEVICES" 2>&1 | head -12
} > "$OUTDIR/env.txt"
echo "pass,group,instance,seed,time_limit,status,target,value,feasible,reached,tts,wall" > "$OUTDIR/runs.csv"

say() { echo "[$(date '+%m-%d %H:%M:%S')] $*" | tee -a "$OUTDIR/progress.log"; }
field() { awk -v key="$2" 'index($0, key) == 1 { sub(/^[^=]*=[ \t]*/, "", $0); print $1; exit }' "$1"; }
best_of() { awk -v n="$1.txt" '$1 == n { print $2; exit }' "$BEST_FILE"; }

notify() {
    [[ ${NOTIFY:-1} == 0 ]] && return 0
    local topic
    topic=$(sed -n 's/^NTFY_TOPIC = "\(.*\)"/\1/p' ~/.claude/hooks/notify-iphone.py 2>/dev/null)
    [[ -n $topic ]] && curl -s -m 20 -d "$1" "https://ntfy.sh/$topic" > /dev/null 2>&1
    return 0
}

# run_one <pass> <group> <inst> <seed> <time_limit>  -> 戻り値 0 = 到達
run_one() {
    local pass=$1 group=$2 inst=$3 seed=$4 tl=$5
    local target log t0 t1 rc status value feasible reached tts lic=0
    target=$(best_of "$inst")
    log="$OUTDIR/logs/${inst}_p${pass}_s${seed}.log"
    while :; do
        t0=$(date +%s)
        nice -n 19 "$PYTHON" src/tsptw/time_occupancy_v2.py "$tl" -i "instances/Dumas/$inst.txt" \
            --seed "$seed" --target-energy "$target" --no-plot -q $V2_ARGS > "$log" 2>&1
        rc=$?
        t1=$(date +%s)
        if [[ $rc -ne 0 ]] && (( lic < 5 )) && grep -q -e "License is in use" -e "Variable limit exceeded" "$log"; then
            lic=$((lic + 1)); mv "$log" "${log%.log}.licfail$lic.log"
            say "  $inst: ライセンスが取れないので 300 秒後に再実行 ($lic/5)"
            sleep 300; continue
        fi
        break
    done
    status=ok; [[ $rc -ne 0 ]] && status="error($rc)"
    value=$(field "$log" "travel time"); feasible=$(field "$log" "feasible"); tts=$(field "$log" "TTS")
    reached=0
    [[ $feasible == True && -n $value ]] && (( value <= target )) && reached=1
    echo "$pass,$group,$inst,$seed,$tl,$status,$target,${value:-},${feasible:-},$reached,${tts:-},$((t1 - t0))" >> "$OUTDIR/runs.csv"
    say "  pass $pass $inst seed=$seed tl=${tl}s -> value=${value:--} (best $target) feasible=${feasible:--} reached=$reached tts=${tts:--} wall=$((t1 - t0))s $status"
    [[ $reached -eq 1 ]]
}

remaining() { echo $(( deadline_epoch - $(date +%s) - 120 )); }

say "開始: 出力先 $OUTDIR、期限 $DEADLINE"
notify "occupancy_v2_until 開始: $(echo $MAIN | wc -w) 件、期限 $DEADLINE"
todo=($MAIN)
done_list=()
pass=1
budget=$BASE
stop=0
while (( ${#todo[@]} > 0 )) && (( ! stop )); do
    say "=== 第 $pass 周（1 件 ${budget} 秒、残り ${#todo[@]} 件: ${todo[*]}）"
    next=()
    for inst in "${todo[@]}"; do
        rem=$(remaining)
        if (( rem < 600 )); then stop=1; next+=("$inst"); continue; fi
        tl=$(( budget < rem ? budget : rem ))
        if run_one "$pass" main "$inst" $((100 + pass)) "$tl"; then
            done_list+=("$inst")
        else
            next+=("$inst")
        fi
    done
    todo=("${next[@]}")
    pass=$((pass + 1))
    budget=$((budget * 2))
done

if (( ${#todo[@]} == 0 )); then
    say "本命 ${#done_list[@]} 件すべて既知最良値に到達。表現できない側を回す"
    for inst in $NONREP; do
        rem=$(remaining)
        (( rem < 600 )) && { say "期限が近いので打ち切り"; break; }
        tl=$(( NONREP_TIME < rem ? NONREP_TIME : rem ))
        run_one 1 nonrep "$inst" 101 "$tl" || true
    done
fi

msg="occupancy_v2_until 終了: 到達 ${#done_list[@]} 件 (${done_list[*]:-なし})、未到達 ${#todo[@]} 件 (${todo[*]:-なし})"
say "$msg"
notify "$msg"
