"""DB から Variant を読み出して、ブランド横断の推奨サイズを出す。

sizing.py を純粋に保つため、SQL に触れるのはこのモジュールだけにしている。
"""

from __future__ import annotations

import sqlite3
from collections import defaultdict
from pathlib import Path
from typing import Optional, Sequence

from .normalize import normalize_ranges
from .sizing import Dog, Fit, Variant, recommend_across_brands


def connect(path: str | Path) -> sqlite3.Connection:
    con = sqlite3.connect(str(path))
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys = ON")
    return con


def load_variants(con: sqlite3.Connection, category: str,
                  brand_slugs: Optional[Sequence[str]] = None
                  ) -> dict[str, list[Variant]]:
    """カテゴリ内の全サイズ行を、表ごとにまとめて返す。"""
    sql = "SELECT * FROM v_size_row WHERE category = ?"
    args: list = [category]
    if brand_slugs:
        sql += f" AND brand_slug IN ({','.join('?' * len(brand_slugs))})"
        args += list(brand_slugs)
    sql += " ORDER BY brand_slug, sort_order"

    charts: dict[str, list[Variant]] = defaultdict(list)
    for r in con.execute(sql, args):
        key = f"{r['brand_slug']}/{r['category']}/{r['series'] or '-'}"

        raw = {
            "neck": (r["neck_min"], r["neck_max"]),
            "chest": (r["chest_min"], r["chest_max"]),
            "back": (r["back_min"], r["back_max"]),
            "weight": (r["weight_min"], r["weight_max"]),
        }
        # 表が「服の実寸」なら犬基準へ変換する。変換したものは estimated になる。
        n = normalize_ranges(raw, r["measure_basis"], r["stretch"])

        charts[key].append(Variant(
            variant_id=r["variant_id"],
            brand_name=r["brand_name"],
            size_label=r["size_label"],
            sort_order=r["sort_order"],
            category=r["category"],
            stretch=n.scoring_stretch,
            # 保存時点の provenance と、変換由来の推定を両立させる。
            # どちらかが推定なら、出力は推定として扱う。
            provenance=("estimated"
                        if "estimated" in (r["provenance"], n.provenance)
                        else r["provenance"]),
            ranges=n.ranges,
        ))
    return dict(charts)


def recommend(con: sqlite3.Connection, dog: Dog, category: str = "wear") -> list[Fit]:
    return recommend_across_brands(dog, load_variants(con, category))


def sources_for(con: sqlite3.Connection, fits: Sequence[Fit]) -> list[sqlite3.Row]:
    """掲載時に必ず添える出典。これが取れない結果は公開しない。"""
    ids = [f.variant.variant_id for f in fits]
    if not ids:
        return []
    return list(con.execute(
        f"SELECT DISTINCT source_url AS url, source_fetched_at AS fetched_at, brand_name "
        f"FROM v_size_row WHERE variant_id IN ({','.join('?' * len(ids))})", ids))
