#!/usr/bin/env python3
"""End-to-end smoke test of the free half of the ladder. No credentials, no spend.

Renders a SYNTHETIC receipt, reads it with a real OCR engine to build the
reference layer, then runs four simulated provider claims through Tier 0 and
Tier 1 and prints what the stopping rule decided and why.

The four claims are the failure classes the design argues about:

    1. an honest reading                  -> should certify cheaply
    2. a transcription error              -> source_text and value disagree
    3. a hallucinated field               -> nothing like it is on the page
    4. right value, wrong location        -> the subtotal reported as the total

The receipt is synthetic and labeled as such. It is here to exercise the
machinery, and no T-metric is ever computed from it (ADR-0005).

Usage:
    python tools/demo.py
    python tools/demo.py --augmented     # same run on a degraded page
"""

from __future__ import annotations

import argparse
import sys
from decimal import Decimal
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

sys.path.insert(0, str(Path(__file__).resolve().parent))

from verumetric.checks.base import CheckOutcome  # noqa: E402
from verumetric.checks.tier0_deterministic import (  # noqa: E402
    ClassPolicy,
    check_arithmetic_reconciliation,
    check_counterpart_match,
    check_master_data_match,
    check_type_format,
    check_value_parses_from_source_text,
)
from verumetric.checks.tier1_provenance import (  # noqa: E402
    check_location_agrees,
    check_reference_reads_same_value,
    check_source_text_grounds,
)
from verumetric.checks.weights import EvidenceWeights  # noqa: E402
from verumetric.evidence import Decision, StoppingRule, combine  # noqa: E402
from verumetric.reference import TesseractEngine  # noqa: E402
from verumetric.schema import (  # noqa: E402
    BoundingBox,
    ExtractionResult,
    FieldClaim,
    FieldClass,
    Provenance,
)

# SYNTHETIC receipt. Amounts chosen so the arithmetic actually reconciles:
# 30,000 + 30,000 = 60,000 subtotal; + 6,000 tax = 66,000 total.
RECEIPT_LINES = [
    ("WARUNG SYNTHETIC", 40, 40, 34),
    ("SYNTHETIC TEST DOCUMENT - NOT REAL", 40, 84, 18),
    ("NASI GORENG    2", 40, 150, 26),
    ("30.000", 430, 150, 26),
    ("ES TEH MANIS   2", 40, 195, 26),
    ("30.000", 430, 195, 26),
    ("SUBTOTAL", 40, 280, 26),
    ("60.000", 430, 280, 26),
    ("TAX 10%", 40, 325, 26),
    ("6.000", 430, 325, 26),
    ("TOTAL", 40, 385, 30),
    ("66.000", 430, 385, 30),
]

IDR_TO_USD = Decimal("0.000061")  # illustrative rate, for this demo only
POLICY = ClassPolicy(
    decimal_separator=",",  # "." is a thousands separator here
    currency="IDR",
    usd_per_currency_unit=IDR_TO_USD,
)
GROUPS = {
    "tier1.source_text_grounds": "grounding",
    "tier1.location_agrees": "grounding",
    "tier0.type_format": "tier0_shape",
    "tier0.value_parses_from_source_text": "tier0_shape",
}


def render_receipt(path: Path) -> Path:
    img = Image.new("RGB", (640, 460), (255, 255, 255))
    draw = ImageDraw.Draw(img)
    for text, x, y, size in RECEIPT_LINES:
        try:
            font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", size)
        except OSError:
            font = ImageFont.load_default()
        draw.text((x, y), text, fill=(0, 0, 0), font=font)
    path.parent.mkdir(parents=True, exist_ok=True)
    img.save(path)
    return path


def find_bbox(layer, text: str, fallback: BoundingBox) -> BoundingBox:
    """Where the reference layer actually saw a string - a provider with honest
    provenance would point here."""
    for w in layer.words:
        if w.text.strip() == text:
            return w.bbox
    return fallback


def claim(cid, name, value, field_class, bbox, source_text) -> FieldClaim:
    return FieldClaim(
        claim_id=cid,
        field_name=name,
        field_class=field_class,
        value=value,
        provenance=Provenance.located(page=1, bbox=bbox, source_text=source_text),
    )


def run_checks(c, doc, layer, weights, invariant):
    results = [
        check_type_format(c, POLICY, weights),
        check_value_parses_from_source_text(c, POLICY, weights),
        check_source_text_grounds(c, layer, weights),
        check_location_agrees(c, layer, weights),
        check_reference_reads_same_value(c, layer, weights, POLICY),
        check_master_data_match(c, None, weights),
        check_counterpart_match(c, None, weights),
    ]
    if c.field_class is FieldClass.MONEY and c.field_name in ("total", "subtotal", "tax"):
        results.append(check_arithmetic_reconciliation(doc, invariant, POLICY, weights))
    return results


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("--augmented", action="store_true", help="degrade the page first")
    ap.add_argument("--out", type=Path, default=Path("data/demo"))
    args = ap.parse_args(argv)

    image_path = render_receipt(args.out / "synthetic_receipt.png")

    if args.augmented:
        import yaml
        from augment import augment_image, page_rng

        cfg = yaml.safe_load(Path("config/augment.yaml").read_text())
        with Image.open(image_path) as im:
            degraded, _ = augment_image(im.convert("RGB"), cfg, page_rng(cfg["seed"], "demo"))
        image_path = args.out / "synthetic_receipt_augmented.jpg"
        degraded.save(image_path, quality=50)
        print("running on the AUGMENTED page (rotated, blurred, recompressed)\n")

    print(f"reference layer: reading {image_path.name} with Tesseract...")
    layer = TesseractEngine().read(image_path, doc_id="demo-1")
    print(f"  read {len(layer.words)} words in {len(layer.lines())} lines\n")

    total_box = find_bbox(layer, "66.000", BoundingBox(x0=0.66, y0=0.83, x1=0.82, y1=0.90))
    sub_box = find_bbox(layer, "60.000", BoundingBox(x0=0.66, y0=0.60, x1=0.82, y1=0.67))
    tax_box = find_bbox(layer, "6.000", BoundingBox(x0=0.68, y0=0.70, x1=0.80, y1=0.77))
    empty_box = BoundingBox(x0=0.05, y0=0.95, x1=0.25, y1=0.99)

    # A document as a provider would return it, with three deliberate defects.
    honest_total = claim("c1", "total", "66.000", FieldClass.MONEY, total_box, "66.000")
    subtotal = claim("c2", "subtotal", "60.000", FieldClass.MONEY, sub_box, "60.000")
    tax = claim("c3", "tax", "6.000", FieldClass.MONEY, tax_box, "6.000")
    doc = ExtractionResult(
        document_id="demo-1",
        document_class="cord_receipt",
        provider_id="simulated",
        schema_version="0.1.0",
        claims=(honest_total, subtotal, tax),
    )

    cases = [
        ("honest reading", honest_total, POLICY.to_usd(Decimal("66000"))),
        (
            "transcription error",
            claim("c4", "total", "68.000", FieldClass.MONEY, total_box, "66.000"),
            POLICY.to_usd(Decimal("68000")),
        ),
        (
            "hallucinated field",
            claim("c5", "service_charge", "12.500", FieldClass.MONEY, empty_box, "12.500"),
            POLICY.to_usd(Decimal("12500")),
        ),
        (
            "right value, wrong place",
            claim("c6", "total", "60.000", FieldClass.MONEY, total_box, "60.000"),
            POLICY.to_usd(Decimal("60000")),
        ),
    ]

    weights = EvidenceWeights.load()
    invariant = {"id": "subtotal_plus_tax", "expr": "subtotal + tax == total", "tolerance": "1"}
    rule = StoppingRule()

    print(
        f"consequence: face value in {POLICY.currency} converted to USD "
        f"(a 66.000 receipt total is ${POLICY.to_usd(Decimal('66000')):.2f} at risk)\n"
    )
    print(f"{'case':<26}{'P(wrong)':>10}{'decision':>14}   what caught it")
    print("-" * 96)

    exit_code = 0
    for label, c, consequence in cases:
        doc_for_case = (
            doc
            if c.claim_id == "c1"
            else ExtractionResult(
                document_id="demo-1",
                document_class="cord_receipt",
                provider_id="simulated",
                schema_version="0.1.0",
                claims=(c, subtotal, tax)
                if c.field_name == "total"
                else (honest_total, subtotal, tax, c),
            )
        )
        results = run_checks(c, doc_for_case, layer, weights, invariant)
        posterior = combine(0.90, results, groups=GROUPS)
        # Tier 2 is the next paid check; its price is what the rule weighs against.
        decision, detail = rule.decide(posterior, c.field_class, consequence, Decimal("0.0013"))

        failed = [
            r.check_id.replace("tier0.", "T0 ").replace("tier1.", "T1 ")
            for r in results
            if r.outcome is CheckOutcome.FAIL
        ]
        note = ", ".join(failed) if failed else "nothing failed"
        print(f"{label:<26}{posterior.p_wrong:>10.4f}{str(decision):>14}   {note}")

        if label == "honest reading" and decision is not Decision.PASS:
            exit_code = 1
        if label != "honest reading" and decision is Decision.PASS:
            exit_code = 1

    unavailable = [
        r.check_id
        for r in run_checks(honest_total, doc, layer, weights, invariant)
        if r.outcome is CheckOutcome.UNAVAILABLE
    ]
    print("-" * 96)
    print(f"checks that could not run here: {', '.join(unavailable) or 'none'}")
    print("  (no counterpart documents or master data in this corpus - so measured")
    print("   coverage is a LOWER BOUND; real customer paper adds both.)")
    print("\ncost of everything above: $0.00 - every check on this page is free.")
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
