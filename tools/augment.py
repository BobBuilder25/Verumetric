#!/usr/bin/env python3
"""Contamination-control augmentation (ADR-0005, config/augment.yaml).

CORD and SROIE are almost certainly in the training data of the frontier models
we call. Memorization inflates accuracy and suppresses provider divergence,
which would push us toward a false PIVOT B on routing and a false GO on
residual. So every page runs twice - as-is (the probe) and augmented - and ALL
T-metrics are computed on the augmented run.

Two design properties are load-bearing:

1. **Boxes are transformed with the image.** The corpora publish box-level
   annotations; rotating and cropping a page invalidates every one of them. Each
   augmented page carries the exact affine, and gold quads are mapped through
   it. Without this, Tier 1 grounding would be scored against coordinates for a
   page that no longer exists - and it would look like it was working.

2. **Per-page seeds derive from (global seed, doc_id)**, not from one sequential
   stream, so adding a page later does not re-augment every page after it.

Usage:
    python tools/augment.py --corpus cord
    python tools/augment.py --corpus all --force
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import random
import sys
from dataclasses import dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from _corpus import (  # noqa: E402
    CORPORA,
    DATA_AUGMENTED,
    DATA_RAW,
    REPO_ROOT,
    Field,
    Page,
    read_manifest,
    write_manifest,
)

DEFAULT_CONFIG = REPO_ROOT / "config" / "augment.yaml"


@dataclass(frozen=True)
class Transform:
    """The affine actually applied, so any box can be mapped after the fact."""

    rotation_deg: float
    src_width: int
    src_height: int
    rotated_width: int
    rotated_height: int
    crop_left: int
    crop_top: int
    out_width: int
    out_height: int

    def map_point(self, x: float, y: float) -> tuple[float, float]:
        """Source pixel -> augmented pixel.

        Rotation is about the source centre, into an expanded canvas (PIL's
        `expand=True` semantics), then the crop offset is subtracted.
        """
        theta = math.radians(-self.rotation_deg)  # PIL rotates counter-clockwise
        cx, cy = self.src_width / 2.0, self.src_height / 2.0
        dx, dy = x - cx, y - cy
        rx = dx * math.cos(theta) - dy * math.sin(theta)
        ry = dx * math.sin(theta) + dy * math.cos(theta)
        rx += self.rotated_width / 2.0
        ry += self.rotated_height / 2.0
        return rx - self.crop_left, ry - self.crop_top

    def map_quad(self, quad: list[list[float]]) -> list[list[float]]:
        return [list(self.map_point(px, py)) for px, py in quad]

    def to_json(self) -> dict:
        return {
            "rotation_deg": self.rotation_deg,
            "src_size": [self.src_width, self.src_height],
            "rotated_size": [self.rotated_width, self.rotated_height],
            "crop_offset": [self.crop_left, self.crop_top],
            "out_size": [self.out_width, self.out_height],
        }


def axis_aligned_hull(quad: list[list[float]]) -> list[float]:
    xs = [p[0] for p in quad]
    ys = [p[1] for p in quad]
    return [min(xs), min(ys), max(xs), max(ys)]


def page_rng(seed: int, doc_id: str) -> random.Random:
    """Deterministic per page, independent of iteration order or corpus size."""
    digest = hashlib.sha256(f"{seed}:{doc_id}".encode()).digest()
    return random.Random(int.from_bytes(digest[:8], "big"))


def _uniform(rng: random.Random, span) -> float:
    lo, hi = float(span[0]), float(span[1])
    return rng.uniform(lo, hi)


def augment_image(image, cfg: dict, rng: random.Random):
    """Apply the pipeline; return (image, Transform).

    Order matters and matches config/augment.yaml: rotate, crop, blur,
    brightness, noise, JPEG. Only rotation and crop move pixels, so only they
    enter the Transform.
    """
    from PIL import Image, ImageEnhance, ImageFilter

    src_w, src_h = image.width, image.height

    rotation = 0.0
    if cfg.get("rotation", {}).get("enabled", False):
        rotation = _uniform(rng, cfg["rotation"]["degrees"])
        fill = tuple(cfg["rotation"].get("fill", [255, 255, 255]))
        image = image.rotate(
            rotation,
            resample=Image.BICUBIC,
            expand=bool(cfg["rotation"].get("expand", True)),
            fillcolor=fill,
        )
    rot_w, rot_h = image.width, image.height

    crop_left = crop_top = 0
    if cfg.get("crop", {}).get("enabled", False):
        frac = _uniform(rng, cfg["crop"]["margin_fraction"])
        dx, dy = int(round(rot_w * frac)), int(round(rot_h * frac))
        # Positive fraction crops inward; negative pads outward.
        left, top = max(0, dx), max(0, dy)
        right, bottom = rot_w - max(0, dx), rot_h - max(0, dy)
        if right - left > 16 and bottom - top > 16:
            image = image.crop((left, top, right, bottom))
            crop_left, crop_top = left, top

    if cfg.get("blur", {}).get("enabled", False):
        radius = _uniform(rng, cfg["blur"]["gaussian_radius_px"])
        image = image.filter(ImageFilter.GaussianBlur(radius=radius))

    if cfg.get("brightness", {}).get("enabled", False):
        image = ImageEnhance.Brightness(image).enhance(_uniform(rng, cfg["brightness"]["factor"]))

    if cfg.get("noise", {}).get("enabled", False):
        import numpy as np

        sigma = _uniform(rng, cfg["noise"]["gaussian_sigma"])
        arr = np.asarray(image, dtype=np.float32)
        # Seeded from the page RNG so the noise is reproducible too.
        gen = np.random.default_rng(rng.getrandbits(63))
        arr = arr + gen.normal(0.0, sigma, arr.shape)
        image = Image.fromarray(np.clip(arr, 0, 255).astype("uint8"))

    transform = Transform(
        rotation_deg=rotation,
        src_width=src_w,
        src_height=src_h,
        rotated_width=rot_w,
        rotated_height=rot_h,
        crop_left=crop_left,
        crop_top=crop_top,
        out_width=image.width,
        out_height=image.height,
    )
    return image, transform


def augment_page(page: Page, cfg: dict, out_root: Path) -> tuple[Page, Transform]:
    from PIL import Image

    rng = page_rng(int(cfg["seed"]), page.doc_id)
    with Image.open(page.image_path()) as im:
        image = im.convert("RGB")
        image, transform = augment_image(image, cfg, rng)

        out_dir = out_root / page.corpus / "images"
        out_dir.mkdir(parents=True, exist_ok=True)
        out_path = out_dir / f"{page.doc_id}.jpg"
        quality = (
            int(_uniform(rng, cfg["jpeg"]["quality"])) if cfg.get("jpeg", {}).get("enabled") else 95
        )
        image.save(out_path, format="JPEG", quality=quality)

    mapped = [
        Field(
            label=f.label,
            text=f.text,
            quad=transform.map_quad(f.quad) if f.quad else [],
            field_class=f.field_class,
        )
        for f in page.fields
    ]
    augmented = Page(
        doc_id=page.doc_id,
        corpus=page.corpus,
        split=page.split,
        image=str(out_path.relative_to(REPO_ROOT)),
        width=transform.out_width,
        height=transform.out_height,
        fields=mapped,
    )

    meta_dir = out_root / page.corpus / "transforms"
    meta_dir.mkdir(parents=True, exist_ok=True)
    meta = {
        "doc_id": page.doc_id,
        "config_version": cfg.get("version"),
        "seed": cfg["seed"],
        "jpeg_quality": quality,
        "transform": transform.to_json(),
    }
    if cfg.get("boxes", {}).get("emit_axis_aligned_hull", True):
        meta["hulls"] = {f.label: axis_aligned_hull(f.quad) for f in mapped if f.quad}
    (meta_dir / f"{page.doc_id}.json").write_text(json.dumps(meta), encoding="utf-8")

    return augmented, transform


def main(argv: list[str] | None = None) -> int:
    import yaml

    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("--corpus", choices=[*CORPORA, "all"], required=True)
    ap.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    ap.add_argument("--raw", type=Path, default=DATA_RAW)
    ap.add_argument("--out", type=Path, default=DATA_AUGMENTED)
    ap.add_argument("--force", action="store_true")
    args = ap.parse_args(argv)

    cfg = yaml.safe_load(args.config.read_text(encoding="utf-8"))
    corpora = list(CORPORA) if args.corpus == "all" else [args.corpus]

    for corpus in corpora:
        pages = list(read_manifest(corpus, args.raw))
        out_manifest = args.out / corpus / "manifest.jsonl"
        if out_manifest.exists() and not args.force:
            print(f"{corpus}: already augmented, skipping (--force to redo)")
            continue

        augmented = []
        for i, page in enumerate(pages, 1):
            aug, _ = augment_page(page, cfg, args.out)
            augmented.append(aug)
            if i % 50 == 0:
                print(f"  {corpus}: {i}/{len(pages)}")

        write_manifest(corpus, augmented, args.out)
        print(f"{corpus}: {len(augmented)} augmented pages -> {out_manifest}")

    print("\nReminder: T-metrics are computed on the augmented run.")
    print("The as-is minus augmented delta per provider is the contamination estimate.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
