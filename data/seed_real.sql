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

-- ============================================================
-- 追加分（2026-08-30）
-- 4,5 = ChatGPT が収集し、Claude が公式ページで原文・数値を再確認したもの
-- 6,7,8 = サブエージェントが公式ページから収集したもの（原文引用あり）
-- CRAZYBOO は表の基準が公式に明記されていないため取り込まない（推測で保存しない）
-- ============================================================

INSERT INTO source (id, kind, url, title, fetched_at, note) VALUES
 (4,'brand_official','https://moncheri.jp/pages/size',
    'monchéri サイズ表','2026-08-30T13:30:00+09:00',
    '原文: 「※ヌード寸法は各お洋服の仕上がり目安としている寸法です。」→ dog_fit_range。列見出しが「ヌード寸法」（＝犬の実測）であることを根拠とする。文言はやや曖昧なため要再確認。直接確認済み'),
 (5,'brand_official','https://shop.dogbase-yokohama.com/pages/size',
    'DOGBASE YOKOHAMA サイズ表','2026-08-30T13:30:00+09:00',
    '原文: 「※下記サイズ表はお洋服の寸法ではなく、わんちゃんのボディの寸法になります。」→ dog_fit_range。直接確認済み'),
 (6,'brand_official','https://with-dog.co.jp/hpgen/HPB/entries/1.html',
    '犬と生活 L.W.D. サイズの測り方','2026-08-30T00:30:00+09:00',
    '原文: 「対応するワンちゃん、猫ちゃんの計測サイズです。」→ dog_fit_range。背丈は「◯◯前後」の単一値'),
 (7,'brand_official','https://www.kiminofuku-dogwear.com/page/2',
    'キミノフク。サイズについて','2026-08-30T00:30:00+09:00',
    '原文: 「サイズの数字は、お洋服の仕上がりのサイズです。」→ garment_actual。対応体重の記載なし'),
 (8,'brand_official','https://www.pompreece.jp/page/5',
    'ポンポリース サイズ表','2026-08-30T00:30:00+09:00',
    '原文: 「寸法はワンちゃん・ねこちゃんのヌード（ボディ）寸法での記載です。」→ dog_fit_range。背丈は単一値');

INSERT INTO brand (id, slug, name, official_url, size_policy) VALUES
 (4,'moncheri','monchéri','https://moncheri.jp/','ヌード寸法表記'),
 (5,'dogbase','DOGBASE YOKOHAMA','https://shop.dogbase-yokohama.com/','ボディ寸法表記（公式に明記）'),
 (6,'with-dog','犬と生活 L.W.D.','https://with-dog.co.jp/','計測サイズ表記。背丈は単一値'),
 (7,'kiminofuku','キミノフク。','https://www.kiminofuku-dogwear.com/','仕上がり寸法表記（公式に明記）'),
 (8,'pompreece','ポンポリース','https://www.pompreece.jp/','ヌード（ボディ）寸法表記');

INSERT INTO size_chart (id, brand_id, category, series, source_id, measure_basis, stretch) VALUES
 (4,4,'wear','基本サイズ',4,'dog_fit_range','low'),
 (5,5,'wear','基本サイズ',5,'dog_fit_range','low'),
 (6,6,'wear','号数',      6,'dog_fit_range','low'),
 (7,7,'wear','基本サイズ',7,'garment_actual','low'),
 (8,8,'wear','号数',      8,'dog_fit_range','low');

-- monchéri（ヌード寸法）
INSERT INTO size_variant
 (chart_id,label,sort_order,neck_min,neck_max,chest_min,chest_max,back_min,back_max,weight_min,weight_max,provenance,source_id) VALUES
 (4,'XS',1,14,20,24,34,16,20,NULL,1.5,'official',4),
 (4,'S' ,2,18,24,30,40,20,24,NULL,2.0,'official',4),
 (4,'M' ,3,22,28,34,44,24,28,NULL,4.0,'official',4),
 (4,'DM',4,22,28,32,42,31,35,NULL,5.0,'official',4),
 (4,'L' ,5,26,32,38,48,28,32,NULL,6.0,'official',4),
 (4,'XL',6,30,36,42,52,32,36,NULL,8.0,'official',4);

-- DOGBASE YOKOHAMA（ボディ寸法。括弧内のレンジを採用）
INSERT INTO size_variant
 (chart_id,label,sort_order,neck_min,neck_max,chest_min,chest_max,back_min,back_max,weight_min,weight_max,provenance,source_id) VALUES
 (5,'XXXS ショート',1,15,19,23,27,18,18,NULL,1.8,'official',5),
 (5,'XXXS ロング'  ,2,15,19,23,27,21,21,NULL,1.8,'official',5),
 (5,'XXS',3,18,22,28,32,24,24,NULL,2.5,'official',5),
 (5,'XS' ,4,21,25,33,37,26,26,NULL,3.5,'official',5),
 (5,'S'  ,5,24,28,38,42,28,28,NULL,5.0,'official',5),
 (5,'M'  ,6,27,31,43,47,30,30,NULL,7.0,'official',5),
 (5,'L'  ,7,32,36,48,53,33,33,NULL,8.0,'official',5),
 (5,'XL' ,8,36,40,53,58,35,35,NULL,10.0,'official',5);

-- 犬と生活 L.W.D.（計測サイズ。背丈は「◯◯前後」の単一値）
INSERT INTO size_variant
 (chart_id,label,sort_order,neck_min,neck_max,chest_min,chest_max,back_min,back_max,weight_min,weight_max,provenance,source_id) VALUES
 (6,'XS'   ,1,NULL,17,NULL,27,19,19,NULL,NULL,'official',6),
 (6,'1号'  ,2,17,19,27,32,23,23,NULL,NULL,'official',6),
 (6,'2号'  ,3,19,23,32,36,25,25,NULL,NULL,'official',6),
 (6,'2Long',4,19,23,32,36,29,29,NULL,NULL,'official',6),
 (6,'3号'  ,5,23,25,36,39,29,29,NULL,NULL,'official',6),
 (6,'3LONG',6,23,25,36,39,34,34,NULL,NULL,'official',6),
 (6,'MDS'  ,7,23,25,36,39,34,34,3.0,4.5,'official',6),
 (6,'4号'  ,8,25,27,39,44,34,34,NULL,NULL,'official',6),
 (6,'4LONG',9,25,27,39,44,37,37,NULL,NULL,'official',6),
 (6,'MDM'  ,10,25,27,39,44,37,37,4.5,6.0,'official',6),
 (6,'5号'  ,11,27,31,44,49,37,37,NULL,NULL,'official',6),
 (6,'6号'  ,12,31,34,49,53,40,40,NULL,NULL,'official',6);

-- キミノフク。（服の仕上がり寸法 → 読み出し時に犬基準へ換算され estimated になる）
INSERT INTO size_variant
 (chart_id,label,sort_order,neck_min,neck_max,chest_min,chest_max,back_min,back_max,weight_min,weight_max,provenance,source_id) VALUES
 (7,'3S',1,17,17,26,26,18,18,NULL,NULL,'official',7),
 (7,'SS',2,20,20,30,30,20,20,NULL,NULL,'official',7),
 (7,'S' ,3,23,23,34,34,22,22,NULL,NULL,'official',7),
 (7,'M' ,4,26,26,38,38,24,24,NULL,NULL,'official',7),
 (7,'L' ,5,29,29,42,42,26,26,NULL,NULL,'official',7),
 (7,'LL',6,32,32,46,46,28,28,NULL,NULL,'official',7);

-- ポンポリース（ヌード寸法。背丈は単一値。ロングは別シリーズ扱いせず接尾辞で区別）
INSERT INTO size_variant
 (chart_id,label,sort_order,neck_min,neck_max,chest_min,chest_max,back_min,back_max,weight_min,weight_max,provenance,source_id) VALUES
 (8,'3S'      ,1,14,18,21,26,18,18,NULL,NULL,'official',8),
 (8,'1号(SS)' ,2,18,20,26,29,20,20,NULL,NULL,'official',8),
 (8,'2号(S)'  ,3,20,23,29,35,23,23,NULL,NULL,'official',8),
 (8,'2号ロング',4,19,24,31,38,28,28,NULL,NULL,'official',8),
 (8,'3号(M)'  ,5,23,26,35,41,27,27,NULL,NULL,'official',8),
 (8,'3号ロング',6,23,28,37,43,32,32,NULL,NULL,'official',8),
 (8,'4号(L)'  ,7,26,30,41,47,31,31,NULL,NULL,'official',8),
 (8,'4号ロング',8,27,31,42,48,36,36,NULL,NULL,'official',8),
 (8,'5号(LL)' ,9,30,33,47,53,35,35,NULL,NULL,'official',8),
 (8,'5号ロング',10,30,35,47,54,40,40,NULL,NULL,'official',8);
