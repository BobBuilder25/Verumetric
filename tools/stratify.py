#!/usr/bin/env python3
"""Intake and stratification report (ADR-0005).

Answers, before any provider is called: what is actually in this corpus, how
ugly is it, how much of it carries the arithmetic invariants the evidence stack
depends on, and how much of it is unverifiable in principle.

The report contains counts, distributions and label names ONLY. No field text,
no crops, no document content of any kind - `reports/` is committed, and a table
of extracted receipt totals is document content whatever it is called.

Usage:
    python tools/stratify.py --corpus cord
    python tools/stratify.py --corpus all --source augmented
"""

from __future__ import annotations

import argparse
import json
import math
import statistics
import sys
from collections import Counter
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from _corpus import (  # noqa: E402
    CORPORA,
    DATA_AUGMENTED,
    DATA_RAW,
    REPO_ROOT,
    Page,
    load_field_class_map,
    read_manifest,
)

REPORTS = REPO_ROOT / "reports"
SCHEMA_BY_CORPUS = {
    "cord": REPO_ROOT / "config" / "schemas" / "receipt" / "cord.yaml",
}

# An "ugly" page, operationally. Thresholds are stated here rather than buried:
# they set the stratification the whole experiment is measured over.
BLUR_UGLY_BELOW = 100.0  # variance of Laplacian; lower = blurrier
LOW_RES_BELOW_PX = 700  # shorter side
SMALL_CROP_BELOW_PX = 14  # field height; below this a crop is hard to read


def laplacian_variance(image) -> float:
    """Sharpness proxy: variance of the Laplacian of the grayscale image."""
    import numpy as np

    arr = np.asarray(image.convert("L"), dtype=np.float32)
    if arr.shape[0] < 3 or arr.shape[1] < 3:
        return 0.0
    lap = -4.0 * arr[1:-1, 1:-1] + arr[:-2, 1:-1] + arr[2:, 1:-1] + arr[1:-1, :-2] + arr[1:-1, 2:]
    return float(lap.var())


def quad_angle_deg(quad: list[list[float]]) -> float | None:
    """Angle of a quad's top edge. None for a degenerate or empty quad."""
    if len(quad) < 2:
        return None
    (x0, y0), (x1, y1) = quad[0], quad[1]
    dx, dy = x1 - x0, y1 - y0
    if abs(dx) < 1e-6 and abs(dy) < 1e-6:
        return None
    return math.degrees(math.atan2(dy, dx))


def skew_estimate(page: Page) -> float | None:
    """Median text-line angle, when the annotations are not axis-aligned.

    CORD hulls and FUNSD boxes are axis-aligned, so this returns None for raw
    pages from those corpora - reported as 'not estimable from annotations'
    rather than as 0.0, which would be a fabricated measurement. On augmented
    pages the mapped quads do carry the rotation, so it becomes estimable.
    """
    angles = [a for f in page.fields if (a := quad_angle_deg(f.quad)) is not None]
    angles = [a for a in angles if abs(a) < 45.0]
    if len(angles) < 3:
        return None
    if all(abs(a) < 1e-6 for a in angles):
        return None
    return float(statistics.median(angles))


def analyze(corpus: str, source_root: Path) -> dict:
    from PIL import Image

    class_map = {}
    schema_path = SCHEMA_BY_CORPUS.get(corpus)
    if schema_path and schema_path.exists():
        class_map = load_field_class_map(schema_path)
        invariant_labels = _invariant_labels(schema_path)
    else:
        invariant_labels = set()

    pages = list(read_manifest(corpus, source_root))
    field_classes: Counter[str] = Counter()
    labels: Counter[str] = Counter()
    unmapped: Counter[str] = Counter()

    blurs: list[float] = []
    skews: list[float] = []
    short_sides: list[int] = []
    pages_with_totals = 0
    pages_with_line_items = 0
    pages_no_provenance = 0

    money_total = 0
    money_ambiguous = 0

    for page in pages:
        with Image.open(page.image_path()) as im:
            image = im.convert("RGB")
            blur = laplacian_variance(image)
        blurs.append(blur)
        short_sides.append(min(page.width, page.height))

        skew = skew_estimate(page)
        if skew is not None:
            skews.append(skew)

        label_counts = Counter(f.label for f in page.fields)
        has_total = any("total" in lbl.lower() for lbl in label_counts)
        has_items = any(lbl.startswith("menu") for lbl in label_counts)
        pages_with_totals += int(has_total)
        pages_with_line_items += int(has_items)
        if page.fields and not any(f.quad for f in page.fields):
            pages_no_provenance += 1

        for f in page.fields:
            labels[f.label] += 1
            fc = class_map.get(f.label)
            if fc is None:
                unmapped[f.label] += 1
                fc = "unmapped"
            field_classes[fc] += 1

            if fc == "money":
                money_total += 1
                if _is_ambiguous_money(f, page, label_counts, invariant_labels, blur):
                    money_ambiguous += 1

    return {
        "corpus": corpus,
        "source": str(source_root.relative_to(REPO_ROOT)),
        "generated": date.today().isoformat(),
        "pages": len(pages),
        "splits": dict(Counter(p.split for p in pages)),
        "fields_total": sum(field_classes.values()),
        "fields_by_class": dict(field_classes),
        "distinct_labels": len(labels),
        "unmapped_labels": dict(unmapped.most_common(40)),
        "unmapped_field_share": _share(sum(unmapped.values()), sum(field_classes.values())),
        "share_with_totals": _share(pages_with_totals, len(pages)),
        "share_with_line_items": _share(pages_with_line_items, len(pages)),
        "pages_without_any_provenance_box": pages_no_provenance,
        "image_quality": {
            "blur_laplacian_var": _dist(blurs),
            "share_blurry": _share(sum(1 for b in blurs if b < BLUR_UGLY_BELOW), len(blurs)),
            "short_side_px": _dist([float(s) for s in short_sides]),
            "share_low_res": _share(
                sum(1 for s in short_sides if s < LOW_RES_BELOW_PX), len(short_sides)
            ),
            "skew_deg": _dist(skews) if skews else None,
            "skew_note": (
                None
                if skews
                else "not estimable: annotations are axis-aligned, so no rotation is\n"
                "recoverable from them"
            ),
        },
        "ambiguity_floor": {
            "definition": (
                "money fields that are single-occurrence on the page AND not covered by any "
                "class-schema invariant AND whose crop is small or the page is blurry"
            ),
            "money_fields": money_total,
            "ambiguous_money_fields": money_ambiguous,
            "estimate": _share(money_ambiguous, money_total),
            "t9_threshold": 0.15,
            "t9_kill_signal": 0.30,
            "caveat": (
                "Measured on a receipt population. Receipts likely carry a HIGHER ambiguity "
                "floor than construction tickets backed by supplier statements. A T9 result "
                "here is not a verdict on the construction vertical (ADR-0005)."
            ),
        },
        "counterpart_documents": {
            "available": False,
            "note": (
                "Not present in any public corpus used. Cross-document reconciliation is "
                "untestable here; counterpart evidence is UNAVAILABLE, never FAIL. Measured "
                "coverage is therefore a LOWER BOUND (ADR-0005)."
            ),
        },
    }


def _invariant_labels(schema_path: Path) -> set[str]:
    """Labels named by at least one invariant - those have confirming evidence."""
    import re

    import yaml

    schema = yaml.safe_load(schema_path.read_text(encoding="utf-8"))
    out: set[str] = set()
    for inv in schema.get("invariants") or []:
        out.update(re.findall(r"[a-z_]+\.[a-z_]+", inv.get("expr", "")))
    return out


def _is_ambiguous_money(
    f, page: Page, label_counts: Counter, invariant_labels: set[str], blur: float
) -> bool:
    single_source = label_counts[f.label] == 1
    unreconciled = f.label not in invariant_labels
    if f.quad:
        ys = [p[1] for p in f.quad]
        crop_small = (max(ys) - min(ys)) < SMALL_CROP_BELOW_PX
    else:
        crop_small = True  # no box at all is worse than a small one
    return single_source and unreconciled and (crop_small or blur < BLUR_UGLY_BELOW)


def _share(n: int, d: int) -> float | None:
    return round(n / d, 4) if d else None


def _dist(values: list[float]) -> dict | None:
    if not values:
        return None
    s = sorted(values)
    return {
        "n": len(s),
        "min": round(s[0], 2),
        "p25": round(s[len(s) // 4], 2),
        "median": round(s[len(s) // 2], 2),
        "p75": round(s[(3 * len(s)) // 4], 2),
        "max": round(s[-1], 2),
    }


def to_markdown(r: dict) -> str:
    q = r["image_quality"]
    amb = r["ambiguity_floor"]
    lines = [
        f"# Intake report — {r['corpus']} ({r['source']})",
        "",
        f"Generated {r['generated']}. Counts and distributions only; no document content.",
        "",
        "## Population",
        "",
        f"- Pages: **{r['pages']}** ({r['splits']})",
        f"- Fields: **{r['fields_total']}** across {r['distinct_labels']} distinct labels",
        f"- Share with a total: **{_pct(r['share_with_totals'])}**",
        f"- Share with line items: **{_pct(r['share_with_line_items'])}**",
        f"- Pages with no provenance box at all: **{r['pages_without_any_provenance_box']}**",
        "",
        "## Fields by class",
        "",
        "| Field class | Count |",
        "|---|---|",
    ]
    for k, v in sorted(r["fields_by_class"].items(), key=lambda kv: -kv[1]):
        lines.append(f"| {k} | {v} |")
    lines += [
        "",
        f"Unmapped share: **{_pct(r['unmapped_field_share'])}**. Unmapped labels are "
        "treated as `text` and listed below so the class schema gets corrected from "
        "real data rather than guessed.",
        "",
    ]
    if r["unmapped_labels"]:
        lines += ["| Unmapped label | Count |", "|---|---|"]
        lines += [f"| `{k}` | {v} |" for k, v in r["unmapped_labels"].items()]
        lines.append("")

    lines += [
        "## Image quality",
        "",
        f"- Blur (variance of Laplacian): {q['blur_laplacian_var']}",
        f"- Share blurry (< {BLUR_UGLY_BELOW}): **{_pct(q['share_blurry'])}**",
        f"- Short side px: {q['short_side_px']}",
        f"- Share low-res (< {LOW_RES_BELOW_PX}px): **{_pct(q['share_low_res'])}**",
        f"- Skew: {q['skew_deg'] if q['skew_deg'] else q['skew_note']}",
        "",
        "## Ambiguity floor (T9 input)",
        "",
        f"> {amb['definition']}",
        "",
        f"- Money fields: **{amb['money_fields']}**",
        f"- Ambiguous: **{amb['ambiguous_money_fields']}**",
        f"- Estimate: **{_pct(amb['estimate'])}** "
        f"(T9 threshold {_pct(amb['t9_threshold'])}, kill signal {_pct(amb['t9_kill_signal'])})",
        "",
        f"{amb['caveat']}",
        "",
        "## Counterpart documents",
        "",
        f"{r['counterpart_documents']['note']}",
        "",
    ]
    return "\n".join(lines)


def _pct(v: float | None) -> str:
    return "n/a" if v is None else f"{v * 100:.1f}%"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("--corpus", choices=[*CORPORA, "all"], required=True)
    ap.add_argument("--source", choices=["raw", "augmented"], default="raw")
    ap.add_argument("--out", type=Path, default=REPORTS)
    args = ap.parse_args(argv)

    root = DATA_RAW if args.source == "raw" else DATA_AUGMENTED
    corpora = list(CORPORA) if args.corpus == "all" else [args.corpus]
    args.out.mkdir(parents=True, exist_ok=True)

    for corpus in corpora:
        result = analyze(corpus, root)
        stem = f"intake-{corpus}-{args.source}"
        (args.out / f"{stem}.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
        (args.out / f"{stem}.md").write_text(to_markdown(result), encoding="utf-8")
        print(to_markdown(result))
        print(f"\nwritten: {args.out / stem}.md / .json\n")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
