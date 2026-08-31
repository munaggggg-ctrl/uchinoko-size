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


# =====================================================================
# 採寸ガイド
# =====================================================================

from pipeline.article import BasisSurvey, measuring_guide_article  # noqa: E402

SURVEY = BasisSurvey(
    dog_fit_brands=["CALULU", "VERY-PET", "monchéri", "DOGBASE YOKOHAMA",
                    "犬と生活 L.W.D.", "ポンポリース"],
    garment_brands=["IDOG&ICAT", "キミノフク。"],
    unknown_brands=[],
)
GUIDE_SOURCES = [
    Source("CALULU", "https://www.calulu-dogwear.jp/user_data/dogwearsize", "2026-08-29"),
    Source("IDOG&ICAT", "https://www.idog.jp/blog/sizepage/", "2026-08-29"),
]
QUOTES = [
    ("CALULU", "当サイトに掲載のサイズ表は、ワンちゃんのボディサイズです。"),
    ("IDOG&ICAT", "サイズ表の数字は全てお洋服の仕上り寸法となっております。"),
]


def test_measuring_guide_passes_lint():
    a = measuring_guide_article(SURVEY, GUIDE_SOURCES, QUOTES)
    assert lint(a.body) == [], [f.rule for f in lint(a.body)]


def test_measuring_guide_refuses_without_survey_data():
    """採寸方法の説明だけなら、どのブランドのサイトにも書いてある。
    横断調査という独自部分がないなら、記事を作らせない。"""
    empty = BasisSurvey([], [], [])
    try:
        measuring_guide_article(empty, GUIDE_SOURCES)
    except ValueError as e:
        assert "横断調査" in str(e)
    else:
        raise AssertionError("独自データのない薄い記事を作ってはいけない")


def test_survey_numbers_appear_in_the_text():
    body = measuring_guide_article(SURVEY, GUIDE_SOURCES).body
    assert "8社" in body, "調べた社数を明記する"
    assert "6社" in body and "2社" in body


def test_official_quotes_are_shown_verbatim():
    body = measuring_guide_article(SURVEY, GUIDE_SOURCES, QUOTES).body
    assert "ワンちゃんのボディサイズです" in body
    assert "お洋服の仕上り寸法" in body


def test_all_three_measurements_are_explained():
    body = measuring_guide_article(SURVEY, GUIDE_SOURCES).body
    for k in ("首回り", "胴回り", "着丈", "前足の付け根", "しっぽの付け根"):
        assert k in body


def test_ease_figures_are_attributed():
    """あき量は当サイトの当て推量ではなく、出典のある数字であることを本文で示す。"""
    body = measuring_guide_article(SURVEY, GUIDE_SOURCES).body
    assert "milla milla" in body
    assert "2〜3cm" in body and "4〜5cm" in body


def test_unknown_brands_row_is_omitted_when_empty():
    body = measuring_guide_article(SURVEY, GUIDE_SOURCES).body
    assert "公式に明記なし" not in body


def test_unknown_brands_row_is_shown_when_present():
    """基準が不明なブランドがあることも隠さない。"""
    s = BasisSurvey(["A"], ["B"], ["CRAZYBOO"])
    body = measuring_guide_article(s, GUIDE_SOURCES).body
    assert "公式に明記なし" in body and "CRAZYBOO" in body


def test_guide_slug_and_title():
    a = measuring_guide_article(SURVEY, GUIDE_SOURCES)
    assert a.slug == "how-to-measure-dog"
    assert "測り方" in a.title


def test_brand_names_in_survey_are_escaped():
    s = BasisSurvey(["<b>X</b>"], ["Y"], [])
    body = measuring_guide_article(s, GUIDE_SOURCES).body
    assert "<b>X</b>" not in body and "&lt;b&gt;" in body
