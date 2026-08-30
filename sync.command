#!/bin/bash
# うちの子サイズ — コード更新をGitHubへ送る
cd "$(dirname "$0")" || exit 1

fail () { echo; echo "!! $1"; echo; read -p "Enterキーで閉じます " _; exit 1; }

# 前回の作業で残ったロックファイルを掃除する
rm -f .git/index.lock
find .git/objects -name 'tmp_obj_*' -delete 2>/dev/null
rm -f data/*.db data/*.db-journal data/*.db-wal data/*.db-shm 2>/dev/null
rm -f tools/diag_rakuten.py 2>/dev/null   # 役目を終えた一時ファイル

REPO="munaggggg-ctrl/uchinoko-size"
[ -f .token ] || fail ".token がありません。チャットで「同期したい」とお伝えください"
TOKEN=$(tr -d '[:space:]' < .token)

echo "== テスト =="
python3 tests/run.py || fail "テストに失敗したため送信を中止しました"

echo
echo "== 変更内容 =="
git add -A
git status --short
if git diff --staged --quiet; then
  echo "  変更はありません"
  rm -f .token
  read -p "Enterキーで閉じます " _; exit 0
fi

MSG=${1:-"update: $(date +%Y-%m-%d\ %H:%M)"}
git commit -q -m "$MSG"

echo
echo "== GitHubへ送信 =="
git push "https://x-access-token:${TOKEN}@github.com/${REPO}.git" main || fail "送信に失敗しました"
rm -f .token

echo
echo "===================================="
echo " 送信しました。"
echo " https://github.com/${REPO}/actions"
echo " ↑ ここで自動チェックの結果が見られます"
echo "===================================="
echo
read -p "Enterキーで閉じます " _
