#!/bin/bash
# うちの子サイズ — GitHubへの初回配置
cd "$(dirname "$0")" || exit 1

fail () { echo; echo "!! $1"; echo; read -p "Enterキーで閉じます " _; exit 1; }

REPO="munaggggg-ctrl/uchinoko-size"
[ -f .token ] || fail ".token が見つかりません"
TOKEN=$(tr -d '[:space:]' < .token)

echo "== 0/3 トークンの権限を確認 =="
PERM=$(curl -s -H "Authorization: Bearer ${TOKEN}" \
       -H "Accept: application/vnd.github+json" \
       "https://api.github.com/repos/${REPO}" \
  | python3 -c "
import json,sys
try:
    d = json.load(sys.stdin)
except Exception:
    print('NOJSON'); raise SystemExit
if 'permissions' in d:
    print('WRITE' if d['permissions'].get('push') else 'READONLY')
else:
    print('NOACCESS:' + str(d.get('message','')))
")
case "$PERM" in
  WRITE)    echo "  OK 書き込み権限があります" ;;
  READONLY) fail "トークンに書き込み権限がありません。GitHubでトークンの Contents を Read and write に変更してください" ;;
  NOACCESS*) fail "トークンがこのリポジトリにアクセスできません（${PERM}）。Only select repositories で uchinoko-size を選び直してください" ;;
  *)        echo "  判定できませんでした。このまま続行します" ;;
esac

echo "== 1/3 テスト =="
python3 tests/run.py || fail "テストに失敗しました"

echo
echo "== 2/3 GitHubへ送信 =="
rm -rf .git
git init -q || fail "git init に失敗しました"
# 古い git には 'git init -b' が無いため、この方法で main を既定ブランチにする
git symbolic-ref HEAD refs/heads/main || fail "ブランチ設定に失敗しました"
git config user.name  "koinu-bot"
git config user.email "bot@users.noreply.github.com"
git add -A || fail "git add に失敗しました"
git commit -q -m "Phase 1 基盤: サイズDB・適合判定・正規化・校閲linter・楽天クライアント" \
  || fail "commit に失敗しました"
git remote add origin "https://x-access-token:${TOKEN}@github.com/${REPO}.git"
git push -u origin main || fail "push に失敗しました（トークンの権限を確認します）"
git remote set-url origin "https://github.com/${REPO}.git"
echo "  送信しました"

echo
echo "== 3/3 Secrets の登録 =="
python3 .setup_secrets.py .token
SECRET_STATUS=$?

rm -f .token .setup_secrets.py .bundle.tar.gz

echo
echo "===================================="
if [ $SECRET_STATUS -eq 0 ]; then
  echo " 完了しました。作業はここまでです。"
else
  echo " コードの送信は完了しました。"
  echo " Secrets の登録だけ失敗したので、"
  echo " チャットでその旨をお知らせください。"
fi
echo " https://github.com/${REPO}"
echo "===================================="
echo
read -p "Enterキーで閉じます " _
