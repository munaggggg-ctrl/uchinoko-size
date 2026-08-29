-- =====================================================================
--  小型犬サイズDB / schema
--  設計原則
--    1. すべての数値は出典(source_id)と種別(provenance)なしに保存できない
--    2. provenance は official / estimated / user の3値のみ
--    3. 表示側は provenance を必ず添えて出す（公式値とAI推定値を混同しない）
--    4. CMSに依存しない。SQLiteファイル単体で完結し、Gitで差分が追える
-- =====================================================================

PRAGMA foreign_keys = ON;

-- ---------------------------------------------------------------------
-- 出典。数値を持つ行はすべてここを参照する
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS source (
  id           INTEGER PRIMARY KEY,
  kind         TEXT NOT NULL CHECK (kind IN (
                 'brand_official',   -- ブランド公式サイトのサイズ表
                 'maker_catalog',    -- メーカー配布資料
                 'estimation',       -- 自社の推定ロジック（式・前提を note に書く）
                 'user_report'       -- ユーザー投稿
               )),
  url          TEXT,                 -- estimation の場合のみ NULL 可
  title        TEXT NOT NULL,
  fetched_at   TEXT NOT NULL,        -- ISO8601。取得日時（第19項の要求）
  note         TEXT,                 -- 推定の場合は式と前提を必ず書く
  CHECK (kind = 'estimation' OR url IS NOT NULL)
);

-- ---------------------------------------------------------------------
-- ブランド
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS brand (
  id            INTEGER PRIMARY KEY,
  slug          TEXT NOT NULL UNIQUE,
  name          TEXT NOT NULL,
  official_url  TEXT,
  size_policy   TEXT,               -- 「実寸表記」「ゆとり込み表記」などの注記
  created_at    TEXT NOT NULL DEFAULT (datetime('now'))
);

-- ---------------------------------------------------------------------
-- サイズ表（ブランド × カテゴリ × 表の版）
--   同じブランドでも「犬服」と「ハーネス」で別の表を持つ
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS size_chart (
  id          INTEGER PRIMARY KEY,
  brand_id    INTEGER NOT NULL REFERENCES brand(id) ON DELETE CASCADE,
  category    TEXT NOT NULL CHECK (category IN ('wear','harness','carrier')),
  series      TEXT,                 -- 「タンクトップ」など表が分かれる場合の識別
  source_id   INTEGER NOT NULL REFERENCES source(id),

  -- 表の数値が「犬の適合レンジ」なのか「服の実寸」なのか。
  -- ブランドによって意味が違うため、これを取り違えると比較が丸ごと壊れる。
  measure_basis TEXT NOT NULL DEFAULT 'dog_fit_range'
                CHECK (measure_basis IN ('dog_fit_range','garment_actual')),
  stretch     TEXT CHECK (stretch IN ('none','low','high')),  -- 伸縮性
  updated_at  TEXT NOT NULL DEFAULT (datetime('now')),
  UNIQUE (brand_id, category, series)
);

-- ---------------------------------------------------------------------
-- サイズ1行（S / M / 3号 など）
--   数値は「その表が示す適合レンジ」。単位はすべて cm / kg
--   NULL は「その項目の記載がない」を意味する。0 で埋めない
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS size_variant (
  id             INTEGER PRIMARY KEY,
  chart_id       INTEGER NOT NULL REFERENCES size_chart(id) ON DELETE CASCADE,
  label          TEXT NOT NULL,      -- 'S' '3号' 'SS' など、ブランド表記のまま
  sort_order     INTEGER NOT NULL,   -- 小さい順に並べるための整数

  neck_min       REAL, neck_max       REAL,   -- 首回り
  chest_min      REAL, chest_max      REAL,   -- 胴回り
  back_min       REAL, back_max       REAL,   -- 着丈
  weight_min     REAL, weight_max     REAL,   -- 対応体重

  provenance     TEXT NOT NULL CHECK (provenance IN ('official','estimated','user')),
  source_id      INTEGER NOT NULL REFERENCES source(id),
  confidence     REAL CHECK (confidence BETWEEN 0 AND 1),  -- estimated のときのみ

  UNIQUE (chart_id, label),
  -- 範囲の向きが逆転しているデータを弾く
  CHECK (neck_min   IS NULL OR neck_max   IS NULL OR neck_min   <= neck_max),
  CHECK (chest_min  IS NULL OR chest_max  IS NULL OR chest_min  <= chest_max),
  CHECK (back_min   IS NULL OR back_max   IS NULL OR back_min   <= back_max),
  CHECK (weight_min IS NULL OR weight_max IS NULL OR weight_min <= weight_max),
  -- 推定値は confidence 必須。公式値に confidence は付けない
  CHECK ((provenance = 'estimated') = (confidence IS NOT NULL))
);

CREATE INDEX IF NOT EXISTS idx_variant_chart ON size_variant(chart_id, sort_order);

-- ---------------------------------------------------------------------
-- カテゴリ固有の属性（外寸・耐荷重・電車利用可否・調整幅 など）
--   カテゴリごとに列が違うため、ここだけEAVで持つ
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS size_attribute (
  id           INTEGER PRIMARY KEY,
  variant_id   INTEGER NOT NULL REFERENCES size_variant(id) ON DELETE CASCADE,
  key          TEXT NOT NULL,        -- 'outer_w' 'load_capacity' 'train_ok' ...
  value_num    REAL,
  value_text   TEXT,
  unit         TEXT,
  provenance   TEXT NOT NULL CHECK (provenance IN ('official','estimated','user')),
  source_id    INTEGER NOT NULL REFERENCES source(id),
  UNIQUE (variant_id, key),
  CHECK (value_num IS NOT NULL OR value_text IS NOT NULL)
);

-- ---------------------------------------------------------------------
-- 商品。サイズ表に紐づく。購入リンクは別テーブル
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS product (
  id          INTEGER PRIMARY KEY,
  chart_id    INTEGER NOT NULL REFERENCES size_chart(id),
  name        TEXT NOT NULL,
  slug        TEXT NOT NULL UNIQUE,
  image_url   TEXT,
  created_at  TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS offer (
  id          INTEGER PRIMARY KEY,
  product_id  INTEGER NOT NULL REFERENCES product(id) ON DELETE CASCADE,
  merchant    TEXT NOT NULL CHECK (merchant IN ('rakuten','amazon','yahoo','official')),
  url         TEXT NOT NULL,        -- アフィリエイトリンク生成後のURL
  price       INTEGER,
  checked_at  TEXT NOT NULL,
  UNIQUE (product_id, merchant)
);

-- ---------------------------------------------------------------------
-- 犬種の参考採寸値。「体重しか知らない」ユーザーの入口になる
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS breed (
  id          INTEGER PRIMARY KEY,
  slug        TEXT NOT NULL UNIQUE,
  name_ja     TEXT NOT NULL,
  body_type   TEXT CHECK (body_type IN ('long','standard','short')),  -- 胴長/標準/短め
  weight_min  REAL, weight_max REAL,
  provenance  TEXT NOT NULL CHECK (provenance IN ('official','estimated','user')),
  source_id   INTEGER NOT NULL REFERENCES source(id)
);

-- ---------------------------------------------------------------------
-- Phase 2 用。ユーザーの実測フィットデータ
--   いまは書き込まないが、スキーマは先に切っておく
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS fit_report (
  id           INTEGER PRIMARY KEY,
  variant_id   INTEGER NOT NULL REFERENCES size_variant(id),
  breed_id     INTEGER REFERENCES breed(id),
  weight       REAL,
  neck         REAL,
  chest        REAL,
  back         REAL,
  verdict      TEXT NOT NULL CHECK (verdict IN ('too_small','snug','just','loose','too_large')),
  comment      TEXT,
  submitted_at TEXT NOT NULL DEFAULT (datetime('now')),
  approved     INTEGER NOT NULL DEFAULT 0   -- 目視/ルール承認を経てから表示する
);

-- ---------------------------------------------------------------------
-- 表示用ビュー。provenance を落として使えないようにしてある
-- ---------------------------------------------------------------------
CREATE VIEW IF NOT EXISTS v_size_row AS
SELECT
  b.slug        AS brand_slug,
  b.name        AS brand_name,
  c.category    AS category,
  c.series        AS series,
  c.stretch       AS stretch,
  c.measure_basis AS measure_basis,
  v.id          AS variant_id,
  v.label       AS size_label,
  v.sort_order  AS sort_order,
  v.neck_min, v.neck_max,
  v.chest_min, v.chest_max,
  v.back_min, v.back_max,
  v.weight_min, v.weight_max,
  v.provenance  AS provenance,
  v.confidence  AS confidence,
  s.url         AS source_url,
  s.fetched_at  AS source_fetched_at
FROM size_variant v
JOIN size_chart c ON c.id = v.chart_id
JOIN brand      b ON b.id = c.brand_id
JOIN source     s ON s.id = v.source_id;
