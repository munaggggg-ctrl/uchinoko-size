import json
import re
import sqlite3
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from pipeline.build_db import build  # noqa: E402
from pipeline.lint import ERROR, lint  # noqa: E402
from pipeline.toolpage import (  # noqa: E402
    SLUG, ToolPageError, build_tool_page, export_charts, export_sources, render_page,
)

_DB = None


def _db() -> Path:
    """テスト用の実データDBは1回だけ作る。"""
    global _DB
    if _DB is None:
        _DB = Path(tempfile.mkdtemp()) / "t.db"
        build(_DB)
    return _DB


def test_every_row_carries_provenance():
    """出所のない数値を配信しない（引継書 第33項）。"""
    con = sqlite3.connect(str(_db()))
    charts = export_charts(con)
    con.close()
    assert charts
    for c in charts:
        for r in c["rows"]:
            assert r["prov"] in ("official", "estimated", "user"), r
            if r["prov"] == "estimated":
                assert r["conf"] is not None, r


def test_garment_actual_brands_are_marked_estimated():
    """服の実寸表記のブランドは、換算された推定値として出る。"""
    con = sqlite3.connect(str(_db()))
    charts = {c["brand"]: c for c in export_charts(con)}
    con.close()
    idog = charts["IDOG&ICAT"]
    assert idog["basis"] == "garment_actual"
    assert all(r["prov"] == "estimated" for r in idog["rows"])
    # 変換済みなので、採点側で伸縮性を二重に効かせない
    assert all(r["stretch"] is None for r in idog["rows"])

    calulu = charts["CALULU"]
    assert calulu["basis"] == "dog_fit_range"
    assert all(r["prov"] == "official" for r in calulu["rows"])


def test_page_passes_lint():
    art = build_tool_page(_db())
    errors = [f for f in lint(art.body) if f.severity == ERROR]
    assert not errors, [f.rule for f in errors]


def test_page_has_provenance_markers_and_sources():
    art = build_tool_page(_db())
    assert 'data-prov="official"' in art.body
    assert 'data-prov="estimated"' in art.body
    assert "出典" in art.body
    assert art.slug == SLUG
    assert len(art.sources) >= 10
    for s in art.sources:
        assert s.url.startswith("https://")
        assert re.fullmatch(r"\d{4}-\d{2}-\d{2}", s.fetched_at), s.fetched_at


def test_embedded_data_is_valid_json_and_complete():
    art = build_tool_page(_db())
    m = re.search(r'id="ucs-data">(.*?)</script>', art.body, re.S)
    assert m, "埋め込みデータが見つからない"
    data = json.loads(m.group(1))
    brands = {c["brand"] for c in data["charts"]}
    assert len(brands) == 10, brands
    assert sum(len(c["rows"]) for c in data["charts"]) == 78


def test_official_quote_is_shown_and_internal_note_is_not():
    """出典には公式の原文だけを出す。社内向けの判断メモは出さない。"""
    art = build_tool_page(_db())
    assert "サイズ表の数字は全てお洋服の仕上り寸法となっております。" in art.body
    for internal in ("dog_fit_range", "garment_actual", "直接確認済み", "要再確認"):
        assert internal not in art.body, internal


def test_refuses_to_render_without_sources():
    """出典が取れないページは作らない。"""
    try:
        render_page([{"brand": "X", "series": "", "basis": "dog_fit_range",
                      "source_url": "https://example.com", "fetched_at": "2026-01-01",
                      "rows": []}], [])
    except Exception:
        pass  # render 単体は落ちなくてよい。build_tool_page 側で止める
    con = sqlite3.connect(":memory:")
    con.executescript(Path("db/schema.sql").read_text(encoding="utf-8"))
    try:
        export_charts(con)
    except ToolPageError:
        return
    finally:
        con.close()
    raise AssertionError("空のDBからページを作ろうとして止まらなかった")


def test_no_blank_lines_inside_script_or_style():
    """wpautop が </p><p> を差し込む材料（改行）を、配信コードに残さない。"""
    art = build_tool_page(_db())
    for tag in ("script", "style"):
        for m in re.finditer(rf"<{tag}[^>]*>(.*?)</{tag}>", art.body, re.S):
            assert "\n" not in m.group(1), tag


def test_wrapped_in_html_block():
    """ブロックとして保存されると wpautop が外れる。二重の保険。"""
    art = build_tool_page(_db())
    assert art.body.startswith("<!-- wp:html -->")
    assert art.body.rstrip().endswith("<!-- /wp:html -->")


def test_line_comments_are_rejected():
    """1行化でコードが丸ごとコメントアウトされる事故を止める。"""
    from pipeline.toolpage import ToolPageError, _oneline
    try:
        _oneline("var a=1; // memo\nvar b=2;")
    except ToolPageError:
        return
    raise AssertionError("行コメントを含むコードが素通りした")


def test_title_reflects_the_actual_brand_count():
    """タイトルのブランド数を固定値にしない。本文だけ増えてタイトルが嘘になるのを防ぐ。"""
    art = build_tool_page(_db())
    m = re.search(r"(\d+)ブランド", art.title)
    assert m, art.title
    data = json.loads(re.search(r'id="ucs-data">(.*?)</script>', art.body, re.S).group(1))
    assert int(m.group(1)) == len({c["brand"] for c in data["charts"]})
