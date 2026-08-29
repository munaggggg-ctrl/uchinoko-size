-- 動作確認用のサンプル。実データではない（実データはブランド公式サイズ表から収集する）
INSERT INTO source (id, kind, url, title, fetched_at) VALUES
 (1,'brand_official','https://example-a.jp/size','A社 公式サイズ表','2026-08-29T10:00:00+09:00'),
 (2,'brand_official','https://example-b.jp/size','B社 公式サイズ表','2026-08-29T10:05:00+09:00'),
 (3,'brand_official','https://example-c.jp/size','C社 公式サイズ表','2026-08-29T10:10:00+09:00');

INSERT INTO brand (id, slug, name, official_url, size_policy) VALUES
 (1,'brand-a','A社','https://example-a.jp','実寸表記'),
 (2,'brand-b','B社','https://example-b.jp','ゆとり込み表記'),
 (3,'brand-c','C社','https://example-c.jp','実寸表記');

INSERT INTO size_chart (id, brand_id, category, source_id, stretch) VALUES
 (1,1,'wear',1,'low'),
 (2,2,'wear',2,'high'),
 (3,3,'wear',3,'none');

INSERT INTO size_variant
 (chart_id,label,sort_order,neck_min,neck_max,chest_min,chest_max,back_min,back_max,weight_min,weight_max,provenance,source_id) VALUES
 (1,'SS',1,18,21,24,28,18,21,1.0,2.0,'official',1),
 (1,'S' ,2,22,25,30,34,23,26,2.0,3.5,'official',1),
 (1,'M' ,3,26,29,35,40,27,31,3.5,5.5,'official',1),
 (2,'S' ,1,20,23,26,30,20,22,1.5,2.8,'official',2),
 (2,'M' ,2,24,27,31,35,23,26,2.8,4.5,'official',2),
 (2,'L' ,3,28,31,36,41,27,30,4.5,7.0,'official',2),
 (3,'S' ,1,24,28,33,38,26,29,3.0,5.0,'official',3),
 (3,'M' ,2,29,33,39,44,30,34,5.0,8.0,'official',3);
