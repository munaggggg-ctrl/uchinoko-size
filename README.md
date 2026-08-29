# 小型犬サイズDB — Phase 1 基盤

「うちの子の実測値を、各ブランドのサイズに翻訳する」ための最小構成。
2026-08-29 の設計レビューで承認された Phase 1 の実装。

## この構成が守っていること

| 引継書の要求 | どう守っているか |
|---|---|
| 第33項 公式値・AI推定値・ユーザー投稿値を分離 | `size_variant.provenance` を NOT NULL + CHECK。出所のない数値は物理的に保存できない |
| 第33項 AI推定値を公式スペックとして掲載しない | 推定値のみ `confidence` 必須、公式値には付けられない。ビュー `v_size_row` が provenance を必ず返す |
| 第19項 データ元と取得日時を必ず記録 | `source.url` + `source.fetched_at` が NOT NULL。推定のみ URL 省略可（式を `note` に書く） |
| 第23項 CEOのPCが電源OFFでも運営が続く | 実行層は GitHub Actions。Claude のセッションにも CEO の端末にも依存しない |
| 第30項 コスト暴走防止 | `DAILY_TOKEN_CAP` をコード側で強制、`timeout-minutes`、`concurrency` で二重起動を防止 |
| 第31項 AI大量記事サイトにしない | 校閲linter が出典と provenance のない記事の公開を止める |
| 第34項 APIキーを直書きしない | すべて GitHub Secrets 経由 |

## 実データで分かったこと（要注意）

ブランドによってサイズ表の数値の意味が違う。

- **CALULU S** 胴回り 31〜34cm → 「この範囲の犬に合う」（犬の適合レンジ）
- **IDOG&ICAT S** 胴周り 35cm → 「服そのものの寸法」（実寸）

同じ列に並べて比較すると判定が丸ごと壊れる。IDOGのS(35cm)を適合レンジと誤読すると、
胴回り35cmの犬にSを勧めてしまうが、実際には入らない。

`size_chart.measure_basis` でどちらの表かを持ち、`pipeline/normalize.py` が実寸表記を
犬基準へ変換する。変換結果は必ず `provenance='estimated'` + `confidence=0.6` になり、
公式値とは区別して掲載される。この挙動は `tests/test_normalize.py` で固定してある。

## 構成

```
db/schema.sql          サイズDB。SQLite。Gitで差分が追える
pipeline/sizing.py     適合判定エンジン（純粋関数。DBもHTTPも触らない）
pipeline/normalize.py  サイズ表の正規化。実寸表記を犬の適合レンジへ変換する
pipeline/query.py      DB読み出し。SQLに触るのはここだけ
pipeline/rakuten.py    楽天APIクライアント。購入リンクと価格のみ取得する
pipeline/lint.py       公開前の校閲。ERROR があれば公開を止める
tests/run.py           テストランナー（pytest不要）
.github/workflows/     日次パイプラインと週次レポート
```

## 動かす

```bash
python3 tests/run.py              # 80件のテスト
python3 -m pipeline.lint FILE     # 校閲。終了コード1で公開中止
```

デモDBを作って横断推薦を見る:

```bash
python3 - <<'PY'
import sqlite3, pathlib
con = sqlite3.connect("data/demo.db")
con.executescript(pathlib.Path("db/schema.sql").read_text())
con.executescript(pathlib.Path("data/seed_demo.sql").read_text())
con.commit()
PY
```

## 校閲linterが止めるもの

- `AD_DISCLOSURE` — アフィリエイトリンクがあるのに広告表記がない（景表法・ステマ規制）
- `AD_DISCLOSURE_POSITION` — 広告表記が最初のリンクより後ろにある
- `YAKUJI` — 効能・効果の標榜（薬機法）
- `VET_ADVICE` — 診断・投薬・受診要否への踏み込み
- `SUPERLATIVE` — 根拠なき最上級・断定表現（根拠併記があれば WARN に降格）
- `PROVENANCE_MISSING` — 数値に公式/推定/ユーザーの別がない
- `SOURCE_MISSING` — 数値に出典がない

やむを得ない場合のみ、直前の行に理由つきで抑制する:

```html
<!-- lint:allow=YAKUJI 獣医師監修コメントの引用のため -->
```

理由のない抑制は抑制として扱わない。

## まだ無いもの（Day 8 以降）

- `pipeline/collect.py` — ブランド公式サイズ表の取得と構造化（Gemini 無料枠）
- `pipeline/draft.py` — 記事下書き（Claude Haiku + Batch API）
- `pipeline/publish.py` — WordPress REST API への投稿
- `pipeline/weekly_report.py` — 日曜のCEOレポート

いずれも、アカウントとAPIキーが揃ってから実装する。
