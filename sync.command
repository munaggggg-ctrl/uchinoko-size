#!/bin/bash
# うちの子サイズ — コード更新をGitHubへ送る
cd "$(dirname "$0")" || exit 1

fail () { echo; echo "!! $1"; echo; read -p "Enterキーで閉じます " _; exit 1; }

REPO="munaggggg-ctrl/uchinoko-size"

# 前回の作業で残ったロックファイルと一時ファイルを掃除する
rm -f .git/index.lock
find .git/objects -name 'tmp_obj_*' -delete 2>/dev/null
rm -f data/*.db data/*.db-journal data/*.db-wal data/*.db-shm 2>/dev/null
rm -f .token 2>/dev/null        # 平文トークンはもう置かない。keychain に任せる

# 認証は macOS のキーチェーンに預ける。初回だけ Terminal が
#   Username / Password を聞いてくる。Password には GitHub のトークンを貼る。
# 2回目以降は何も聞かれない。
git config credential.helper osxkeychain
git remote get-url origin >/dev/null 2>&1 \
  || git remote add origin "https://github.com/${REPO}.git"
git remote set-url origin "https://github.com/${REPO}.git"

echo "== テスト =="
python3 tests/run.py || fail "テストに失敗したため送信を中止しました"

echo
echo "== 変更内容 =="
git add -A
git status --short
if git diff --staged --quiet; then
  echo "  変更はありません"
  read -p "Enterキーで閉じます " _; exit 0
fi

MSG=${1:-"update: $(date +%Y-%m-%d\ %H:%M)"}
git commit -q -m "$MSG"

echo
echo "== GitHubへ送信 =="
echo "（初回だけ Username と Password を聞かれます。"
echo "  Username: munaggggg-ctrl"
echo "  Password: GitHubのトークン（ghp_… / github_pat_… で始まる文字列）"
echo "  貼り付けても画面には何も表示されませんが、入力されています）"
echo
git push origin main || fail "送信に失敗しました。トークンが違うか、期限切れの可能性があります"

echo
echo "===================================="
echo " 送信しました。"
echo " https://github.com/${REPO}/actions"
echo " ↑ ここで自動チェックの結果が見られます"
echo "===================================="
echo
read -p "Enterキーで閉じます " _
