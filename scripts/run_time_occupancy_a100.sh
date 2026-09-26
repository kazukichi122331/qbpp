#!/usr/bin/env bash
# =============================================================================
# time_occupancy.py (時間展開型・在圏変数版 TSPTW) を A100 上でまとめて計測する。
#
#   SIZES × WIDTHS の各インスタンスを RUNS 回、1 回 TIME_LIMIT 秒。
#   1 インスタンス分の 10 回が終わるたびにプロセスを完全に終了させ、
#   次のインスタンスに移る前に COOLDOWN 秒だけ GPU を明け渡す（共用機のため）。
#
#   既定は「顧客数スイープ」: n = 20/40/60/80/100/150/200、w = 20 固定。
#   「時間窓スイープ」(n = 60 固定、w = 20〜100) は
#   scripts/run_time_occupancy_width_a100.sh が同じ中身を呼ぶ。
#
#   条件は run_time_makespan_a100.sh と揃えてある（GPU 7・10 回 × 30 秒・
#   COOLDOWN 60 秒・ABS3Solver・seed 1〜10）。違いは n200 を足した点だけで、
#   time_makespan 側に n200 の結果はない。--slim は付けない（衝突項は full）。
#
#   既定では target_energy を Dumas の既知最良値（Dumas-best-known-traveltime.txt
#   の Cost 列）に設定し、到達した時刻 TTS を記録する。実行可能解のエネルギーは
#   総移動時間そのものなので、最適解に着けば energy = 既知最良値となり探索が
#   打ち切られる。到達しなければ TIME_LIMIT まで走り、TTS は「その実行の最良解を
#   見つけた時刻」になる（reached=0 で区別する）。
#   注意: 三角不等式が破れるインスタンスでは QUBO 上の最適値が既知最良値より
#   +1〜+3 大きくなることがあり（time_occupancy.py の末尾の注記）、その場合は
#   何回回しても reached=0 になる。
#
# 使い方（リモート機に ssh したあと、リポジトリのルートで）:
#
#   bash scripts/run_time_occupancy_a100.sh                        # GPU 7 を使う（既定）
#   CUDA_VISIBLE_DEVICES=3 bash scripts/run_time_occupancy_a100.sh  # 別の GPU を使う
#   nohup bash scripts/run_time_occupancy_a100.sh > /dev/null 2>&1 &   # 放置する場合
#
# 環境変数で上書きできる（既定値は下の DEFAULT 群）:
#   PYTHON      python 実行系                     (既定 .venv/bin/python)
#   SIZES       顧客数の並び                      (既定 "20 40 60 80 100 150 200")
#   WIDTHS      時間枠幅 w の並び                 (既定 "20" … n200 は 20/40 のみ)
#   INST_ID     インスタンス番号                  (既定 001)
#   RUNS        1 インスタンスあたりの実行回数    (既定 10)
#   TIME_LIMIT  1 回のソルバ制限時間（秒）        (既定 30)
#   COOLDOWN    インスタンス間の待ち時間（秒）    (既定 60)
#   RUN_TIMEOUT 1 回の上限（秒）。0 で無制限      (既定 0)
#   TARGET      target_energy の決め方            (既定 best)
#                 best  … 既知最良値（BEST_FILE から引く）
#                 none  … 指定しない（従来どおり TIME_LIMIT まで探索）
#                 数値  … 全インスタンスにその値を使う
#   BEST_FILE   既知最良値の表                    (既定 instances/Dumas/Dumas-best-known-traveltime.txt)
#   CUDA_VISIBLE_DEVICES  使う GPU 番号            (既定 7)
#   OUTDIR      出力先                            (既定 lab_results/time_occupancy_a100_<条件>_<日時>)
#
# 出力:
#   $OUTDIR/runs.csv     1 行 = 1 実行（生の計測値。target_energy / reached / tts を含む）
#   $OUTDIR/summary.csv  1 行 = 1 インスタンス（平均エネルギー・最小エネルギー・
#                        到達回数・到達した実行の平均 TTS 等）
#   $OUTDIR/logs/*.log   各実行の標準出力そのまま
#   $OUTDIR/env.txt      GPU・python・git コミットの記録
# =============================================================================
set -u -o pipefail

PYTHON=${PYTHON:-.venv/bin/python}
SIZES=${SIZES:-"20 40 60 80 100 150 200"}
WIDTHS=${WIDTHS:-${WIDTH:-20}}          # WIDTH= も旧版との互換で受ける
INST_ID=${INST_ID:-001}
RUNS=${RUNS:-10}
TIME_LIMIT=${TIME_LIMIT:-30}
COOLDOWN=${COOLDOWN:-60}
RUN_TIMEOUT=${RUN_TIMEOUT:-0}
TARGET=${TARGET:-best}
BEST_FILE=${BEST_FILE:-instances/Dumas/Dumas-best-known-traveltime.txt}

# 共用機なので GPU は 1 枚だけ使う。子プロセス（python）に必ず引き継ぐので export。
# 別の番号にしたいときは CUDA_VISIBLE_DEVICES=3 bash scripts/... と前置きすればよい。
export CUDA_VISIBLE_DEVICES=${CUDA_VISIBLE_DEVICES:-7}
STAMP=$(date +%m%d%H%M)
TAG="n$(echo "$SIZES" | tr ' ' '-')_w$(echo "$WIDTHS" | tr ' ' '-')"
OUTDIR=${OUTDIR:-lab_results/time_occupancy_a100_${TAG}_$STAMP}

SCRIPT=${SCRIPT:-src/time_occupancy_target_energy.py}

# --- リポジトリのルートから実行しているか確認（相対パスを持っているため） ---
if [[ ! -f $SCRIPT || ! -d instances/Dumas ]]; then
    echo "ERROR: リポジトリのルートで実行してください（$SCRIPT が見つからない）" >&2
    exit 1
fi
if [[ ! -x $PYTHON ]] && ! command -v "$PYTHON" > /dev/null 2>&1; then
    echo "ERROR: python が見つからない: $PYTHON （PYTHON=... で指定できる）" >&2
    exit 1
fi
if [[ $TARGET == best && ! -f $BEST_FILE ]]; then
    echo "ERROR: 既知最良値の表が見つからない: $BEST_FILE （TARGET=none で無効化できる）" >&2
    exit 1
fi

# インスタンス名 (例 n60w20.001) から target_energy を決める。空なら指定なし。
target_for() {                  # target_for <inst_name>
    case $TARGET in
        none|"") ;;
        best) awk -v name="$1.txt" '$1 == name { print $2; exit }' "$BEST_FILE" ;;
        *)    echo "$TARGET" ;;
    esac
}

mkdir -p "$OUTDIR/logs"
RUNS_CSV=$OUTDIR/runs.csv
SUMMARY_CSV=$OUTDIR/summary.csv

# --- 実験環境の記録（あとで結果を見返すときに効く） ---
{
    echo "date        = $(date '+%F %T')"
    echo "host        = $(hostname)"
    echo "python      = $($PYTHON -V 2>&1)  ($PYTHON)"
    echo "git commit  = $(git rev-parse --short HEAD 2>/dev/null || echo '-')"
    echo "script      = $SCRIPT"
    echo "sizes       = $SIZES   widths = $WIDTHS   inst = $INST_ID"
    echo "runs        = $RUNS    time_limit = ${TIME_LIMIT}s   cooldown = ${COOLDOWN}s"
    echo "target      = $TARGET$([[ $TARGET == best ]] && echo "  ($BEST_FILE)")"
    echo "gpu         = CUDA_VISIBLE_DEVICES=$CUDA_VISIBLE_DEVICES"
    echo "--- nvidia-smi ---"
    nvidia-smi -i "$CUDA_VISIBLE_DEVICES" 2>&1 || nvidia-smi 2>&1 || echo "(nvidia-smi なし)"
} > "$OUTDIR/env.txt"

echo "出力先: $OUTDIR"
sed -n '1,10p' "$OUTDIR/env.txt"
echo

echo "n,instance,run,seed,status,target_energy,energy,reached,tts,objective,violated_cons,tw_violations,feasible,var_count,term_count,build_sec,wall_sec" > "$RUNS_CSV"
echo "n,instance,runs_ok,target_energy,reached_count,tts_mean,tts_min,tts_max,energy_mean,energy_min,violated_cons_mean,violated_cons_min,tw_violations_mean,feasible_count,var_count,term_count,build_sec_mean,wall_sec_mean" > "$SUMMARY_CSV"

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

group=0
for n in $SIZES; do
  for w in $WIDTHS; do
    (( interrupted )) && break 2
    inst_name="n${n}w${w}.${INST_ID}"
    inst="instances/Dumas/${inst_name}.txt"
    if [[ ! -f $inst ]]; then
        echo "SKIP $inst_name : インスタンスがない ($inst)"
        continue
    fi

    # --- 前のインスタンスとの間に GPU を明け渡す時間を挟む（最初は待たない） ---
    if (( group > 0 )) && [[ $COOLDOWN -gt 0 ]]; then
        echo "  (GPU を ${COOLDOWN} 秒明け渡します)"
        sleep "$COOLDOWN"
        echo
    fi
    group=$((group + 1))

    target=$(target_for "$inst_name")
    target_opt=()
    if [[ -n $target ]]; then
        target_opt=(--target-energy "$target")
    elif [[ $TARGET == best ]]; then
        echo "WARN $inst_name : $BEST_FILE に既知最良値がないので target_energy なしで実行"
    fi

    echo "================ $inst_name  (n=$n w=$w)  ${RUNS} 回 × ${TIME_LIMIT} 秒  target=${target:--} ================"
    for run in $(seq 1 "$RUNS"); do
        (( interrupted )) && break
        log="$OUTDIR/logs/${inst_name}_run$(printf '%02d' "$run").log"
        seed=$run

        # 1 回 = 1 プロセス。終われば GPU のメモリもコンテキストも必ず解放される。
        t0=$(date +%s.%N)
        if [[ $RUN_TIMEOUT -gt 0 ]]; then
            timeout "$RUN_TIMEOUT" "$PYTHON" "$SCRIPT" "$TIME_LIMIT" \
                -i "$inst" --seed "$seed" "${target_opt[@]}" --no-plot -q > "$log" 2>&1
        else
            "$PYTHON" "$SCRIPT" "$TIME_LIMIT" \
                -i "$inst" --seed "$seed" "${target_opt[@]}" --no-plot -q > "$log" 2>&1
        fi
        rc=$?
        t1=$(date +%s.%N)
        wall=$(awk -v a="$t0" -v b="$t1" 'BEGIN { printf "%.2f", b - a }')

        if [[ $rc -eq 0 ]]; then status=ok
        elif [[ $rc -eq 124 ]]; then status=timeout
        else status="error($rc)"
        fi

        energy=$(field "$log" "energy")
        objective=$(field "$log" "objective")
        vcons=$(field "$log" "violated cons")
        twv=$(field "$log" "tw violations")
        feasible=$(field "$log" "feasible")
        vars=$(field "$log" "var_count")
        terms=$(field "$log" "term_count")
        build=$(field "$log" "build")
        tts=$(field "$log" "TTS")
        # reached: target_energy に到達したか（1/0）。target なしなら空。
        reached=""
        if [[ -n $target && -n $energy ]]; then
            reached=$(awk -v e="$energy" -v t="$target" 'BEGIN { print (e + 0 <= t + 0) ? 1 : 0 }')
        fi

        echo "$n,$inst_name,$run,$seed,$status,$target,$energy,$reached,$tts,$objective,$vcons,$twv,$feasible,$vars,$terms,$build,$wall" >> "$RUNS_CSV"
        printf '  run %2d/%d  %-8s energy=%-12s reached=%-2s tts=%-8s violated=%-4s tw=%-4s feasible=%-5s vars=%-8s terms=%-9s build=%-8s wall=%ss\n' \
            "$run" "$RUNS" "$status" "${energy:--}" "${reached:--}" "${tts:--}" "${vcons:--}" "${twv:--}" \
            "${feasible:--}" "${vars:--}" "${terms:--}" "${build:--}" "$wall"
    done

    # --- このインスタンスの 10 回をまとめる（instance 名で束ねるので n 固定の掃引でも効く） ---
    # TTS の統計は target に到達した実行だけで取る（未到達は TIME_LIMIT 打ち切りで意味が違う）。
    awk -F',' -v n="$n" -v inst="$inst_name" -v target="$target" -v out="$SUMMARY_CSV" '
        $2 == inst && $5 == "ok" && $7 != "" {
            k++
            e = $7 + 0
            es += e; if (k == 1 || e < emin) emin = e
            if ($8 == "1" && $9 != "") {
                r++
                t = $9 + 0
                ts += t
                if (r == 1 || t < tmin) tmin = t
                if (r == 1 || t > tmax) tmax = t
            }
            v = $11 + 0; vs += v; if (k == 1 || v < vmin) vmin = v
            tws += $12 + 0
            if ($13 == "True") feas++
            vars = $14; terms = $15
            bs += $16 + 0; ws += $17 + 0
        }
        END {
            if (k == 0) {
                print n "," inst ",0," target ",,,,,,,,,,,,,," >> out
                printf "  -> 集計できる成功実行なし\n"
                exit
            }
            if (r > 0) { tmean = sprintf("%.3f", ts/r); tmn = sprintf("%.3f", tmin); tmx = sprintf("%.3f", tmax) }
            else       { tmean = ""; tmn = ""; tmx = "" }
            rc = (target == "") ? "" : r + 0
            printf "%s,%s,%d,%s,%s,%s,%s,%s,%.2f,%.0f,%.2f,%.0f,%.2f,%d,%s,%s,%.3f,%.2f\n",
                   n, inst, k, target, rc, tmean, tmn, tmx,
                   es/k, emin, vs/k, vmin, tws/k, feas, vars, terms, bs/k, ws/k >> out
            printf "  -> %s  平均energy=%.2f  最小energy=%.0f  平均違反=%.2f  " \
                   "実行可能解=%d/%d  変数=%s  項=%s\n",
                   inst, es/k, emin, vs/k, feas, k, vars, terms
            if (target != "")
                printf "     target=%s  到達=%d/%d  平均TTS=%s  最小TTS=%s  最大TTS=%s\n",
                       target, r, k, (tmean == "" ? "-" : tmean " s"),
                       (tmn == "" ? "-" : tmn " s"), (tmx == "" ? "-" : tmx " s")
        }' "$RUNS_CSV"
    echo
  done
done

echo "完了: $RUNS_CSV / $SUMMARY_CSV"
column -s, -t "$SUMMARY_CSV" 2>/dev/null || cat "$SUMMARY_CSV"
