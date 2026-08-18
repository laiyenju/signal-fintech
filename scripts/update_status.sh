#!/usr/bin/env bash
# SIGNAL：每輪（含 no_change / fail_safe）把「最後檢查時戳」寫回 main 的 status.json，
# 讓網站能顯示「最後檢查：N 分鐘前」，與「內容更新於」（data.json 的 _generated_at）區分：
# 前者證明排程活著，後者代表內容真的變了。
# 用法（在 repo 根目錄）：
#   scripts/update_status.sh <outcome> "<newsroom_wiki 狀態行>"
# 走 GitHub contents API 直接寫 main（不動本地 git 狀態、不需另開 PR）。
# Soft-fail：任何失敗不得中斷排程；stdout 最後一行必為 status_json=ok|failed|skipped …
# 環境：STATUS_JSON=0 → 跳過；需 gh 已登入（與開 PR 同一憑證）。

set -u

OUTCOME="${1:-unknown}"
NEWSROOM_LINE="${2:-}"
OWNER_REPO="laiyenju/signal-fintech"
TMP="${TMPDIR:-/tmp}/signal-status.json"

if [ "${STATUS_JSON:-1}" = "0" ]; then
  echo "status_json=skipped outcome=${OUTCOME} reason=STATUS_JSON=0"
  exit 0
fi

if ! command -v gh >/dev/null 2>&1; then
  echo "status_json=failed outcome=${OUTCOME} reason=no_gh"
  exit 0
fi

CHECKED_AT="$(date -u +'%Y-%m-%dT%H:%M:%SZ')"
printf '{\n  "checked_at": "%s",\n  "outcome": "%s",\n  "newsroom_wiki": "%s"\n}\n' \
  "$CHECKED_AT" "$OUTCOME" "${NEWSROOM_LINE//\"/\\\"}" > "$TMP"

if command -v base64 >/dev/null 2>&1 && base64 --help 2>&1 | grep -q -- '-w'; then
  CONTENT="$(base64 -w0 "$TMP")"
else
  CONTENT="$(base64 "$TMP" | tr -d '\n')"
fi

# 既有檔案要帶 sha 才能覆寫；404（首次建立）時 SHA 留空
SHA="$(gh api "repos/${OWNER_REPO}/contents/status.json?ref=main" --jq .sha 2>/dev/null || true)"

if gh api -X PUT "repos/${OWNER_REPO}/contents/status.json" \
    -f message="status: ${OUTCOME}（${CHECKED_AT}）" \
    -f content="$CONTENT" \
    -f branch="main" \
    ${SHA:+-f sha="$SHA"} \
    >/dev/null 2>/tmp/status-json-push.log; then
  echo "status_json=ok outcome=${OUTCOME} checked_at=${CHECKED_AT}"
else
  echo "status_json=failed outcome=${OUTCOME} reason=api_put detail=$(head -c 120 /tmp/status-json-push.log 2>/dev/null | tr '\n' ' ' | tr -s ' ')"
fi
exit 0
