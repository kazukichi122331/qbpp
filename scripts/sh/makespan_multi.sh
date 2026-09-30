#!/usr/bin/env bash
# =============================================================================
# time_makespan_multi_leq.py (時間展開型 mTSPTW, min-max を ret_k <= Z の不等式で
# 書く版) を A100 上でまとめて計測する。
#
#   車両 VEHICLES 台、目的関数は帰着時刻の最大値（min-max）。
#   SCRIPT=src/mtsptw/time_makespan_multi.py にすると one-hot 版を OBJ（sum / max）で回せる。
#   INSTS の各インスタンスを RUNS 回、1 回 TIME_LIMIT 秒。
#   1 インスタンス分が終わるたびに COOLDOWN 秒だけ GPU を明け渡す（共用機のため）。
#
#   既定のインスタンス: n20w20 / n60w20 / n100w20（顧客数）、n60w60 / n60w100（時間窓）。
#
#   min-max の既知最良値は無いので target_energy は指定しない（TIME_LIMIT まで走り、
#   TTS は「その実行の最良解を見つけた時刻」）。
#   value はログの検算値（各ルートを最早開始で辿り直した帰着時刻の最大値、
#   "max return" 行）。解の良し悪しは energy ではなく value で見ること。
#
# 使い方（a100 に ssh したあと、リポジトリのルートで）:
#
#   bash scripts/sh/makespan_multi.sh
#   CUDA_VISIBLE_DEVICES=3 bash scripts/sh/makespan_multi.sh
#   nohup bash scripts/sh/makespan_multi.sh > run_multi.out 2>&1 &
#
# 環境変数:
#   PYTHON      python 実行系                     (既定 .venv/bin/python)
#   INSTS       インスタンス名の並び              (既定 "n20w20.001 n60w20.001 n100w20.001 n60w60.001 n60w100.001")
#   VEHICLES    車両数                            (既定 3)
#   SCRIPT      計測する定式化                    (既定 src/mtsptw/time_makespan_multi_leq.py)
#   OBJ         目的関数 sum / max。SCRIPT が time_makespan_multi.py のときだけ渡す (既定 max)
#   RUNS        1 インスタンスあたりの実行回数    (既定 10)
#   TIME_LIMIT  1 回のソルバ制限時間（秒）        (既定 30.0)
#   COOLDOWN    インスタンス間の待ち時間（秒）    (既定 60)
#   LICENSE_WAIT / LICENSE_RETRIES  ライセンス使用中のときの再実行 (既定 300 秒 / 5 回)
#   CUDA_VISIBLE_DEVICES  使う GPU 番号            (既定 7)
#   NTFY_TOPIC  ntfy.sh の通知先。未設定なら ~/.ntfy_topic の 1 行目。どちらも無ければ通知しない
#   OUTDIR      出力先 (既定 lab_results/<日時>_multi_leq_m<台数>。common.sh 参照)
#
# 出力:
#   $OUTDIR/runs.csv     1 行 = 1 実行
#   $OUTDIR/summary.csv  1 行 = 1 インスタンス
#   $OUTDIR/logs/*.log   各実行の標準出力そのまま
#   $OUTDIR/env.txt      GPU・python・git コミットの記録
# =============================================================================
set -u -o pipefail

PYTHON=${PYTHON:-.venv/bin/python}
INSTS=${INSTS:-"n20w20.001 n60w20.001 n100w20.001 n60w60.001 n60w100.001"}
VEHICLES=${VEHICLES:-3}
OBJ=${OBJ:-max}
RUNS=${RUNS:-10}
TIME_LIMIT=${TIME_LIMIT:-30.0}
COOLDOWN=${COOLDOWN:-60}
LICENSE_WAIT=${LICENSE_WAIT:-300}
LICENSE_RETRIES=${LICENSE_RETRIES:-5}
SCRIPT=${SCRIPT:-src/mtsptw/time_makespan_multi_leq.py}

# leq 版は --obj を持たない（常に max）
if [[ $(basename "$SCRIPT") == time_makespan_multi.py ]]; then
    obj_opt=(--obj "$OBJ")
else
    OBJ=max
    obj_opt=()
fi

export CUDA_VISIBLE_DEVICES=${CUDA_VISIBLE_DEVICES:-7}
# 出力先の名前は common.sh の result_dir で決める（例 0930-1214_multi_leq_m2_t10）
source "$(dirname "${BASH_SOURCE[0]}")/common.sh"
case $(basename "$SCRIPT" .py) in
    time_makespan_multi_leq) model=multi_leq ;;
    time_makespan_multi)     model=multi_$OBJ ;;
    *)                       model=$(basename "$SCRIPT" .py | sed 's/^time_//') ;;
esac
OUTDIR=${OUTDIR:-$(result_dir "$model" "m$VEHICLES" "$(time_tag "$TIME_LIMIT" 30)")}

if [[ ! -f $SCRIPT || ! -d instances/Dumas ]]; then
    echo "ERROR: リポジトリのルートで実行してください（$SCRIPT が見つからない）" >&2
    exit 1
fi
if [[ ! -x $PYTHON ]] && ! command -v "$PYTHON" > /dev/null 2>&1; then
    echo "ERROR: python が見つからない: $PYTHON （PYTHON=... で指定できる）" >&2
    exit 1
fi

# --- 通知（ntfy.sh）。失敗しても計測は止めない ---
NTFY_SERVER=${NTFY_SERVER:-https://ntfy.sh}
if [[ -z ${NTFY_TOPIC:-} && -f ~/.ntfy_topic ]]; then
    NTFY_TOPIC=$(head -n 1 ~/.ntfy_topic | tr -d '[:space:]')
fi
NTFY_TOPIC=${NTFY_TOPIC:-}
notify() {                      # notify <title(ASCII)> <本文> [tags]
    [[ -z $NTFY_TOPIC ]] && return 0
    curl -fsS -m 15 -o /dev/null \
        -H "Title: $1" -H "Tags: ${3:-bar_chart}" \
        --data-binary "$2" "$NTFY_SERVER/$NTFY_TOPIC" \
        || echo "通知の送信に失敗しました（計測は続けます）"
}

mkdir -p "$OUTDIR/logs"
RUNS_CSV=$OUTDIR/runs.csv
SUMMARY_CSV=$OUTDIR/summary.csv

{
    echo "date        = $(date '+%F %T')"
    echo "host        = $(hostname)"
    echo "python      = $($PYTHON -V 2>&1)  ($PYTHON)"
    echo "git commit  = $(git rev-parse --short HEAD 2>/dev/null || echo '-')"
    echo "script      = $SCRIPT"
    echo "insts       = $INSTS"
    echo "vehicles    = $VEHICLES   obj = $OBJ"
    echo "runs        = $RUNS    time_limit = ${TIME_LIMIT}s   cooldown = ${COOLDOWN}s"
    echo "gpu         = CUDA_VISIBLE_DEVICES=$CUDA_VISIBLE_DEVICES"
    echo "notify      = $([[ -n $NTFY_TOPIC ]] && echo "on ($NTFY_SERVER)" || echo off)"
    echo "--- nvidia-smi ---"
    nvidia-smi -i "$CUDA_VISIBLE_DEVICES" 2>&1 || nvidia-smi 2>&1 || echo "(nvidia-smi なし)"
} > "$OUTDIR/env.txt"

echo "出力先: $OUTDIR"
sed -n '1,10p' "$OUTDIR/env.txt"
echo

echo "n,instance,vehicles,obj,run,seed,status,energy,tts,objective,violated_cons,tw_violations,feasible,value,total_travel,used_vehicles,var_count,term_count,build_sec,wall_sec" > "$RUNS_CSV"
echo "n,instance,vehicles,obj,runs_ok,feasible_count,value_mean,value_min,total_travel_mean,total_travel_min,energy_mean,energy_min,violated_cons_mean,tw_violations_mean,tts_mean,var_count,term_count,build_sec_mean,wall_sec_mean" > "$SUMMARY_CSV"

# ログから "見出し = 値" の値を 1 つ取り出す（最初に一致した行の 1 トークン目）
field() {                       # field <log> <行頭の見出し>
    awk -v key="$2" '
        index($0, key) == 1 {
            sub(/^[^=]*=[ \t]*/, "", $0)
            print $1
            exit
        }' "$1"
}

interrupted=0
trap 'interrupted=1; echo; echo "中断されました（$OUTDIR に途中までの結果が残っています）"' INT TERM

if [[ $OBJ == max ]]; then value_key="max return"; else value_key="total return"; fi

group=0
for inst_name in $INSTS; do
    (( interrupted )) && break
    inst="instances/Dumas/${inst_name}.txt"
    if [[ ! -f $inst ]]; then
        echo "SKIP $inst_name : インスタンスがない ($inst)"
        continue
    fi
    n=${inst_name#n}; n=${n%%w*}

    if (( group > 0 )) && [[ $COOLDOWN -gt 0 ]]; then
        echo "  (GPU を ${COOLDOWN} 秒明け渡します)"
        sleep "$COOLDOWN"
        echo
    fi
    group=$((group + 1))

    echo "================ $inst_name  m=$VEHICLES obj=$OBJ  ${RUNS} 回 × ${TIME_LIMIT} 秒 ================"
    for run in $(seq 1 "$RUNS"); do
        (( interrupted )) && break
        log="$OUTDIR/logs/${inst_name}_run$(printf '%02d' "$run").log"
        seed=$run

        # ライセンス使用中で無償枠に落ちたら LICENSE_WAIT 秒待ってその 1 回だけやり直す
        lic_try=0
        while :; do
            t0=$(date +%s.%N)
            "$PYTHON" "$SCRIPT" "$TIME_LIMIT" -i "$inst" -m "$VEHICLES" "${obj_opt[@]}" \
                --seed "$seed" --no-plot -q > "$log" 2>&1
            rc=$?
            t1=$(date +%s.%N)
            if [[ $rc -ne 0 ]] && (( lic_try < LICENSE_RETRIES )) && ! (( interrupted )) \
                && grep -q -e "License is in use" -e "Variable limit exceeded" "$log"; then
                lic_try=$((lic_try + 1))
                mv "$log" "${log%.log}.licfail${lic_try}.log"
                echo "  run $run: ライセンスが取れなかったので ${LICENSE_WAIT} 秒後に再実行します (${lic_try}/${LICENSE_RETRIES})"
                sleep "$LICENSE_WAIT"
                continue
            fi
            break
        done
        wall=$(awk -v a="$t0" -v b="$t1" 'BEGIN { printf "%.2f", b - a }')
        if [[ $rc -eq 0 ]]; then status=ok; else status="error($rc)"; fi

        energy=$(field "$log" "energy")
        objective=$(field "$log" "objective")
        vcons=$(field "$log" "violated cons")
        twv=$(field "$log" "tw violations")
        feasible=$(field "$log" "feasible")
        value=$(field "$log" "$value_key")
        travel=$(field "$log" "total travel")
        used=$(field "$log" "used vehicles"); used=${used%%/*}
        vars=$(field "$log" "var_count")
        terms=$(field "$log" "term_count")
        build=$(field "$log" "build")
        tts=$(field "$log" "TTS")

        echo "$n,$inst_name,$VEHICLES,$OBJ,$run,$seed,$status,$energy,$tts,$objective,$vcons,$twv,$feasible,$value,$travel,$used,$vars,$terms,$build,$wall" >> "$RUNS_CSV"
        printf '  run %2d/%d  %-8s energy=%-10s value=%-6s travel=%-6s used=%-2s feasible=%-5s violated=%-4s tw=%-4s tts=%-8s wall=%ss\n' \
            "$run" "$RUNS" "$status" "${energy:--}" "${value:--}" "${travel:--}" "${used:--}" "${feasible:--}" \
            "${vcons:--}" "${twv:--}" "${tts:--}" "$wall"
    done

    # --- このインスタンスの RUNS 回をまとめる。value / travel は実行可能解だけで取る ---
    awk -F',' -v n="$n" -v inst="$inst_name" -v m="$VEHICLES" -v obj="$OBJ" -v out="$SUMMARY_CSV" '
        $2 == inst && $7 == "ok" && $8 != "" {
            k++
            e = $8 + 0; es += e; if (k == 1 || e < emin) emin = e
            ts += $9 + 0
            vs += $11 + 0; tws += $12 + 0
            if ($13 == "True") {
                feas++
                x = $14 + 0; xs += x; if (feas == 1 || x < xmin) xmin = x
                y = $15 + 0; ys += y; if (feas == 1 || y < ymin) ymin = y
            }
            vars = $17; terms = $18
            bs += $19 + 0; ws += $20 + 0
        }
        END {
            if (k == 0) {
                print n "," inst "," m "," obj ",0,,,,,,,,,,,,,," >> out
                printf "  -> 集計できる成功実行なし\n"
                exit
            }
            if (feas > 0) { xm = sprintf("%.2f", xs/feas); xn = xmin; ym = sprintf("%.2f", ys/feas); yn = ymin }
            else          { xm = ""; xn = ""; ym = ""; yn = "" }
            printf "%s,%s,%s,%s,%d,%d,%s,%s,%s,%s,%.2f,%.0f,%.2f,%.2f,%.3f,%s,%s,%.3f,%.2f\n",
                   n, inst, m, obj, k, feas, xm, xn, ym, yn,
                   es/k, emin, vs/k, tws/k, ts/k, vars, terms, bs/k, ws/k >> out
            printf "  -> %s  実行可能解=%d/%d  平均value=%s  最良value=%s  平均違反=%.2f  変数=%s  項=%s\n",
                   inst, feas, k, (xm == "" ? "-" : xm), (xn == "" ? "-" : xn), vs/k, vars, terms
        }' "$RUNS_CSV"
    echo
done

if (( interrupted )); then
    notify "a100 $(basename "$SCRIPT" .py) interrupted" "中断: $OUTDIR" warning
else
    body=$(awk -F',' 'NR > 1 { printf "%s 実行可能 %s/%s 最良 %s\n", $2, $6, $5, ($8 == "" ? "-" : $8) }' "$SUMMARY_CSV")
    notify "a100 $(basename "$SCRIPT" .py) done" "完了: $OUTDIR
$body" white_check_mark
fi

echo "完了: $RUNS_CSV / $SUMMARY_CSV"
column -s, -t "$SUMMARY_CSV" 2>/dev/null || cat "$SUMMARY_CSV"
