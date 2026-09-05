"""ドキュメントが実態からズレたら落ちるテスト。

README が「3ブランド24行」と書いたまま実データが10ブランド78行になっていた。
散文は黙って古くなる。数値を書いた箇所は、機械が確認できる形にしておく。
"""

import re
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from pipeline.build_db import build  # noqa: E402
from pipeline.query import connect  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
DOCS = ("README.md", "CLAUDE.md", "PROJECT_CONTEXT.md", "KNOWLEDGE.md", "TODO.md")


def _counts():
    db = Path(tempfile.mkdtemp()) / "docs.db"
    build(db)
    con = connect(db)
    try:
        brands = con.execute(
            "SELECT COUNT(DISTINCT brand_id) FROM size_chart").fetchone()[0]
        rows = con.execute("SELECT COUNT(*) FROM size_variant").fetchone()[0]
    finally:
        con.close()
    return brands, rows


def test_required_docs_exist():
    for name in DOCS:
        assert (ROOT / name).exists(), name


def test_brand_and_row_counts_in_docs_match_the_database():
    brands, rows = _counts()
    bad = []
    for name in DOCS:
        text = (ROOT / name).read_text(encoding="utf-8")
        for m in re.finditer(r"(\d+)\s*ブランド\s*(\d+)\s*行", text):
            if (int(m.group(1)), int(m.group(2))) != (brands, rows):
                bad.append(f"{name}: 「{m.group(0)}」 実際は {brands}ブランド{rows}行")
    assert not bad, bad


def test_claude_md_stays_short():
    """CLAUDE.md は毎回読み込まれる。肥らせると文脈を食う。
    専門知識は KNOWLEDGE.md へ、手順は Skills へ逃がす。"""
    lines = (ROOT / "CLAUDE.md").read_text(encoding="utf-8").splitlines()
    assert len(lines) <= 80, f"CLAUDE.md が {len(lines)} 行。80行以内に保つ"


def test_absolute_rules_are_present():
    """事故の再発を止めている条文が消えていないこと。"""
    text = (ROOT / "CLAUDE.md").read_text(encoding="utf-8")
    for phrase in ("出所のない数値を保存しない",
                   "推測しない",
                   "モール内ページを根拠にしない",
                   "直書きしない",
                   "下書きへ戻さない"):
        assert phrase in text, phrase
