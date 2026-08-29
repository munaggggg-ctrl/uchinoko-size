# Secrets 一覧

**このファイルに値を書かないこと。** 名前と用途だけを管理する。
実際の値は GitHub リポジトリの Settings → Secrets and variables → Actions に入れる。

## 必須（Phase 1）

| 名前 | 用途 | 秘匿レベル |
|---|---|---|
| `RAKUTEN_APP_ID` | 楽天APIのアプリ識別子 | 準公開（クライアント側にも出る） |
| `RAKUTEN_ACCESS_KEY` | 楽天APIの認証キー | **秘密**。漏れたらアプリ管理ページで再発行 |
| `RAKUTEN_AFFILIATE_ID` | 成果計上用。リンクに含まれる | 公開情報 |
| `WP_URL` | `https://uchinoko-size.com` | 公開情報 |
| `WP_USER` | WordPress の管理ユーザー名 | 準公開 |
| `WP_APP_PASS` | WordPress のアプリケーションパスワード | **秘密**。管理画面からいつでも失効できる |
| `GEMINI_API_KEY` | サイズ表の読み取り（画像入力を含む）。無料枠 | **秘密**。Google AI Studio で再発行可 |

## Phase 1 後半で追加

| 名前 | 用途 |
|---|---|
| `ANTHROPIC_API_KEY` | 記事下書き・週次レポート |
| `GA4_PROPERTY_ID` / `GSC_CREDENTIALS` | 週次レポートの数値取得 |

## 運用ルール

- 値をコード・README・Issue・チャットに書かない。
- WordPress は管理者パスワードではなく **アプリケーションパスワード** を使う。
  権限を絞れて、漏れても管理画面から1クリックで失効できる。
- DB接続情報（DB名・DBユーザー・DBパスワード）は **使わない**。
  自動化は WordPress REST API 経由でのみ行う。
- 鍵を再発行したら、GitHub Secrets の値も同時に差し替える。
