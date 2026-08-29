import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from pipeline.sizing import (  # noqa: E402
    CHECK, FITS, JUST, UNFIT,
    Dog, Variant, best_size, evaluate, explain,
    recommend_across_brands, score_dimension,
)


def wear(label, order, neck, chest, back, weight=None, stretch=None, brand="A社"):
    return Variant(
        variant_id=order, brand_name=brand, size_label=label, sort_order=order,
        category="wear", stretch=stretch,
        ranges={"neck": neck, "chest": chest, "back": back,
                "weight": weight or (None, None)},
    )


# --- score_dimension ------------------------------------------------

def test_within_range_scores_high():
    r = score_dimension("chest", 32.0, 30.0, 34.0)
    assert r.direction == "in"
    assert r.score > 0.85


def test_over_max_is_penalised_hard():
    r = score_dimension("chest", 40.0, 30.0, 34.0)
    assert r.direction == "over"
    assert r.score < 0.05, "胴回りが6cm超過なら着られない。ほぼ0点でよい"


def test_ordering_survives_large_deviations():
    """大きく外れた候補どうしでも順序が保たれること。
    線形減点だと軒並み0点で並び、『どれが一番惜しいか』を出せなくなる。"""
    near = score_dimension("chest", 38.0, 30.0, 34.0).score
    far = score_dimension("chest", 46.0, 30.0, 34.0).score
    assert near > far > 0.0


def test_under_min_is_penalised_but_less():
    over = score_dimension("chest", 38.0, 30.0, 34.0).score
    under = score_dimension("chest", 26.0, 30.0, 34.0).score
    assert under > over, "同じ外れ幅なら『大きい』より『きつい』方が致命的"


def test_stretch_extends_upper_bound_only():
    tight = score_dimension("chest", 35.0, 30.0, 34.0, stretch="none")
    stretchy = score_dimension("chest", 35.0, 30.0, 34.0, stretch="high")
    assert stretchy.score > tight.score

    loose_none = score_dimension("chest", 27.0, 30.0, 34.0, stretch="none")
    loose_high = score_dimension("chest", 27.0, 30.0, 34.0, stretch="high")
    assert loose_high.score == loose_none.score, "伸縮性はぶかぶかを解決しない"


def test_missing_range_returns_none():
    assert score_dimension("back", 25.0, None, None) is None


def test_one_sided_range_is_handled():
    r = score_dimension("weight", 3.0, None, 5.0)
    assert r is not None and r.direction == "in"
    r2 = score_dimension("weight", 7.0, None, 5.0)
    assert r2.direction == "over" and r2.score < 0.5


def test_boundary_values_are_inside():
    assert score_dimension("chest", 30.0, 30.0, 34.0).direction == "in"
    assert score_dimension("chest", 34.0, 30.0, 34.0).direction == "in"


# --- evaluate -------------------------------------------------------

def test_perfect_fit_is_just():
    dog = Dog(neck=23, chest=32, back=24)
    v = wear("S", 1, (22, 25), (30, 34), (23, 26))
    f = evaluate(dog, v)
    assert f.verdict in (JUST, FITS)
    assert f.score > 0.85


def test_dominant_dimension_failure_forces_unfit():
    # 首回りと着丈は完璧だが、胴回りが入らない。総合を○にしてはいけない
    dog = Dog(neck=23, chest=45, back=24)
    v = wear("S", 1, (22, 25), (30, 34), (23, 26))
    f = evaluate(dog, v)
    assert f.verdict == UNFIT, "胴回りが致命的に外れているのに適合を出してはいけない"
    assert f.limiting.dim == "chest"


def test_partial_measurements_still_evaluate():
    dog = Dog(chest=32)  # 胴回りしか分からない飼い主は多い
    v = wear("S", 1, (22, 25), (30, 34), (23, 26))
    f = evaluate(dog, v)
    assert f is not None
    assert f.covered_weight == 0.50, "胴回りの重みだけで判定される"


def test_no_usable_measurement_returns_none():
    dog = Dog(weight=3.0)
    v = wear("S", 1, (22, 25), (30, 34), (23, 26))  # weight レンジなし
    assert evaluate(dog, v) is None


def test_harness_weights_neck_more_than_wear():
    dog = Dog(neck=30, chest=32)  # 首回りだけ大きく外れている
    w = Variant(1, "A社", "S", 1, "wear", None, "official",
                {"neck": (22, 25), "chest": (30, 34)})
    h = Variant(2, "A社", "S", 1, "harness", None, "official",
                {"neck": (22, 25), "chest": (30, 34)})
    assert evaluate(dog, h).score < evaluate(dog, w).score


# --- best_size ------------------------------------------------------

def test_picks_the_right_size_from_a_chart():
    dog = Dog(neck=23, chest=32, back=24)
    variants = [
        wear("SS", 1, (18, 21), (24, 28), (18, 21)),
        wear("S", 2, (22, 25), (30, 34), (23, 26)),
        wear("M", 3, (26, 29), (35, 40), (27, 31)),
    ]
    assert best_size(dog, variants).variant.size_label == "S"


def test_ties_prefer_the_smaller_size():
    dog = Dog(chest=30)
    variants = [
        wear("S", 1, (None, None), (28, 32), (None, None)),
        wear("M", 2, (None, None), (28, 32), (None, None)),
    ]
    assert best_size(dog, variants).variant.size_label == "S"


def test_large_dog_gets_unfit_not_a_wrong_recommendation():
    dog = Dog(neck=40, chest=60, back=45)
    variants = [wear("S", 1, (22, 25), (30, 34), (23, 26))]
    assert best_size(dog, variants).verdict == UNFIT


# --- cross-brand ----------------------------------------------------

def test_same_dog_gets_different_sizes_across_brands():
    """事業の中核となる主張が成立することの確認。
    胴回り32cmの犬は、A社ならS、B社ならM、C社ではSでも大きい。"""
    dog = Dog(neck=23, chest=32, back=24)
    charts = {
        "A": [wear("S", 1, (22, 25), (30, 34), (23, 26), brand="A社"),
              wear("M", 2, (26, 29), (35, 40), (27, 31), brand="A社")],
        "B": [wear("S", 1, (20, 23), (26, 30), (20, 22), brand="B社"),
              wear("M", 2, (24, 27), (31, 35), (23, 26), brand="B社")],
        "C": [wear("S", 1, (24, 28), (33, 38), (26, 29), brand="C社"),
              wear("M", 2, (29, 33), (39, 44), (30, 34), brand="C社")],
    }
    result = {f.variant.brand_name: f for f in recommend_across_brands(dog, charts)}

    assert result["A社"].variant.size_label == "S"
    assert result["B社"].variant.size_label == "M"
    assert result["C社"].variant.size_label == "S"
    assert result["C社"].verdict in (CHECK, UNFIT), "C社のSは同じ犬には大きい"
    assert result["A社"].score > result["C社"].score


def test_results_are_sorted_by_score():
    dog = Dog(chest=32)
    charts = {
        "A": [wear("S", 1, (None, None), (30, 34), (None, None), brand="A社")],
        "C": [wear("S", 1, (None, None), (38, 44), (None, None), brand="C社")],
    }
    out = recommend_across_brands(dog, charts)
    assert [f.variant.brand_name for f in out] == ["A社", "C社"]


# --- explain --------------------------------------------------------

def test_explain_states_the_limiting_reason():
    dog = Dog(neck=23, chest=45, back=24)
    f = evaluate(dog, wear("S", 1, (22, 25), (30, 34), (23, 26)))
    text = explain(f)
    assert "胴回り" in text and "×" in text


def test_explain_avoids_asserting_for_borderline():
    dog = Dog(neck=23, chest=34.8, back=24)   # 胴回りが上限を僅かに超える
    f = evaluate(dog, wear("S", 1, (22, 25), (30, 34), (23, 26)))
    assert f.verdict == CHECK, f"境界のはずが {f.verdict} (score={f.score})"
    assert "ご確認ください" in explain(f), "境界では断定せず確認を促す"


def test_provenance_is_carried_through():
    v = Variant(1, "A社", "S", 1, "wear", None, "estimated",
                {"chest": (30, 34)})
    f = evaluate(Dog(chest=32), v)
    assert f.provenance == "estimated", "推定値であることが出力まで残る"
