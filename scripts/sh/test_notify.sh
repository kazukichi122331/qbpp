#!/usr/bin/env bash
# =============================================================================
# occupancy_long.sh の通知を a100 上で試す（数分で終わる）。
#
#   1. トピック名が読めるか（NTFY_TOPIC か ~/.ntfy_topic）
#   2. a100 から ntfy.sh に直接送れるか（失敗したら curl のエラーをそのまま出す）
#   3. 本番スクリプトを極小条件で最後まで流す
#        n20w20 と n60w20 を各 1 回 × 5 秒、COOLDOWN / GAP 0 秒
#        → iPhone に「sweep done」2 通と「all done」1 通が届けば成功
#      出力は /tmp/occupancy_notify_test/ に置く（lab_results は汚さない）
#
# 使い方（a100 に ssh したあと、リポジトリのルートで）:
#
#   bash scripts/sh/test_notify.sh             # 1〜3 を全部
#   SKIP_RUN=1 bash scripts/sh/test_notify.sh  # 1〜2 だけ（GPU を使わない）
# =============================================================================
set -u

HERE=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
NTFY_SERVER=${NTFY_SERVER:-https://ntfy.sh}

# --- 1. トピック名 ---
if [[ -z ${NTFY_TOPIC:-} && -f ~/.ntfy_topic ]]; then
    NTFY_TOPIC=$(head -n 1 ~/.ntfy_topic | tr -d '[:space:]')
fi
if [[ -z ${NTFY_TOPIC:-} ]]; then
    echo "NG  トピック名がありません。次で作ってください:"
    echo "    echo '<トピック名>' > ~/.ntfy_topic && chmod 600 ~/.ntfy_topic"
    exit 1
fi
echo "OK  トピック名を読みました（${#NTFY_TOPIC} 文字）"

# --- 2. 直接送信 ---
echo "..  $NTFY_SERVER に送信します"
if curl -fsS -m 15 -o /dev/null -H "Title: a100 notify test" -H "Tags: test_tube" \
        --data-binary "a100 ($(hostname)) からのテスト送信 $(date '+%F %T')" \
        "$NTFY_SERVER/$NTFY_TOPIC"; then
    echo "OK  送信できました。iPhone に「a100 notify test」が届いたか確認してください"
else
    echo "NG  送信に失敗しました。詳しい様子:"
    curl -v -m 15 -o /dev/null --data-binary "debug" "$NTFY_SERVER/$NTFY_TOPIC" 2>&1 \
        | grep -E -i "connect|resolve|ssl|tls|certificate|issuer|HTTP/|error" | head -20
    exit 1
fi

[[ -n ${SKIP_RUN:-} ]] && exit 0

# --- 3. 本番スクリプトを極小条件で ---
echo
echo "..  本番スクリプトを極小条件で流します（数分）"
NTFY_TOPIC=$NTFY_TOPIC \
TIME_LIMIT=5 RUNS=1 COOLDOWN=0 GAP=0 \
SIZE_SWEEP="20" WIDTH_SWEEP="20" \
OUT_ROOT=/tmp/occupancy_notify_test \
    bash "$HERE/occupancy_long.sh"
rc=$?
echo
echo "終了 (rc=$rc)。iPhone に通知が 3 通（sweep done ×2・all done）届いていれば成功です"
echo "出力: /tmp/occupancy_notify_test/"
exit $rc
