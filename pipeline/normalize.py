"""
サイズ表の正規化。

実データを見て分かったこと（2026-08-29）:
  ブランドによって、サイズ表の数値が指すものが違う。

    CALULU  S : 胴回り 31〜34cm  → これは「この範囲の犬に合う」という犬の適合レンジ
    IDOG    S : 胴周り 35cm      → これは「服そのものの実寸」

  この2つを同じ列に並べて比較すると、判定が丸ごと壊れる。
  IDOGのS(35cm)を犬の適合レンジと誤読すると、胴回り35cmの犬にSを勧めてしまう。
  実際には服の実寸が35cmなので、35cmの犬には入らない。

  そこで garment_actual の表は、ゆとり量を引いて犬の適合レンジに変換する。
  この変換結果は必ず provenance='estimated' として保存し、公式値と混ぜない（第33項）。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

DOG_FIT_RANGE = "dog_fit_range"      # 表の数値＝犬の適合レンジ
GARMENT_ACTUAL = "garment_actual"    # 表の数値＝服の実寸

# 服の実寸から犬の実測を引いた「ゆとり」の想定量 (cm)。
#   dog ∈ [garment - loose, garment - tight]
#   tight 側を小さくすると「きつくても入る」判定になるので、安全側に取る。
# 伸縮性が高いほど、きつめでも着られるので tight 側を詰められる。
EASE: dict[str, dict[str, tuple[float, float]]] = {
    #                    (tight, loose)
    "chest": {"none": (2.0, 7.0), "low": (1.5, 6.0), "high": (0.5, 5.0)},
    "neck":  {"none": (1.5, 6.0), "low": (1.0, 5.0), "high": (0.0, 4.5)},
    # 着丈は「ゆとり」ではなく合わせる寸法。服の着丈≒犬の背丈でよい
    "back":  {"none": (-1.5, 1.5), "low": (-1.5, 1.5), "high": (-2.0, 2.0)},
}

# 変換の確からしさ。公式レンジ(1.0相当)より明確に低いことを数字で残す
CONVERSION_CONFIDENCE = 0.6

CONVERSION_NOTE = (
    "服の実寸表記を犬の適合レンジへ変換。"
    "dog ∈ [実寸 - loose, 実寸 - tight]、ゆとり量は伸縮性別に "
    "胴回り none(2.0,7.0)/low(1.5,6.0)/high(0.5,5.0)、"
    "首回り none(1.5,6.0)/low(1.0,5.0)/high(0.0,4.5)、"
    "着丈 ±1.5〜2.0cm。confidence=0.6"
)


def _ease(dim: str, stretch: Optional[str]) -> tuple[float, float]:
    table = EASE[dim]
    return table.get(stretch or "none", table["none"])


def garment_to_dog_range(dim: str,
                         lo: Optional[float],
                         hi: Optional[float],
                         stretch: Optional[str] = None
                         ) -> tuple[Optional[float], Optional[float]]:
    """服の実寸を、犬の適合レンジに変換する。

    表が単一値（IDOGのように「胴周り 35cm」）の場合は lo == hi で渡す。
    体重はそもそも犬についての数値なので、この関数を通さない。
    """
    if dim not in EASE:
        return (lo, hi)
    if lo is None and hi is None:
        return (None, None)

    tight, loose = _ease(dim, stretch)
    g_lo = lo if lo is not None else hi
    g_hi = hi if hi is not None else lo

    dog_lo = round(g_lo - loose, 1)
    dog_hi = round(g_hi - tight, 1)
    if dog_lo > dog_hi:                      # ゆとり幅が表の幅より広い場合の保険
        dog_lo, dog_hi = dog_hi, dog_lo
    return (dog_lo, dog_hi)


@dataclass(frozen=True)
class Normalized:
    """犬基準に揃えたサイズ1行。"""
    ranges: dict[str, tuple[Optional[float], Optional[float]]]
    provenance: str
    confidence: Optional[float]
    # 判定時に伸縮性の緩和を適用してよいか。
    # garment_actual の変換ではゆとり量に伸縮性を織り込み済みなので、
    # ここで None を返して二重適用を防ぐ。
    scoring_stretch: Optional[str]


def normalize_ranges(ranges: dict[str, tuple[Optional[float], Optional[float]]],
                     measure_basis: str,
                     stretch: Optional[str] = None) -> Normalized:
    """サイズ1行分のレンジを犬基準に揃える。

    dog_fit_range の表は official のまま通す（伸縮性は判定側で使う）。
    garment_actual の表は変換され、estimated + confidence が付く。
    """
    if measure_basis == DOG_FIT_RANGE:
        return Normalized(dict(ranges), "official", None, stretch)

    out: dict[str, tuple[Optional[float], Optional[float]]] = {}
    for dim, (lo, hi) in ranges.items():
        if dim == "weight":
            out[dim] = (lo, hi)          # 体重は犬についての値。変換しない
        else:
            out[dim] = garment_to_dog_range(dim, lo, hi, stretch)
    return Normalized(out, "estimated", CONVERSION_CONFIDENCE, None)
