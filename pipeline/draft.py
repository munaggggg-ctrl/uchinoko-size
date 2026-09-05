"""
記事の下書きを組み立てる。

方針:
  LLMを一切使わない。記事の中心は文章ではなく「他のどこにも載っていない表」であり、
  その表はDBから決まる（引継書 第31項）。したがって生成コストはゼロ、
  出力は毎回同じ、テストで固定できる。

  article.py が記事の組み立て方を持ち、query.py がDBを持つ。
  このモジュールは両者をつなぐだけで、独自の判断は持たない。

出力:
  build/<slug>.html を書き出す。公開は publish.py が行う。
  校閲（lint）を通らないものは書き出さない。壊れた記事をワークフローの
  後段に渡さないため、ここで止める。
"""

from __future__ import annotations

import re
import sqlite3
import sys
from pathlib import Path
from typing import Optional, Sequence

from .article import Article, BasisSurvey, Source, measuring_guide_article, weight_article
from .lint import ERROR, lint
from .query import connect, recommend
from .sizing import UNFIT, Fit

# 記事にする体重。飼い主が確実に知っている値であり、かつ検索で使われる丸い数字。
# 小型犬帯（10kg未満）に収め、ブランド横断の推奨が実際に割れる範囲を選ぶ。
DEFAULT_WEIGHTS: tuple[float, ...] = (2.0, 3.0, 4.0, 5.0, 6.0)

QUOTE = re.compile(r"原文[:：]\s*[「\"](.+?)[」\"]")


class DraftError(RuntimeError):
    pass


# --- DBから記事の材料を取り出す --------------------------------------

def _source_index(con: sqlite3.Connection) -> dict[int, Source]:
    """variant_id → 出典。数値と出典を切り離さないための索引。"""
    out: dict[int, Source] = {}
    for r in con.execute(
            "SELECT variant_id, brand_name, source_url, source_fetched_at FROM v_size_row"):
        out[r["variant_id"]] = Source(brand=r["brand_name"],
                                      url=r["source_url"],
                                      fetched_at=(r["source_fetched_at"] or "")[:10])
    return out


def _pair_with_sources(con: sqlite3.Connection,
                       fits: Sequence[Fit]) -> list[tuple[Fit, Source]]:
    index = _source_index(con)
    pairs = []
    for f in fits:
        src = index.get(f.variant.variant_id)
        if src is None:
            # 出典の取れない判定は載せない（引継書 第19項・第33項）
            continue
        pairs.append((f, src))
    return pairs


def basis_survey(con: sqlite3.Connection) -> tuple[BasisSurvey, list[Source],
                                                   list[tuple[str, str]]]:
    """サイズ表の基準を、DBに実際に入っている内容から数える。

    推測しない。DBに入っているのは公式の記載を確認できたものだけなので、
    ここで数えた結果はそのまま「調べた結果」になる。
    """
    dog, garment, unknown = [], [], []
    sources: list[Source] = []
    quotes: list[tuple[str, str]] = []
    seen = set()

    for r in con.execute(
            "SELECT DISTINCT b.name AS brand, c.measure_basis AS basis, "
            "       s.url AS url, s.fetched_at AS fetched_at, s.note AS note "
            "FROM size_chart c JOIN brand b ON b.id = c.brand_id "
            "JOIN source s ON s.id = c.source_id "
            "WHERE c.category = 'wear' ORDER BY b.name"):
        brand = r["brand"]
        if brand in seen:
            continue
        seen.add(brand)

        if r["basis"] == "dog_fit_range":
            dog.append(brand)
        elif r["basis"] == "garment_actual":
            garment.append(brand)
        else:
            unknown.append(brand)

        sources.append(Source(brand=brand, url=r["url"],
                              fetched_at=(r["fetched_at"] or "")[:10]))
        m = QUOTE.search(r["note"] or "")
        if m:
            quotes.append((brand, m.group(1)))

    return BasisSurvey(dog, garment, unknown), sources, quotes


# --- 記事 -------------------------------------------------------------

def weight_articles(con: sqlite3.Connection,
                    weights: Sequence[float] = DEFAULT_WEIGHTS) -> list[Article]:
    from .sizing import Dog

    all_brands = {r["name"] for r in con.execute(
        "SELECT DISTINCT b.name AS name FROM brand b "
        "JOIN size_chart c ON c.brand_id = b.id WHERE c.category = 'wear'")}
    out = []
    for w in weights:
        fits = recommend(con, Dog(weight=w), "wear")
        pairs = _pair_with_sources(con, fits)
        # 判定エンジンは必ず「最も惜しいサイズ」を返すので、まったく合わない体重でも
        # 行は埋まってしまう。×だけが並ぶ記事を publish しないための門。
        # ×の行そのものは「このブランドには無い」という情報なので表からは消さない。
        matched = [pr for pr in pairs if pr[0].verdict != UNFIT]
        if len(matched) < 3:
            continue
        shown = {f.variant.brand_name for f, _ in pairs}
        # 対応体重を公開していないブランドは、体重だけの比較には出てこない。
        # 黙って消すと「10ブランドと言っていたのに7つしかない」と見える。
        excluded = sorted(all_brands - shown)
        out.append(weight_article(w, pairs, excluded_brands=excluded))
    return out


def guide_article(con: sqlite3.Connection) -> Optional[Article]:
    survey, sources, quotes = basis_survey(con)
    if survey.total == 0:
        return None
    return measuring_guide_article(survey, sources, quotes)


def build_all(db_path: Optional[Path] = None) -> list[Article]:
    from .build_db import DEFAULT_OUT, build
    path = Path(db_path) if db_path else DEFAULT_OUT
    if not path.exists():
        build(path)

    con = connect(path)
    try:
        articles = weight_articles(con)
        guide = guide_article(con)
    finally:
        con.close()

    if guide is not None:
        articles.append(guide)

    if not articles:
        raise DraftError("記事が1本も組み立てられませんでした。DBを確認してください")

    # 公開前の校閲はワークフロー側でも走るが、壊れたものを後段へ渡さないために
    # ここでも止める。二重に掛ける価値のある工程。
    for a in articles:
        problems = [f for f in lint(a.body) if f.severity == ERROR]
        if problems:
            raise DraftError(
                f"校閲で ERROR: {a.slug} — "
                + "; ".join(f"{f.rule}(L{f.line})" for f in problems))
    return articles


def main(argv: list[str]) -> int:
    out_dir = Path(argv[0]) if argv else Path("build")
    try:
        articles = build_all()
    except DraftError as e:
        print(f"NG: {e}", file=sys.stderr)
        return 1

    out_dir.mkdir(parents=True, exist_ok=True)
    for a in articles:
        (out_dir / f"{a.slug}.html").write_text(a.body, encoding="utf-8")
    print(f"draft: {len(articles)}本を {out_dir}/ に書き出しました")
    for a in articles:
        print(f"    {a.slug}  {a.title}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
