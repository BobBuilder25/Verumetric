"""Tests for the contamination-control augmentation (tools/augment.py).

All images here are SYNTHETIC — solid colours and rectangles generated in
memory. They exist to test coordinate arithmetic, never to stand in for a
document. No T-metric is computed from synthetic data (ADR-0005).

The important test is `test_box_follows_a_rotated_landmark`: if the gold boxes
do not follow the image through augmentation, every Tier 1 grounding measurement
in the experiment is scored against coordinates for a page that no longer
exists — and it would look like it was working.
"""

from __future__ import annotations

import math

import pytest
from augment import Transform, augment_image, axis_aligned_hull, page_rng

PIL = pytest.importorskip("PIL")
from PIL import Image  # noqa: E402

CONFIG = {
    "version": 1,
    "seed": 20260916,
    "rotation": {"enabled": True, "degrees": [-7.0, 7.0], "expand": True, "fill": [255, 255, 255]},
    "crop": {"enabled": True, "margin_fraction": [-0.03, 0.04]},
    "blur": {"enabled": True, "gaussian_radius_px": [0.4, 1.6]},
    "brightness": {"enabled": True, "factor": [0.85, 1.15]},
    "noise": {"enabled": True, "gaussian_sigma": [1.0, 5.0]},
    "jpeg": {"enabled": True, "quality": [35, 60]},
    "boxes": {"emit_quad": True, "emit_axis_aligned_hull": True},
}


def synthetic_page(width: int = 400, height: int = 600) -> Image.Image:
    """SYNTHETIC white page with one black square — a landmark, not a document."""
    img = Image.new("RGB", (width, height), (255, 255, 255))
    for x in range(180, 220):
        for y in range(280, 320):
            img.putpixel((x, y), (0, 0, 0))
    return img


# --- seeding ----------------------------------------------------------------


def test_page_seed_is_stable_for_a_document():
    assert page_rng(1, "doc-a").random() == page_rng(1, "doc-a").random()


def test_page_seeds_differ_between_documents():
    assert page_rng(1, "doc-a").random() != page_rng(1, "doc-b").random()


def test_adding_a_page_does_not_change_other_pages():
    """Seeds derive from (seed, doc_id), not a sequential stream — so a page
    added next month does not silently re-augment the corpus measured last month."""
    before = [page_rng(7, f"doc-{i}").random() for i in range(5)]
    _ = page_rng(7, "doc-new").random()
    after = [page_rng(7, f"doc-{i}").random() for i in range(5)]
    assert before == after


def test_same_seed_reproduces_the_same_image():
    a, ta = augment_image(synthetic_page(), CONFIG, page_rng(CONFIG["seed"], "d1"))
    b, tb = augment_image(synthetic_page(), CONFIG, page_rng(CONFIG["seed"], "d1"))
    assert a.tobytes() == b.tobytes()
    assert ta == tb


# --- the coordinate arithmetic that matters ---------------------------------


def test_identity_transform_is_identity():
    t = Transform(0.0, 400, 600, 400, 600, 0, 0, 400, 600)
    assert t.map_point(123.0, 456.0) == pytest.approx((123.0, 456.0))


def test_crop_offset_shifts_points():
    t = Transform(0.0, 400, 600, 400, 600, 10, 20, 380, 560)
    assert t.map_point(100.0, 100.0) == pytest.approx((90.0, 80.0))


def test_rotation_maps_the_centre_to_the_new_centre():
    t = Transform(7.0, 400, 600, 420, 640, 0, 0, 420, 640)
    assert t.map_point(200.0, 300.0) == pytest.approx((210.0, 320.0))


def test_rotation_preserves_distance_from_centre():
    t = Transform(7.0, 400, 600, 420, 640, 0, 0, 420, 640)
    x, y = t.map_point(200.0, 100.0)
    moved = math.hypot(x - 210.0, y - 320.0)
    assert moved == pytest.approx(200.0, abs=1e-6)


def test_box_follows_a_rotated_landmark():
    """The black square's mapped box must land on the black pixels.

    This is the test that protects every Tier 1 grounding number in the
    experiment: annotations are published against the original page, and
    augmentation moves the pixels out from under them.
    """
    import numpy as np

    image, transform = augment_image(synthetic_page(), CONFIG, page_rng(CONFIG["seed"], "landmark"))
    quad = [[180.0, 280.0], [220.0, 280.0], [220.0, 320.0], [180.0, 320.0]]
    x0, y0, x1, y1 = axis_aligned_hull(transform.map_quad(quad))

    arr = np.asarray(image.convert("L"), dtype=np.float32)
    dark_ys, dark_xs = np.where(arr < 128)
    assert dark_xs.size > 0, "landmark vanished from the augmented page"

    # Every dark pixel should sit inside the mapped hull, within a tolerance for
    # blur bleed and JPEG ringing at the edges.
    tol = 6.0
    assert dark_xs.min() >= x0 - tol
    assert dark_xs.max() <= x1 + tol
    assert dark_ys.min() >= y0 - tol
    assert dark_ys.max() <= y1 + tol


def test_hull_contains_the_rotated_quad():
    t = Transform(7.0, 400, 600, 420, 640, 5, 5, 415, 635)
    quad = [[180.0, 280.0], [220.0, 280.0], [220.0, 320.0], [180.0, 320.0]]
    mapped = t.map_quad(quad)
    x0, y0, x1, y1 = axis_aligned_hull(mapped)
    for px, py in mapped:
        assert x0 - 1e-9 <= px <= x1 + 1e-9
        assert y0 - 1e-9 <= py <= y1 + 1e-9


def test_hull_is_larger_than_the_quad_under_rotation():
    """Documented consequence: axis-aligned grounding on a rotated page is the
    conservative case, because the hull is strictly larger than the true region."""
    t = Transform(7.0, 400, 600, 420, 640, 0, 0, 420, 640)
    quad = [[180.0, 280.0], [220.0, 280.0], [220.0, 320.0], [180.0, 320.0]]
    x0, y0, x1, y1 = axis_aligned_hull(t.map_quad(quad))
    assert (x1 - x0) > 40.0
    assert (y1 - y0) > 40.0


# --- pipeline behaviour -----------------------------------------------------


def test_rotation_expands_the_canvas_so_nothing_is_clipped():
    image, t = augment_image(synthetic_page(), CONFIG, page_rng(CONFIG["seed"], "expand"))
    assert t.rotated_width >= t.src_width
    assert t.rotated_height >= t.src_height


def test_augmentation_actually_degrades_the_page():
    """If augmentation were a no-op the contamination probe would be worthless:
    the as-is and augmented runs would agree by construction."""
    original = synthetic_page()
    augmented, _ = augment_image(original.copy(), CONFIG, page_rng(CONFIG["seed"], "degrade"))
    assert augmented.tobytes() != original.tobytes()


def test_disabled_stages_are_skipped():
    cfg = {**CONFIG, "rotation": {"enabled": False}, "crop": {"enabled": False}}
    _, t = augment_image(synthetic_page(), cfg, page_rng(1, "d"))
    assert t.rotation_deg == 0.0
    assert (t.crop_left, t.crop_top) == (0, 0)
    assert (t.out_width, t.out_height) == (400, 600)
