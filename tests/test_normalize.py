import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from pipeline.normalize import (  # noqa: E402
    DOG_FIT_RANGE, GARMENT_ACTUAL,
    garment_to_dog_range, normalize_ranges,
)
from pipeline.sizing import Dog, Variant, evaluate  # noqa: E402


def test_dog_fit_range_passes_through_unchanged():
    ranges = {"chest": (31.0, 34.0), "neck": (21.0, 23.0)}
    n = normalize_ranges(ranges, DOG_FIT_RANGE, "low")
    assert n.ranges == ranges
    assert n.provenance == "official" and n.confidence is None
    assert n.scoring_stretch == "low", "適合レンジ表では伸縮性は判定側で使う"


def test_garment_actual_becomes_estimated():
    n = normalize_ranges({"chest": (35.0, 35.0)}, GARMENT_ACTUAL, "low")
    assert n.provenance == "estimated", "変換した値を公式値として扱ってはいけない（第33項）"
    assert n.confidence == 0.6


def test_stretch_is_not_applied_twice():
    """変換でゆとり量に伸縮性を織り込んでいるので、判定側で再度緩めてはいけない。"""
    n = normalize_ranges({"chest": (35.0, 35.0)}, GARMENT_ACTUAL, "high")
    assert n.scoring_stretch is None


def test_single_value_chart_expands_to_a_range():
    lo, hi = garment_to_dog_range("chest", 35.0, 35.0, "low")
    assert lo < hi, "単一値の表でも犬側はレンジになる"
    assert (lo, hi) == (29.0, 33.5)


def test_dog_range_is_below_the_garment_measurement():
    """服の実寸35cmなら、胴回り35cmの犬は入らない。ここを外すと致命的。"""
    lo, hi = garment_to_dog_range("chest", 35.0, 35.0, "low")
    assert hi < 35.0


def test_stretch_allows_a_tighter_fit():
    _, hi_none = garment_to_dog_range("chest", 35.0, 35.0, "none")
    _, hi_high = garment_to_dog_range("chest", 35.0, 35.0, "high")
    assert hi_high > hi_none


def test_weight_is_never_converted():
    n = normalize_ranges({"weight": (1.6, 2.5)}, GARMENT_ACTUAL, "low")
    assert n.ranges["weight"] == (1.6, 2.5), "体重は犬についての値なので変換しない"


def test_back_length_is_matched_not_eased():
    lo, hi = garment_to_dog_range("back", 23.0, 23.0, "none")
    assert lo < 23.0 < hi, "着丈はゆとりではなく合わせる寸法"


def test_the_bug_this_module_exists_to_prevent():
    """実データでの回帰テスト。
    IDOG S は『胴周り 35cm』だが、これは服の実寸。
    変換せずに犬の適合レンジとして扱うと、胴回り35cmの犬にSを勧めてしまう。"""
    dog = Dog(chest=35.0)

    naive = Variant(1, "IDOG&ICAT", "S", 1, "wear", "low", "official",
                    {"chest": (35.0, 35.0)})
    assert evaluate(dog, naive).verdict in ("just", "fits"), "変換前は誤って適合と出る"

    n = normalize_ranges({"chest": (35.0, 35.0)}, GARMENT_ACTUAL, "low")
    correct = Variant(1, "IDOG&ICAT", "S", 1, "wear", n.scoring_stretch,
                      n.provenance, n.ranges)
    f = evaluate(dog, correct)
    assert f.verdict == "unfit", "変換後は正しく不適合になる"
    assert f.provenance == "estimated"
