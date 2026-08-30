import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from pipeline.article import Offer, Source, weight_article  # noqa: E402
from pipeline.lint import ERROR, lint  # noqa: E402
from pipeline.sizing import Dog, Variant, evaluate  # noqa: E402


def fit(brand, label, ranges, prov="official", basis_stretch="low"):
    v = Variant(1, brand, label, 1, "wear", basis_stretch, prov, ranges)
    return evaluate(Dog(chest=32, weight=2.8, neck=23, back=24), v)


FITS = [
    (fit("CALULU", "S", {"neck": (21, 23), "chest": (31, 34),
                         "back": (21, 23), "weight": (2.2, 2.8)}),
     Source("CALULU", "https://www.calulu-dogwear.jp/user_data/dogwearsize", "2026-08-29")),
    (fit("IDOG&ICAT", "S", {"neck": (20.5, 21), "chest": (31, 32),
                            "back": (21.5, 24.5), "weight": (1.6, 2.5)}, prov="estimated"),
     Source("IDOG&ICAT", "https://www.idog.jp/blog/sizepage/", "2026-08-29")),
]

OFFERS = [Offer("小型犬用タンクトップ", 1980,
                "https://hb.afl.rakuten.co.jp/hgc/xxx/")]


# --- 校閲を通ること。これが最重要 ---------------------------------

def test_article_without_offers_passes_lint():
    a = weight_article(2.8, FITS)
    assert lint(a.body) == [], [f.rule for f in lint(a.body)]


def test_article_with_offers_passes_lint():
    a = weight_article(2.8, FITS, OFFERS)
    assert lint(a.body) == [], [f.rule for f in lint(a.body)]


def test_offers_trigger_the_ad_disclosure():
    body = weight_article(2.8, FITS, OFFERS).body
    assert "本記事は広告を含みます。" in body
    assert body.index("広告を含みます") < body.index("hb.afl.rakuten.co.jp"), \
        "広告表記はアフィリエイトリンクより前に置く"


def test_no_disclosure_when_there_are_no_offers():
    assert "広告を含みます" not in weight_article(2.8, FITS).body


def test_removing_the_disclosure_would_be_caught():
    """校閲が実際に効いていることの確認。ここが素通りすると法令リスクが残る。"""
    broken = weight_article(2.8, FITS, OFFERS).body.replace("本記事は広告を含みます。", "")
    assert "AD_DISCLOSURE" in {f.rule for f in lint(broken) if f.severity == ERROR}


# --- 数値の出所 ---------------------------------------------------

def test_every_spec_cell_carries_its_provenance():
    body = weight_article(2.8, FITS).body
    assert body.count('data-prov="official"') >= 4
    assert body.count('data-prov="estimated"') >= 4


def test_estimated_rows_are_called_out_in_prose():
    body = weight_article(2.8, FITS).body
    assert "当サイトの推定値" in body and "公式値ではありません" in body


def test_sources_include_url_and_fetch_date():
    body = weight_article(2.8, FITS).body
    assert "https://www.calulu-dogwear.jp/user_data/dogwearsize" in body
    assert "2026-08-29 取得" in body


def test_sources_are_deduplicated():
    dup = FITS + [FITS[0]]
    assert len(weight_article(2.8, dup).sources) == 2


# --- 記事の中身 ---------------------------------------------------

def test_title_and_slug():
    a = weight_article(2.8, FITS)
    assert a.title == "体重2.8kgの小型犬に合う犬服のサイズ｜2ブランド横断比較"
    assert a.slug == "dog-wear-size-2-8kg"


def test_whole_number_weight_has_no_decimal_point():
    a = weight_article(3.0, FITS)
    assert "体重3kg" in a.title and a.slug == "dog-wear-size-3kg"


def test_comparison_table_lists_every_brand():
    body = weight_article(2.8, FITS).body
    for brand in ("CALULU", "IDOG&amp;ICAT"):
        assert brand in body


def test_measuring_guide_is_included():
    """胴回りを知らない飼い主が大半。ここが全導線の入口になる。"""
    body = weight_article(2.8, FITS).body
    for k in ("首回り", "胴回り", "着丈", "前足の付け根"):
        assert k in body


def test_brand_names_are_escaped():
    f, s = FITS[0]
    f.variant.__dict__  # dataclass は frozen なので新しく作る
    from pipeline.sizing import Variant
    v = Variant(9, '<script>x</script>', "S", 1, "wear", "low", "official",
                {"chest": (31, 34)})
    from pipeline.sizing import Dog, evaluate
    body = weight_article(2.8, [(evaluate(Dog(chest=32), v), s)]).body
    assert "<script>x</script>" not in body
    assert "&lt;script&gt;" in body


def test_offer_price_is_formatted_with_commas():
    body = weight_article(2.8, FITS, [Offer("高いやつ", 12800, "https://hb.afl.rakuten.co.jp/a")]).body
    assert "12,800円" in body


def test_limiting_reasons_are_explained():
    body = weight_article(2.8, FITS).body
    assert "判定が下がった理由" in body or "サイズが分かれる理由" in body


def test_weight_only_article_says_so():
    """体重だけの比較であることを、記事の側でも隠さない。"""
    from pipeline.sizing import Variant, evaluate, Dog
    v = Variant(1, "A社", "M", 1, "wear", "low", "official",
                {"weight": (2.8, 3.8)})
    f = evaluate(Dog(weight=3.0), v)
    body = weight_article(3.0, [(f, Source("A社", "https://a.example/size", "2026-08-29"))]).body
    assert "体重だけを手がかりにした比較" in body
    assert lint(body) == []


def test_fully_measured_article_has_no_such_caveat():
    body = weight_article(2.8, FITS).body
    assert "体重だけを手がかりにした比較" not in body
