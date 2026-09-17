#!/usr/bin/env bash
# =============================================================================
# order_cumulative.py (順序型・累積式) の「モデルサイズ掃引」。
#
#   顧客数 n = 20/40/60/80/100/150 を 1 本ずつ構築し、
#   **変数の数と項の数だけ** を取り出して並べる。
#
#   この定式化は t[i] が t[i-1] を丸ごと含むので構築コスト・モデルサイズが
#   Θ(N^4) になり、n が大きいと実行可能解はまず得られない（order_cumulative.py
#   の docstring 弱点 1）。解の質を見るのが目的ではないので、制限時間は
#   既定 1 秒に固定して探索は形だけ回す。var_count / term_count は
#   ソルバに渡した後でないと出てこないため --build-only は使えない。
#
#   1 インスタンス 1 回だけ。変数数・項数は決定的なので繰り返す意味がない。
#
#   Θ(N^4) はメモリにも効く。実測で n=100 の最大常駐メモリは 24 GB、
#   n=150 はその (151/101)^4 ≒ 5 倍で 100 GB を超える見込み。31 GiB の WSL では
#   n=150 は構築の途中で OOM kill され (status=killed(137))、値が取れない。
#   そのため最大常駐メモリ (maxrss_mb) も記録する。
#
# 使い方（リポジトリのルートで）:
#
#   bash scripts/run_order_cumulative_modelsize.sh
#   CUDA_VISIBLE_DEVICES=0 bash scripts/run_order_cumulative_modelsize.sh
#   nohup bash scripts/run_order_cumulative_modelsize.sh > /dev/null 2>&1 &
#
# 環境変数で上書きできる:
#   PYTHON      python 実行系                     (既定 .venv/bin/python)
#   SCRIPT      対象の定式化                      (既定 src/order_cumulative.py)
#   SIZES       顧客数の並び                      (既定 "20 40 60 80 100 150")
#   WIDTH       時間枠幅 w                        (既定 20)
#   INST_ID     インスタンス番号                  (既定 001)
#   TIME_LIMIT  1 回のソルバ制限時間（秒）        (既定 1)
#   RUN_TIMEOUT 1 回の上限（秒）。0 で無制限      (既定 0)
#   CUDA_VISIBLE_DEVICES  使う GPU 番号            (既定 7。手元の WSL なら 0)
#   OUTDIR      出力先            (既定 lab_results/order_cumulative_modelsize_<条件>_<日時>)
#
# 出力:
#   $OUTDIR/modelsize.csv  1 行 = 1 インスタンス（変数数・項数・最大メモリ）
#   $OUTDIR/logs/*.log     各実行の標準出力そのまま（行バッファなので途中で
#                          kill されても残る）
#   $OUTDIR/logs/*.time    /usr/bin/time の記録（最大常駐メモリ・終了シグナル）
#   $OUTDIR/env.txt        GPU・python・git コミットの記録
# =============================================================================
set -u -o pipefail

PYTHON=${PYTHON:-.venv/bin/python}
SCRIPT=${SCRIPT:-src/order_cumulative.py}
SIZES=${SIZES:-"20 40 60 80 100 150"}
WIDTH=${WIDTH:-20}
INST_ID=${INST_ID:-001}
TIME_LIMIT=${TIME_LIMIT:-1}
RUN_TIMEOUT=${RUN_TIMEOUT:-0}

# 共用機なので GPU は 1 枚だけ使う。子プロセス（python）に必ず引き継ぐので export。
export CUDA_VISIBLE_DEVICES=${CUDA_VISIBLE_DEVICES:-7}
# リダイレクト先がファイルだと python は出力をため込む。OOM kill されると
# それが丸ごと消えてどこで落ちたか分からなくなるので、行ごとに吐かせる。
export PYTHONUNBUFFERED=1
STAMP=$(date +%m%d%H%M)
NAME=$(basename "$SCRIPT" .py)
TAG="n$(echo "$SIZES" | tr ' ' '-')_w${WIDTH}"
OUTDIR=${OUTDIR:-lab_results/${NAME}_modelsize_${TAG}_$STAMP}

# --- リポジトリのルートから実行しているか確認（相対パスを持っているため） ---
if [[ ! -f $SCRIPT || ! -d instances/Dumas ]]; then
    echo "ERROR: リポジトリのルートで実行してください（$SCRIPT が見つからない）" >&2
    exit 1
fi
if [[ ! -x $PYTHON ]] && ! command -v "$PYTHON" > /dev/null 2>&1; then
    echo "ERROR: python が見つからない: $PYTHON （PYTHON=... で指定できる）" >&2
    exit 1
fi

mkdir -p "$OUTDIR/logs"
CSV=$OUTDIR/modelsize.csv

{
    echo "date        = $(date '+%F %T')"
    echo "host        = $(hostname)"
    echo "python      = $($PYTHON -V 2>&1)  ($PYTHON)"
    echo "git commit  = $(git rev-parse --short HEAD 2>/dev/null || echo '-')"
    echo "script      = $SCRIPT"
    echo "sizes       = $SIZES   width = $WIDTH   inst = $INST_ID"
    echo "time_limit  = ${TIME_LIMIT}s （変数数・項数だけ見るので探索はしない扱い）"
    echo "gpu         = CUDA_VISIBLE_DEVICES=$CUDA_VISIBLE_DEVICES"
    echo "memory      = $(free -g | awk '/^Mem:/ { print $2 " GiB (available " $7 " GiB)" }')"
    echo "--- nvidia-smi ---"
    nvidia-smi -i "$CUDA_VISIBLE_DEVICES" 2>&1 || nvidia-smi 2>&1 || echo "(nvidia-smi なし)"
} > "$OUTDIR/env.txt"

echo "出力先: $OUTDIR"
sed -n '1,9p' "$OUTDIR/env.txt"
echo

echo "n,instance,N,status,x_vars,w_vars,var_count,term_count,build_sec,wall_sec,maxrss_mb" > "$CSV"

# ログから "見出し = 値" の値を 1 つ取り出す（最初に一致した行の 1 トークン目）
field() {                       # field <log> <行頭の見出し>
    awk -v key="$2" '
        index($0, key) == 1 {
            sub(/^[^=]*=[ \t]*/, "", $0)
            print $1
            exit
        }' "$1"
}

# 行の途中にある "<見出し> = <数>" を取り出す（"N=21  x vars = 441  w vars = 21"）
inline() {                      # inline <log> <見出し>
    sed -n "s/.*$2 = \([0-9][0-9]*\).*/\1/p" "$1" | head -1
}

interrupted=0
trap 'interrupted=1; echo; echo "中断されました（$OUTDIR に途中までの結果が残っています）"' INT TERM

printf '%-6s %-14s %-10s %-10s %-12s %-10s %-9s %s\n' \
       n instance x_vars var_count term_count build wall maxrss

for n in $SIZES; do
    (( interrupted )) && break
    inst_name="n${n}w${WIDTH}.${INST_ID}"
    inst="instances/Dumas/${inst_name}.txt"
    if [[ ! -f $inst ]]; then
        echo "SKIP $inst_name : インスタンスがない ($inst)"
        continue
    fi

    log="$OUTDIR/logs/${inst_name}.log"
    timefile="$OUTDIR/logs/${inst_name}.time"

    # 最大常駐メモリを測る（OOM kill されたときは終了シグナルもここに残る）。
    cmd=("$PYTHON" "$SCRIPT" "$TIME_LIMIT" -i "$inst" --no-plot -q)
    [[ -x /usr/bin/time ]] && cmd=(/usr/bin/time -f "maxrss_kb = %M  elapsed = %E" \
                                   -o "$timefile" "${cmd[@]}")
    [[ $RUN_TIMEOUT -gt 0 ]] && cmd=(timeout "$RUN_TIMEOUT" "${cmd[@]}")

    t0=$(date +%s.%N)
    "${cmd[@]}" > "$log" 2>&1
    rc=$?
    t1=$(date +%s.%N)
    wall=$(awk -v a="$t0" -v b="$t1" 'BEGIN { printf "%.2f", b - a }')

    if [[ $rc -eq 0 ]]; then status=ok
    elif [[ $rc -eq 124 ]]; then status=timeout
    elif [[ $rc -eq 137 ]]; then status="killed(137)"      # OOM kill の可能性が高い
    else status="error($rc)"
    fi

    bigN=$(sed -n 's/^N=\([0-9][0-9]*\).*/\1/p' "$log" | head -1)
    xv=$(inline "$log" "x vars")
    wv=$(inline "$log" "w vars")
    vars=$(field "$log" "var_count")
    terms=$(field "$log" "term_count")
    build=$(field "$log" "build")
    rss=$(sed -n 's/^maxrss_kb = \([0-9][0-9]*\).*/\1/p' "$timefile" 2>/dev/null | head -1)
    rss=$(awk -v k="${rss:-}" 'BEGIN { if (k != "") printf "%.0f", k / 1024 }')

    echo "$n,$inst_name,$bigN,$status,$xv,$wv,$vars,$terms,$build,$wall,$rss" >> "$CSV"
    printf '%-6s %-14s %-10s %-10s %-12s %-10s %-9s %s' \
           "$n" "$inst_name" "${xv:--}" "${vars:--}" "${terms:--}" \
           "${build:--}" "${wall}s" "${rss:--}MB"
    [[ $status == ok ]] && echo || echo "   <- $status（$log / $timefile を見てください）"
done

echo
echo "完了: $CSV"
column -s, -t "$CSV" 2>/dev/null || cat "$CSV"
