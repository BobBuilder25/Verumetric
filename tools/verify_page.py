#!/usr/bin/env python3
"""Run the free ladder over a real page: reference layer + grounding.

Takes an image and a set of provider claims with `source_text` but no boxes -
which is what an LLM-native extractor produces - reads the page with our own OCR
engine, and reports what could be grounded and what could not.

This is the honest test of a hard page. Grounding is the only confirming
evidence available on a document with no arithmetic and no counterpart, so the
share that grounds IS the ceiling on certified coverage for that document class.

Usage:
    python tools/verify_page.py --image PAGE.jpg --claims claims.json
"""

from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path

from verumetric.reference import TesseractEngine, ground


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("--image", type=Path, required=True)
    ap.add_argument("--claims", type=Path, required=True)
    ap.add_argument("--threshold", type=float, default=0.85)
    args = ap.parse_args(argv)

    if not args.image.exists():
        raise SystemExit(f"no such image: {args.image}")
    if shutil.which("tesseract") is None:
        raise SystemExit("no OCR engine installed (ADR-0006 fallback is tesseract)")

    doc = json.loads(args.claims.read_text(encoding="utf-8"))
    print(f"reading {args.image.name} with the reference layer...")
    layer = TesseractEngine().read(args.image, doc_id=doc.get("document_id", "page"))
    print(
        f"  {len(layer.words)} words, {len(layer.lines())} lines, "
        f"skew {layer.estimate_skew_deg():+.1f} deg\n"
    )

    if not layer.words:
        print("The reference layer read NOTHING.")
        print("Grounding is the only confirming evidence available here, so every")
        print("field goes to the exception stream. That is a measurement of the")
        print("document class, not a failure of the pipeline.")
        return 0

    print(f"{'field':<24}{'score':>7}  {'grounded':>9}   reference layer read")
    print("-" * 92)
    grounded = 0
    for c in doc["claims"]:
        result = ground(c["source_text"], layer)
        ok = result.score >= args.threshold
        grounded += int(ok)
        matched = (result.matched_text or "")[:38]
        print(f"{c['field']:<24}{result.score:>7.2f}  {'yes' if ok else 'NO':>9}   {matched!r}")

    total = len(doc["claims"])
    print("-" * 92)
    print(f"grounded: {grounded}/{total} ({grounded / total:.0%})")
    print(
        "\nOn a document with no arithmetic and no counterpart, grounding is the\n"
        "ONLY confirming evidence. Fields that do not ground cannot be certified\n"
        "at any price - the exception stream is where they belong, and the share\n"
        "above is the ceiling on coverage for this document class."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
