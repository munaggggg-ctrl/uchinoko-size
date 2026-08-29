"""
サイズ適合判定エンジン.

このモジュールが事業の中核。実測値からブランド別の推奨サイズを出す。
方針:
  - 純粋関数として書く。DBもHTTPも触らない（テストできることを優先）
  - 「なぜその判定になったか」を必ず返す。理由を出せない推薦は掲載しない
  - 推定であることを出力に持たせる。断定しない
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Optional, Sequence

# --- 判定ラベル ------------------------------------------------------

JUST = "just"        # ◎ ぴったり
FITS = "fits"        # ○ 適合
CHECK = "check"      # △ 要確認
UNFIT = "unfit"      # × 不適合

MARK = {JUST: "◎", FITS: "○", CHECK: "△", UNFIT: "×"}

# --- 寸法の重み ------------------------------------------------------
# カテゴリごとに、どの寸法が購入可否を支配するかは違う。
# 犬服は胴回り、ハーネスは首回りと胴回り、キャリーは体重と体長。
WEIGHTS: dict[str, dict[str, float]] = {
    "wear":    {"chest": 0.50, "back": 0.25, "neck": 0.20, "weight": 0.05},
    "harness": {"chest": 0.45, "neck": 0.35, "weight": 0.20},
    "carrier": {"weight": 0.60, "back": 0.40},
}

# 「きつい側」の外れは「ゆるい側」より致命的（着られない/入らない）
OVER_PENALTY = {"chest": 3.0, "neck": 3.0, "back": 1.6, "weight": 2.2}
UNDER_PENALTY = {"chest": 1.4, "neck": 1.2, "back": 1.8, "weight": 0.8}

# 伸縮性による上限の緩和率
STRETCH_SLACK = {"none": 0.00, "low": 0.03, "high": 0.08, None: 0.00}

# レンジ内で最も快適な位置（下限から何割の地点か）。やや余裕側に置く
SWEET_SPOT = 0.45


@dataclass(frozen=True)
class Dog:
    """うちの子の実測値。分かっている項目だけ入れる。"""
    neck: Optional[float] = None
    chest: Optional[float] = None
    back: Optional[float] = None
    weight: Optional[float] = None

    def get(self, dim: str) -> Optional[float]:
        return getattr(self, dim)

    def known_dims(self) -> set[str]:
        return {d for d in ("neck", "chest", "back", "weight") if self.get(d) is not None}


@dataclass(frozen=True)
class Variant:
    """サイズ表の1行。DBの size_variant に対応。"""
    variant_id: int
    brand_name: str
    size_label: str
    sort_order: int = 0
    category: str = "wear"
    stretch: Optional[str] = None
    provenance: str = "official"
    ranges: dict[str, tuple[Optional[float], Optional[float]]] = field(default_factory=dict)

    def range_of(self, dim: str) -> tuple[Optional[float], Optional[float]]:
        return self.ranges.get(dim, (None, None))


@dataclass(frozen=True)
class DimResult:
    dim: str
    value: float
    lo: Optional[float]
    hi: Optional[float]
    score: float
    direction: str          # 'in' | 'over' | 'under'
    reason: str


@dataclass(frozen=True)
class Fit:
    variant: Variant
    score: float                     # 0.0–1.0
    verdict: str                     # JUST / FITS / CHECK / UNFIT
    dims: tuple[DimResult, ...]
    covered_weight: float            # 判定に使えた寸法の重み合計
    provenance: str

    @property
    def mark(self) -> str:
        return MARK[self.verdict]

    @property
    def limiting(self) -> Optional[DimResult]:
        """判定を最も引き下げた寸法。「なぜ」を説明するために使う。"""
        out = [d for d in self.dims if d.direction != "in"]
        return min(out, key=lambda d: d.score) if out else None


DIM_JA = {"neck": "首回り", "chest": "胴回り", "back": "着丈", "weight": "体重"}
UNIT = {"neck": "cm", "chest": "cm", "back": "cm", "weight": "kg"}


def _span(lo: Optional[float], hi: Optional[float]) -> float:
    """外れ量を正規化するための基準幅。片側しかない表にも耐えるようにする。"""
    if lo is not None and hi is not None and hi > lo:
        return hi - lo
    base = hi if hi is not None else lo
    return max(abs(base) * 0.10, 0.5) if base else 1.0


def score_dimension(dim: str, value: float,
                    lo: Optional[float], hi: Optional[float],
                    stretch: Optional[str] = None) -> Optional[DimResult]:
    """1寸法の適合度を 0.0–1.0 で返す。表に記載がなければ None。"""
    if lo is None and hi is None:
        return None

    span = _span(lo, hi)
    unit = UNIT[dim]
    name = DIM_JA[dim]

    # 伸縮性は上限のみ緩める。下限（ぶかぶか）は伸縮では解決しない
    slack = STRETCH_SLACK.get(stretch, 0.0)
    ehi = hi * (1 + slack) if hi is not None else None

    # 外れ量は指数で減衰させる。線形にすると大きく外れた候補が軒並み0点で並び、
    # 「どのブランドが一番惜しいか」の順序が失われるため。
    if ehi is not None and value > ehi:
        over = (value - ehi) / span
        score = math.exp(-OVER_PENALTY[dim] * over)
        reason = f"{name} {value}{unit} は上限 {hi}{unit} を超えています"
        return DimResult(dim, value, lo, hi, round(score, 4), "over", reason)

    if lo is not None and value < lo:
        under = (lo - value) / span
        score = math.exp(-UNDER_PENALTY[dim] * under)
        reason = f"{name} {value}{unit} は下限 {lo}{unit} を下回ります"
        return DimResult(dim, value, lo, hi, round(score, 4), "under", reason)

    # レンジ内。中心よりやや余裕側を最良として、端に寄るほど僅かに減点する
    if lo is not None and hi is not None and hi > lo:
        sweet = lo + (hi - lo) * SWEET_SPOT
        offset = abs(value - sweet) / (hi - lo)
        score = 1.0 - min(offset, 1.0) * 0.30
        if value > sweet:
            reason = f"{name} は範囲内（やや詰まり気味）"
        else:
            reason = f"{name} は範囲内（余裕あり）"
    else:
        score = 0.95
        reason = f"{name} は範囲内"

    return DimResult(dim, value, lo, hi, round(score, 4), "in", reason)


def evaluate(dog: Dog, variant: Variant) -> Optional[Fit]:
    """1つのサイズに対する適合を判定する。判定材料が無ければ None。"""
    weights = WEIGHTS.get(variant.category, WEIGHTS["wear"])

    results: list[DimResult] = []
    total_w = 0.0
    acc = 0.0

    for dim, w in weights.items():
        v = dog.get(dim)
        if v is None:
            continue
        lo, hi = variant.range_of(dim)
        r = score_dimension(dim, v, lo, hi, variant.stretch)
        if r is None:
            continue
        results.append(r)
        acc += r.score * w
        total_w += w

    if total_w == 0:
        return None

    score = acc / total_w

    # 支配的な寸法（重み最大）が明確に外れている場合は、平均が高くても不適合に落とす。
    # 「胴回りが入らないのに総合○」を出さないための安全弁。
    dominant = max(weights, key=lambda d: weights[d])
    for r in results:
        if r.dim == dominant and r.direction != "in" and r.score < 0.5:
            score = min(score, 0.45)

    verdict = (JUST if score >= 0.90 else
               FITS if score >= 0.75 else
               CHECK if score >= 0.55 else
               UNFIT)

    return Fit(
        variant=variant,
        score=round(score, 4),
        verdict=verdict,
        dims=tuple(results),
        covered_weight=round(total_w, 4),
        provenance=variant.provenance,
    )


def best_size(dog: Dog, variants: Sequence[Variant]) -> Optional[Fit]:
    """同一ブランド・同一表の中から最良の1サイズを選ぶ。"""
    fits = [f for f in (evaluate(dog, v) for v in variants) if f is not None]
    if not fits:
        return None
    # 同点なら小さい方（sort_order が小さい方）を選ぶ。大きめを勧めて失敗する方が損失が大きい
    return max(fits, key=lambda f: (f.score, -f.variant.sort_order))


def recommend_across_brands(dog: Dog,
                            variants_by_chart: dict[str, Sequence[Variant]]
                            ) -> list[Fit]:
    """ブランド横断の推奨サイズ一覧。これがサイトの中核出力。"""
    out = []
    for _chart_key, variants in variants_by_chart.items():
        f = best_size(dog, variants)
        if f is not None:
            out.append(f)
    return sorted(out, key=lambda f: (-f.score, f.variant.brand_name))


def explain(fit: Fit) -> str:
    """掲載用の一文。断定を避け、根拠の寸法を必ず添える。"""
    v = fit.variant
    head = f"{v.brand_name} は {v.size_label} が {fit.mark}"
    lim = fit.limiting
    if fit.verdict == UNFIT and lim:
        return f"{head}（{lim.reason}）"
    if fit.verdict == CHECK and lim:
        return f"{head}。{lim.reason}ので、購入前にご確認ください"
    if lim:
        return f"{head}。{lim.reason}"
    tight = [d for d in fit.dims if d.direction == "in" and d.score < 0.85]
    if tight:
        return f"{head}。{tight[0].reason}"
    return f"{head}"
