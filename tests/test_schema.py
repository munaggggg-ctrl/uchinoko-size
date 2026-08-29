"""スキーマの制約が実際に効いているかの確認。
『出所不明の数値は保存できない』が設計の中心なので、ここは必ず検証する。"""
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

SCHEMA = (ROOT / "db" / "schema.sql").read_text(encoding="utf-8")


def fresh():
    con = sqlite3.connect(":memory:")
    con.executescript(SCHEMA)
    con.execute("PRAGMA foreign_keys = ON")
    con.execute(
        "INSERT INTO source (id, kind, url, title, fetched_at) VALUES "
        "(1, 'brand_official', 'https://example.com/size', 'A社 公式サイズ表', '2026-08-29T10:00:00+09:00')"
    )
    con.execute("INSERT INTO brand (id, slug, name) VALUES (1, 'a-sha', 'A社')")
    con.execute(
        "INSERT INTO size_chart (id, brand_id, category, source_id, stretch) "
        "VALUES (1, 1, 'wear', 1, 'low')"
    )
    return con


def insert_variant(con, **kw):
    cols = {"chart_id": 1, "label": "S", "sort_order": 1,
            "chest_min": 30, "chest_max": 34,
            "provenance": "official", "source_id": 1, "confidence": None}
    cols.update(kw)
    keys = ", ".join(cols)
    marks = ", ".join("?" * len(cols))
    con.execute(f"INSERT INTO size_variant ({keys}) VALUES ({marks})", tuple(cols.values()))
    con.commit()


def expect_error(fn, label):
    try:
        fn()
    except sqlite3.IntegrityError:
        return
    raise AssertionError(f"制約が効いていない: {label}")


def test_valid_row_is_accepted():
    con = fresh()
    insert_variant(con)
    assert con.execute("SELECT COUNT(*) FROM size_variant").fetchone()[0] == 1


def test_provenance_is_required():
    con = fresh()
    expect_error(lambda: insert_variant(con, provenance=None), "provenance NOT NULL")


def test_unknown_provenance_is_rejected():
    con = fresh()
    expect_error(lambda: insert_variant(con, provenance="guess"), "provenance CHECK")


def test_source_is_required():
    con = fresh()
    expect_error(lambda: insert_variant(con, source_id=None), "source_id NOT NULL")


def test_estimated_requires_confidence():
    con = fresh()
    expect_error(lambda: insert_variant(con, provenance="estimated", confidence=None),
                 "推定値に confidence が無い")


def test_official_must_not_carry_confidence():
    con = fresh()
    expect_error(lambda: insert_variant(con, provenance="official", confidence=0.8),
                 "公式値に confidence が付いている")


def test_estimated_with_confidence_is_accepted():
    con = fresh()
    insert_variant(con, provenance="estimated", confidence=0.72)
    row = con.execute("SELECT provenance, confidence FROM size_variant").fetchone()
    assert row == ("estimated", 0.72)


def test_inverted_range_is_rejected():
    con = fresh()
    expect_error(lambda: insert_variant(con, chest_min=40, chest_max=30),
                 "min > max のレンジ")


def test_duplicate_size_label_is_rejected():
    con = fresh()
    insert_variant(con, label="S")
    expect_error(lambda: insert_variant(con, label="S", sort_order=2), "同一表内のラベル重複")


def test_estimation_source_may_omit_url():
    con = fresh()
    con.execute("INSERT INTO source (kind, title, fetched_at, note) VALUES "
                "('estimation', '当サイト推定', '2026-08-29', '体重から胴回りを回帰推定')")
    con.commit()
    assert con.execute(
        "SELECT COUNT(*) FROM source WHERE kind='estimation'").fetchone()[0] == 1


def test_non_estimation_source_requires_url():
    con = fresh()
    expect_error(
        lambda: con.execute(
            "INSERT INTO source (kind, title, fetched_at) "
            "VALUES ('brand_official', 'URLなし公式', '2026-08-29')"),
        "公式出典にURLが無い",
    )


def test_view_carries_provenance_and_source():
    con = fresh()
    insert_variant(con)
    row = con.execute(
        "SELECT brand_name, size_label, provenance, source_url, source_fetched_at "
        "FROM v_size_row").fetchone()
    assert row[0] == "A社" and row[2] == "official"
    assert row[3].startswith("https://") and row[4].startswith("2026-")


def test_deleting_a_chart_removes_its_variants():
    con = fresh()
    insert_variant(con)
    con.execute("DELETE FROM size_chart WHERE id = 1")
    con.commit()
    assert con.execute("SELECT COUNT(*) FROM size_variant").fetchone()[0] == 0
