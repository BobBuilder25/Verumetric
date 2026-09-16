"""Tests for the reference layer and provenance grounding.

Every reference layer here is SYNTHETIC — hand-built word boxes, no image, no
OCR engine. That is the point of ADR-0006's split: the part that carries
evidence weight is pure and testable without installing a deep-learning runtime.
No T-metric is computed from anything in this file.
"""

from __future__ import annotations

import pytest

from verumetric.reference import (
    GroundingResult,
    ReferenceLayer,
    ReferenceWord,
    ground,
    iou,
    normalize,
    read_region,
    similarity,
)
from verumetric.schema import BoundingBox


def box(x0: float, y0: float, x1: float, y1: float) -> BoundingBox:
    return BoundingBox(x0=x0, y0=y0, x1=x1, y1=y1)


def word(
    text: str, x0: float, y0: float, x1: float, y1: float, conf: float = 0.99
) -> ReferenceWord:
    return ReferenceWord(text=text, bbox=box(x0, y0, x1, y1), confidence=conf)


@pytest.fixture
def layer() -> ReferenceLayer:
    """SYNTHETIC receipt-shaped page: three lines of words."""
    return ReferenceLayer(
        doc_id="synthetic-1",
        page=1,
        width=1000,
        height=1400,
        engine="synthetic",
        words=(
            word("NASI", 0.10, 0.300, 0.20, 0.320),
            word("GORENG", 0.21, 0.300, 0.34, 0.320),
            word("2", 0.60, 0.300, 0.63, 0.320),
            word("30,000", 0.70, 0.300, 0.85, 0.320),
            word("SUBTOTAL", 0.10, 0.500, 0.28, 0.520),
            word("60,000", 0.70, 0.500, 0.85, 0.520),
            word("TOTAL", 0.10, 0.700, 0.22, 0.720),
            word("66,000", 0.70, 0.700, 0.85, 0.720),
        ),
    )


# --- normalization ----------------------------------------------------------


def test_normalize_folds_separators_and_currency():
    assert normalize("Rp 66,000") == normalize("66000")
    assert normalize("$18,381.16") == normalize("18381 16")


def test_normalize_does_not_fold_digit_letter_confusions():
    """O/0 and l/1 are exactly the misreads the stack exists to catch. Folding
    them here would hide a wrong value behind a perfect grounding score."""
    assert normalize("O") != normalize("0")
    assert normalize("l") != normalize("1")


def test_similarity_bounds():
    assert similarity("TOTAL", "TOTAL") == 1.0
    assert similarity("", "") == 1.0
    assert similarity("TOTAL", "") == 0.0
    assert 0.0 < similarity("66,000", "68,000") < 1.0


def test_similarity_ignores_cosmetic_differences():
    assert similarity("Rp66.000", "66,000") == 1.0


# --- geometry ---------------------------------------------------------------


def test_iou_identical_is_one():
    assert iou(box(0.1, 0.1, 0.2, 0.2), box(0.1, 0.1, 0.2, 0.2)) == pytest.approx(1.0)


def test_iou_disjoint_is_zero():
    assert iou(box(0.1, 0.1, 0.2, 0.2), box(0.5, 0.5, 0.6, 0.6)) == 0.0


def test_iou_partial_overlap():
    assert 0.0 < iou(box(0.0, 0.0, 0.2, 0.2), box(0.1, 0.1, 0.3, 0.3)) < 1.0


# --- line structure ---------------------------------------------------------


def test_lines_group_by_vertical_position(layer):
    lines = layer.lines()
    assert len(lines) == 3
    assert [len(line) for line in lines] == [4, 2, 2]


def test_lines_are_in_reading_order(layer):
    first = layer.lines()[0]
    assert [layer.words[i].text for i in first] == ["NASI", "GORENG", "2", "30,000"]


def test_line_count_supports_recall_checks(layer):
    """The structural row count is how Tier 4 locates a skipped region when
    reconciliation fails for a missing line (part-3 §3)."""
    assert len(layer.lines()) == 3


# --- grounding: the load-bearing check --------------------------------------


def test_grounds_an_exact_value(layer):
    r = ground("66,000", layer)
    assert r.found
    assert r.score == 1.0
    assert r.matched_text == "66,000"


def test_grounds_across_several_words(layer):
    r = ground("NASI GORENG", layer)
    assert r.score == 1.0
    assert len(r.word_indices) == 2


def test_grounds_a_noisy_reading(layer):
    """A provider reading '66,00O' (letter O) should still locate the field —
    and score below 1.0, so the difference is visible as evidence."""
    r = ground("66,00O", layer)
    assert r.found
    assert 0.5 < r.score < 1.0


def test_a_hallucinated_value_does_not_ground(layer):
    """The check a fabricating extractor cannot pass: an invented value has no
    matching text anywhere on the page."""
    r = ground("99,999,999", layer)
    assert r.score < 0.6


def test_reports_location_agreement_when_a_box_is_claimed(layer):
    r = ground("66,000", layer, claimed_bbox=box(0.70, 0.700, 0.85, 0.720))
    assert r.score == 1.0
    assert r.location_agrees is True
    assert r.iou > 0.9


def test_right_value_wrong_location_is_visible(layer):
    """The failure class part-2 §5 names: the value exists, but not where the
    provider said. Collapsing the two signals would hide it entirely."""
    r = ground("66,000", layer, claimed_bbox=box(0.10, 0.300, 0.20, 0.320))
    assert r.score == 1.0
    assert r.location_agrees is False
    assert r.iou == 0.0


def test_location_agreement_is_none_without_a_claim(layer):
    r = ground("66,000", layer)
    assert r.location_agrees is None
    assert r.iou is None


def test_subtotal_and_total_are_distinguished(layer):
    """60,000 and 66,000 sit on different lines; grounding must not confuse the
    two, or a subtotal read as a total would ground perfectly."""
    subtotal = ground("60,000", layer)
    total = ground("66,000", layer)
    assert subtotal.bbox.y0 == pytest.approx(0.500)
    assert total.bbox.y0 == pytest.approx(0.700)


def test_empty_inputs_ground_to_nothing(layer):
    assert ground("", layer).found is False
    empty = ReferenceLayer(doc_id="d", page=1, width=100, height=100)
    assert ground("TOTAL", empty).found is False


def test_max_span_bounds_the_match(layer):
    """Without a span bound, a long enough window matches anything by
    accumulating characters."""
    r = ground("NASI GORENG 2 30,000", layer, max_span=1)
    assert len(r.word_indices) == 1


def test_grounding_result_found_property():
    assert GroundingResult(score=0.0, bbox=None, matched_text="").found is False


# --- independent read of a region -------------------------------------------


def test_read_region_returns_our_own_reading(layer):
    assert read_region(layer, box(0.68, 0.690, 0.90, 0.730)) == "66,000"


def test_read_region_is_empty_off_the_text(layer):
    assert read_region(layer, box(0.01, 0.010, 0.05, 0.020)) == ""


def test_read_region_joins_in_reading_order(layer):
    assert read_region(layer, box(0.05, 0.290, 0.95, 0.330)) == "NASI GORENG 2 30,000"


# --- persistence ------------------------------------------------------------


def test_round_trips_through_json(tmp_path, layer):
    path = layer.save(tmp_path / "ref.json")
    restored = ReferenceLayer.load(path)
    assert restored == layer


def test_engine_version_is_recorded(layer):
    """A reference-layer version change moves every grounding score, so it is
    recorded per page rather than inferred later (ADR-0006)."""
    assert "engine" in layer.to_json()
    assert "engine_version" in layer.to_json()
