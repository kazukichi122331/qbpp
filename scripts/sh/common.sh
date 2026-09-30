# =============================================================================
# 結果フォルダの名前を決める共通部品。各 sh から source して使う（単体では実行しない）。
#
#   source "$(dirname "${BASH_SOURCE[0]}")/common.sh"
#   OUTDIR=${OUTDIR:-$(result_dir occupancy "$(sweep_tag "$SIZES" "$WIDTHS")" ...)}
#
# 命名: <OUT_ROOT>/<月日>-<時分>_<モデル>_<条件>[_<備考>...][_<ホスト>]
#   例  lab_results/0928-1421_makespan_nsweep
#       lab_results/0928-2329_occupancy_nsweep_t300
#       lab_results/0929-2207_multi_leq_m2_wsl
#   - 日時は開始時刻。先頭に置くので ls で時系列順に並ぶ
#   - 既定値と違う条件だけを備考として足す（t300, notarget, m2 など）。
#     細かい条件（n・w の並び、回数など）は env.txt に残るので名前には入れない
#   - A100（a100x8）は既定なので何も付けない。WSL なら _wsl、それ以外はホスト名
# =============================================================================

OUT_ROOT=${OUT_ROOT:-lab_results}

# result_dir <モデル> [<条件・備考>...]   空の引数は飛ばす
result_dir() {
    local name part host
    name=$(date +%m%d-%H%M)
    for part in "$@"; do
        [[ -n $part ]] && name+="_$part"
    done
    host=$(hostname)
    if grep -qi microsoft /proc/version 2> /dev/null; then
        name+="_wsl"
    elif [[ $host != a100x8 ]]; then
        name+="_$host"
    fi
    echo "$OUT_ROOT/$name"
}

# sweep_tag <sizes> <widths>
#   顧客数だけ複数 → nsweep、時間窓だけ複数 → wsweep、両方 1 つ → n40w20、両方複数 → n20-40_w20-60
sweep_tag() {
    local -a s=($1) w=($2)
    if (( ${#s[@]} > 1 && ${#w[@]} == 1 )); then
        echo nsweep
    elif (( ${#s[@]} == 1 && ${#w[@]} > 1 )); then
        echo wsweep
    elif (( ${#s[@]} == 1 && ${#w[@]} == 1 )); then
        echo "n${s[0]}w${w[0]}"
    else
        echo "n$(echo "${s[*]}" | tr ' ' '-')_w$(echo "${w[*]}" | tr ' ' '-')"
    fi
}

# time_tag <秒> <既定の秒>   既定と違うときだけ t<秒> を返す（小数点以下は切る）
time_tag() {
    [[ ${1%.*} != "${2%.*}" ]] && echo "t${1%.*}"
    return 0
}
