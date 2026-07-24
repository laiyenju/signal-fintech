#!/usr/bin/env bash
# SIGNAL：把本輪 newsroom 日誌寫入 GitHub Wiki（soft-fail，不中斷出刊）。
# 用法（在 repo 根目錄）：
#   scripts/newsroom_wiki.sh <outcome> <today>
#   <outcome> = published | no_change | fail_safe
#   <today>   = YYYY-MM-DD（台北日，與 candidate.meta.json 的 today 相同）
# 需要：candidate.meta.json、candidate.json、scripts/raw_items.json
# 環境：
#   NEWSROOM_WIKI=0          → 跳過（印 skipped）
#   NEWSROOM_WIKI_TOKEN      → 建議：可寫 wiki 的 fine-grained/classic PAT（scope 含 repo／wiki）
#   GH_TOKEN / GITHUB_TOKEN  → 備援 token（若具 wiki 寫權）
# 狀態：stdout 最後一行必為 newsroom_wiki=ok|failed|skipped …

set -u

OUTCOME="${1:-}"
TODAY="${2:-}"
WIKI="${NEWSROOM_WIKI_DIR:-/tmp/newsroom-wiki}"
OWNER_REPO_WIKI="laiyenju/signal-fintech.wiki"
PUBLIC_URL="https://github.com/${OWNER_REPO_WIKI}.git"

emit() {
  # 單行狀態；勿在之後再 echo 別的到 stdout 混進 PR body
  echo "$1"
}

if [ -z "$OUTCOME" ] || [ -z "$TODAY" ]; then
  emit "newsroom_wiki=failed outcome=${OUTCOME:-unknown} today=${TODAY:-unknown} reason=unknown detail=usage_outcome_today_required"
  exit 0
fi

if [ "${NEWSROOM_WIKI:-1}" = "0" ]; then
  emit "newsroom_wiki=skipped outcome=${OUTCOME} today=${TODAY} reason=NEWSROOM_WIKI=0"
  exit 0
fi

for f in candidate.meta.json candidate.json scripts/raw_items.json scripts/newsroom.py; do
  if [ ! -f "$f" ]; then
    emit "newsroom_wiki=failed outcome=${OUTCOME} today=${TODAY} reason=render detail=missing_${f//\//_}"
    exit 0
  fi
done

resolve_token() {
  if [ -n "${NEWSROOM_WIKI_TOKEN:-}" ]; then
    printf '%s' "$NEWSROOM_WIKI_TOKEN"
    return 0
  fi
  if [ -n "${GH_TOKEN:-}" ]; then
    printf '%s' "$GH_TOKEN"
    return 0
  fi
  if [ -n "${GITHUB_TOKEN:-}" ]; then
    printf '%s' "$GITHUB_TOKEN"
    return 0
  fi
  if command -v gh >/dev/null 2>&1; then
    gh auth token 2>/dev/null || true
    return 0
  fi
  printf ''
}

auth_remote() {
  local token="$1"
  # x-access-token 適用 PAT / ghs_ / gho_
  printf 'https://x-access-token:%s@github.com/%s.git' "$token" "$OWNER_REPO_WIKI"
}

TOKEN="$(resolve_token || true)"
rm -rf "$WIKI"

CLONE_OK=0
CLONE_VIA=""

# 1) 帶 token 的 HTTPS（雲端寫 wiki 的正解；匿名 clone 成功也 push 不了）
if [ -n "$TOKEN" ]; then
  if git clone --depth 1 "$(auth_remote "$TOKEN")" "$WIKI" >/tmp/newsroom-wiki-clone.log 2>&1; then
    CLONE_OK=1
    CLONE_VIA="https_token"
  fi
fi

# 2) gh repo clone（若環境有 gh 且已登入）
if [ "$CLONE_OK" != "1" ] && command -v gh >/dev/null 2>&1; then
  rm -rf "$WIKI"
  if gh repo clone "$OWNER_REPO_WIKI" "$WIKI" -- --depth 1 >/tmp/newsroom-wiki-clone.log 2>&1; then
    CLONE_OK=1
    CLONE_VIA="gh"
    # 若有 token，把 remote 改成帶憑證，避免 push 又變匿名
    if [ -n "$TOKEN" ]; then
      git -C "$WIKI" remote set-url origin "$(auth_remote "$TOKEN")" || true
    fi
  fi
fi

# 3) 匿名 HTTPS（多半只能讀 public wiki；push 預期 403——仍嘗試以利錯誤訊息）
if [ "$CLONE_OK" != "1" ]; then
  rm -rf "$WIKI"
  if git clone --depth 1 "$PUBLIC_URL" "$WIKI" >/tmp/newsroom-wiki-clone.log 2>&1; then
    CLONE_OK=1
    CLONE_VIA="https_anon"
    if [ -n "$TOKEN" ]; then
      git -C "$WIKI" remote set-url origin "$(auth_remote "$TOKEN")" || true
    fi
  fi
fi

# 4) SSH 備援（雲端常被 proxy 改寫；有金鑰時可試）
if [ "$CLONE_OK" != "1" ]; then
  rm -rf "$WIKI"
  if git clone --depth 1 "git@github.com:${OWNER_REPO_WIKI}.git" "$WIKI" >/tmp/newsroom-wiki-clone.log 2>&1; then
    CLONE_OK=1
    CLONE_VIA="ssh"
  fi
fi

if [ "$CLONE_OK" != "1" ]; then
  detail="clone_failed"
  if [ -z "$TOKEN" ]; then
    detail="clone_failed_no_token_set_NEWSROOM_WIKI_TOKEN"
  fi
  emit "newsroom_wiki=failed outcome=${OUTCOME} today=${TODAY} reason=clone detail=${detail}"
  exit 0
fi

# 確保 push 用的 remote 帶 token（gh/anon clone 後很重要）
if [ -n "$TOKEN" ]; then
  git -C "$WIKI" remote set-url origin "$(auth_remote "$TOKEN")" 2>/dev/null || true
fi

if ! NEWSROOM_DIR="$WIKI" python scripts/newsroom.py \
    candidate.meta.json candidate.json scripts/raw_items.json "$OUTCOME" \
    >/tmp/newsroom-wiki-render.log 2>&1; then
  emit "newsroom_wiki=failed outcome=${OUTCOME} today=${TODAY} reason=render detail=newsroom_py_failed"
  exit 0
fi

git -C "$WIKI" add -A
if git -C "$WIKI" diff --cached --quiet 2>/dev/null; then
  emit "newsroom_wiki=ok outcome=${OUTCOME} today=${TODAY} detail=no_git_change via=${CLONE_VIA}"
  exit 0
fi

# commit 身分（雲端常缺）
git -C "$WIKI" config user.email >/dev/null 2>&1 || \
  git -C "$WIKI" config user.email "newsroom-bot@users.noreply.github.com"
git -C "$WIKI" config user.name >/dev/null 2>&1 || \
  git -C "$WIKI" config user.name "SIGNAL Newsroom"

MSG="newsroom：${TODAY} ${OUTCOME} 選稿日誌（$(TZ=Asia/Taipei date +'%Y-%m-%d %H:%M')）"
if ! git -C "$WIKI" commit -m "$MSG" >/tmp/newsroom-wiki-commit.log 2>&1; then
  emit "newsroom_wiki=failed outcome=${OUTCOME} today=${TODAY} reason=commit detail=git_commit_failed"
  exit 0
fi

if [ -z "$TOKEN" ] && [ "$CLONE_VIA" = "https_anon" ]; then
  emit "newsroom_wiki=failed outcome=${OUTCOME} today=${TODAY} reason=push detail=no_token_anon_clone_cannot_push_set_NEWSROOM_WIKI_TOKEN"
  exit 0
fi

PUSH_LOG=/tmp/newsroom-wiki-push.log
if git -C "$WIKI" push origin HEAD:master >"$PUSH_LOG" 2>&1; then
  emit "newsroom_wiki=ok outcome=${OUTCOME} today=${TODAY} detail=pushed via=${CLONE_VIA}"
  exit 0
fi

# 分類常見錯誤，方便對照設定步驟
DETAIL="git_push_failed"
if grep -qiE '403|Write access|Permission|denied|Authentication failed|Invalid username' "$PUSH_LOG" 2>/dev/null; then
  if [ -z "$TOKEN" ]; then
    DETAIL="http_403_or_auth_no_token_set_NEWSROOM_WIKI_TOKEN"
  else
    DETAIL="http_403_token_lacks_wiki_write_or_egress_blocked"
  fi
elif grep -qiE 'timed out|Could not resolve|Network|proxy|407' "$PUSH_LOG" 2>/dev/null; then
  DETAIL="network_or_egress_blocked"
fi

emit "newsroom_wiki=failed outcome=${OUTCOME} today=${TODAY} reason=push detail=${DETAIL}"
exit 0
