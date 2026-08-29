-- ブランド公式サイズ表からの実データ（小型犬帯のみ）。
-- 数値はすべて各ブランド公式サイトの公開サイズ表による。取得日 2026-08-29。
-- measure_basis は各社の明記を確認して設定している（note に原文を引用）。

INSERT INTO source (id, kind, url, title, fetched_at, note) VALUES
 (1,'brand_official','https://www.calulu-dogwear.jp/user_data/dogwearsize',
    'CALULU 犬服のサイズについて','2026-08-29T17:00:00+09:00',
    '原文: 「当サイトに掲載のサイズ表は、ワンちゃんのボディサイズです。(服のサイズではありません。)」→ dog_fit_range'),
 (2,'brand_official','https://www.idog.jp/blog/sizepage/',
    'IDOG&ICAT お洋服のサイズについて','2026-08-29T17:00:00+09:00',
    '原文: 「サイズ表の数字は全てお洋服の仕上り寸法となっております。」→ garment_actual'),
 (3,'brand_official','https://very-pet.com/pages/size',
    'VERY-PET 犬服のサイズ表','2026-08-29T21:30:00+09:00',
    '原文: 「サイズ表はワンちゃんのボディサイズの目安です。洋服のサイズではありません。」→ dog_fit_range');

INSERT INTO brand (id, slug, name, official_url, size_policy) VALUES
 (1,'calulu','CALULU','https://www.calulu-dogwear.jp/','犬のボディサイズ表記（公式に明記）'),
 (2,'idog','IDOG&ICAT','https://www.idog.jp/','服の仕上り寸法表記（公式に明記）'),
 (3,'very-pet','VERY-PET','https://very-pet.com/','犬のボディサイズ表記（公式に明記）。号数表記');

INSERT INTO size_chart (id, brand_id, category, series, source_id, measure_basis, stretch) VALUES
 (1,1,'wear','ドッグウェア',1,'dog_fit_range','low'),
 (2,2,'wear','基本サイズ',  2,'garment_actual','low'),
 (3,3,'wear','New号数',     3,'dog_fit_range','low');

-- CALULU（犬のボディサイズ）
INSERT INTO size_variant
 (chart_id,label,sort_order,neck_min,neck_max,chest_min,chest_max,back_min,back_max,weight_min,weight_max,provenance,source_id) VALUES
 (1,'3XS',1,14,16,22,24,14,16,0.5,1.0,'official',1),
 (1,'2XS',2,16,18,25,27,15,17,1.0,1.8,'official',1),
 (1,'XS' ,3,18,20,28,30,18,20,1.8,2.3,'official',1),
 (1,'S'  ,4,21,23,31,34,21,23,2.2,2.8,'official',1),
 (1,'M'  ,5,24,27,35,38,24,26,2.8,3.8,'official',1),
 (1,'L'  ,6,27,30,39,42,27,29,3.6,5.3,'official',1),
 (1,'2L' ,7,31,34,43,46,30,32,5.0,7.0,'official',1),
 (1,'3L' ,8,33,36,47,52,34,36,7.0,9.0,'official',1);

-- IDOG&ICAT（服の仕上り寸法。読み出し時に犬基準へ変換され estimated になる）
INSERT INTO size_variant
 (chart_id,label,sort_order,neck_min,neck_max,chest_min,chest_max,back_min,back_max,weight_min,weight_max,provenance,source_id) VALUES
 (2,'XXS',1,18,18,27,27,18,18,NULL,1.0,'official',2),
 (2,'XS' ,2,20,20,31,31,20,20,1.5,1.8,'official',2),
 (2,'S'  ,3,23,23,35,35,23,23,1.6,2.5,'official',2),
 (2,'M'  ,4,26,26,40,40,27,27,2.0,3.5,'official',2),
 (2,'L'  ,5,30,30,45,45,31,31,2.5,5.0,'official',2),
 (2,'XL' ,6,34,34,50,50,35,35,5.0,8.0,'official',2),
 -- ダックス専用サイズ。胴長犬の着丈不足を解決する行として重要
 (2,'DS' ,7,24,24,38,38,31,31,3.0,4.0,'official',2),
 (2,'DM' ,8,28,28,42,42,34,34,5.0,5.5,'official',2),
 (2,'DL' ,9,32,32,46,46,37,37,6.0,7.0,'official',2);

-- VERY-PET（犬のボディサイズ。号数表記）
INSERT INTO size_variant
 (chart_id,label,sort_order,neck_min,neck_max,chest_min,chest_max,back_min,back_max,weight_min,weight_max,provenance,source_id) VALUES
 (3,'New 1',1,18.0,24.5,28.5,33.5,19.5,23.5,1.5,2.5,'official',3),
 (3,'New 2',2,20.0,27.0,33.0,38.0,22.5,26.5,2.0,3.5,'official',3),
 (3,'New 3',3,22.0,29.0,37.0,42.0,25.5,29.5,3.0,5.5,'official',3),
 (3,'New 4',4,24.0,31.0,41.5,46.5,28.5,32.5,4.0,7.0,'official',3),
 (3,'New 5',5,26.0,33.0,46.0,51.0,31.5,35.5,5.0,8.0,'official',3),
 (3,'New 6',6,28.0,35.0,49.5,55.5,34.5,38.5,6.5,9.0,'official',3),
 (3,'New 7',7,30.0,37.0,54.0,60.0,37.5,41.5,7.5,11.0,'official',3);
