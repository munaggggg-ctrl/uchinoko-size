-- ブランド公式サイズ表からの実データ（小型犬帯のみ）。2026-08-29 取得。
-- 数値はすべて各ブランド公式サイトの公開サイズ表による。
INSERT INTO source (id, kind, url, title, fetched_at) VALUES
 (1,'brand_official','https://www.calulu-dogwear.jp/user_data/dogwearsize','CALULU 犬服サイズ表','2026-08-29T17:00:00+09:00'),
 (2,'brand_official','https://www.idog.jp/blog/sizepage/','IDOG&ICAT お洋服のサイズについて','2026-08-29T17:00:00+09:00');

INSERT INTO brand (id, slug, name, official_url, size_policy) VALUES
 (1,'calulu','CALULU','https://www.calulu-dogwear.jp/','適合レンジ表記（犬の実測レンジを掲載）'),
 (2,'idog','IDOG&ICAT','https://www.idog.jp/','実寸表記（服そのものの寸法を掲載）');

INSERT INTO size_chart (id, brand_id, category, series, source_id, measure_basis, stretch) VALUES
 (1,1,'wear','ドッグウェア',1,'dog_fit_range','low'),
 (2,2,'wear','基本サイズ',  2,'garment_actual','low');

-- CALULU: 表の値は犬の適合レンジ。そのまま official
INSERT INTO size_variant
 (chart_id,label,sort_order,neck_min,neck_max,chest_min,chest_max,back_min,back_max,weight_min,weight_max,provenance,source_id) VALUES
 (1,'3XS',1,14,16,22,24,14,16,0.5,1.0,'official',1),
 (1,'2XS',2,16,18,25,27,15,17,1.0,1.8,'official',1),
 (1,'XS' ,3,18,20,28,30,18,20,1.8,2.3,'official',1),
 (1,'S'  ,4,21,23,31,34,21,23,2.2,2.8,'official',1),
 (1,'M'  ,5,24,27,35,38,24,26,2.8,3.8,'official',1),
 (1,'L'  ,6,27,30,39,42,27,29,3.6,5.3,'official',1),
 (1,'2L' ,7,31,34,43,46,30,32,5.0,7.0,'official',1);

-- IDOG&ICAT: 表の値は服の実寸（単一値）。読み出し時に犬基準へ変換され estimated になる
INSERT INTO size_variant
 (chart_id,label,sort_order,neck_min,neck_max,chest_min,chest_max,back_min,back_max,weight_min,weight_max,provenance,source_id) VALUES
 (2,'XXS',1,18,18,27,27,18,18,NULL,1.0,'official',2),
 (2,'XS' ,2,20,20,31,31,20,20,1.5,1.8,'official',2),
 (2,'S'  ,3,23,23,35,35,23,23,1.6,2.5,'official',2),
 (2,'M'  ,4,26,26,40,40,27,27,2.0,3.5,'official',2),
 (2,'L'  ,5,30,30,45,45,31,31,2.5,5.0,'official',2),
 (2,'XL' ,6,34,34,50,50,35,35,5.0,8.0,'official',2);
