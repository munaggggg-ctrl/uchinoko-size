import re
import sqlite3
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from pipeline.article import TOOL_URL, BasisSurvey  # noqa: E402
from pipeline.build_db import build  # noqa: E402
from pipeline.draft import (  # noqa: E402
    DEFAULT_WEIGHTS, DraftError, basis_survey, build_all, guide_article, weight_articles,
)
from pipeline.article import e  # noqa: E402
from pipeline.lint import ERROR, lint  # noqa: E402
from pipeline.query import connect  # noqa: E402

_DB = None


def _db() -> Path:
    global _DB
    if _DB is None:
        _DB = Path(tempfile.mkdtemp()) / "d.db"
        build(_DB)
    return _DB


def test_articles_are_built_from_the_real_data():
    arts = build_all(_db())
    assert len(arts) == len(DEFAULT_WEIGHTS) + 1, [a.slug for a in arts]
    slugs = [a.slug for a in arts]
    assert len(set(slugs)) == len(slugs), slugs
    assert "how-to-measure-dog" in slugs


def test_every_article_passes_lint():
    """校閲を通らない記事を後段へ渡さない。"""
    for a in build_all(_db()):
        errors = [f for f in lint(a.body) if f.severity == ERROR]
        assert not errors, (a.slug, [f.rule for f in errors])


def test_every_article_carries_provenance_and_sources():
    for a in build_all(_db()):
        assert "出典" in a.body, a.slug
        if a.slug != "how-to-measure-dog":
            assert 'data-prov=' in a.body, a.slug
            assert a.sources, a.slug


def test_weight_articles_link_to_the_tool():
    """記事は入口、道具は出口。この導線を切らない。"""
    for a in build_all(_db()):
        if a.slug.startswith("dog-wear-size-"):
            assert TOOL_URL in a.body, a.slug


def test_brands_without_a_weight_range_are_named_not_silently_dropped():
    """体重を公開していないブランドを黙って消すと、ブランド数が食い違って見える。"""
    con = connect(_db())
    try:
        arts = weight_articles(con, (3.0,))
        all_brands = {r["name"] for r in con.execute(
            "SELECT DISTINCT b.name AS name FROM brand b "
            "JOIN size_chart c ON c.brand_id = b.id WHERE c.category = 'wear'")}
    finally:
        con.close()
    assert len(arts) == 1
    body = arts[0].body
    shown = int(re.search(r"｜(\d+)ブランド横断比較", arts[0].title).group(1))
    assert shown < len(all_brands), "テストの前提が崩れている（全ブランドが体重を公開している）"
    assert "対応体重を公開していないため" in body
    for brand in all_brands:
        assert e(brand) in body, f"{brand} が本文のどこにも出てこない"


def test_thin_comparison_is_not_published():
    """3ブランドに満たない比較は「横断比較」と呼べない。作らない。

    判定エンジンは必ず「最も惜しいサイズ」を返すので、行が埋まっていること自体は
    記事を出してよい理由にならない。×だけが並ぶ記事を publish しないための門。
    """
    con = connect(_db())
    try:
        assert weight_articles(con, (12.0,)) == [], "適合1ブランドで記事を作ってはいけない"
        assert weight_articles(con, (20.0,)) == [], "適合0ブランドで記事を作ってはいけない"
        assert weight_articles(con, (3.0,)), "適合が十分ある体重では作られること"
    finally:
        con.close()


def test_survey_counts_only_what_is_in_the_db():
    con = connect(_db())
    try:
        survey, sources, quotes = basis_survey(con)
    finally:
        con.close()
    assert survey.total == len(sources)
    assert survey.dog_fit_brands and survey.garment_brands
    assert not survey.unknown_brands, "基準が不明なブランドはDBに入れない方針"
    # 原文引用は全ブランド分そろっていること（引用が取れない値は保存しない方針）
    assert len(quotes) == survey.total, [b for b, _ in quotes]


def test_guide_is_refused_without_a_survey():
    con = sqlite3.connect(":memory:")
    con.row_factory = sqlite3.Row
    con.executescript(Path("db/schema.sql").read_text(encoding="utf-8"))
    try:
        assert guide_article(con) is None
    finally:
        con.close()


def test_guide_shows_the_basis_split_with_quotes():
    con = connect(_db())
    try:
        art = guide_article(con)
        survey, _, quotes = basis_survey(con)
    finally:
        con.close()
    assert art is not None
    for brand in survey.dog_fit_brands + survey.garment_brands:
        assert e(brand) in art.body, brand
    # 引用が本文に載っていること。これが他所と違う唯一の中身
    assert any(q[:12] in art.body for _, q in quotes), "原文引用が1つも載っていない"


def test_empty_survey_object_is_rejected_by_the_builder():
    try:
        from pipeline.article import measuring_guide_article
        measuring_guide_article(BasisSurvey([], [], []), [])
    except ValueError:
        return
    raise AssertionError("調査結果なしで採寸ガイドが組み立てられてしまった")
