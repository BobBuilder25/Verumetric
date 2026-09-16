#!/usr/bin/env python3
"""Fetch CORD, SROIE and FUNSD into data/raw/ (ADR-0005).

Idempotent: a corpus whose manifest already lists the requested number of pages
is skipped unless --force. Nothing is written outside data/, which is gitignored,
and the pre-commit guard blocks corpus content from ever being committed.

Licenses, verified 2026-09-16 (ADR-0005):

  CORD   CC BY 4.0. Commercial use permitted with attribution.
  FUNSD  Non-commercial, research and educational use ONLY. Fine for the
         experiment; may not back any commercial claim or customer demo.
  SROIE  License NOT CONFIRMED - the ICDAR RRC site was unreachable and no
         clear statement was found elsewhere. This tool therefore REFUSES to
         download SROIE. Supply the archive yourself, having accepted the
         organizers' terms, with --sroie-archive and --accept-sroie-terms.

Usage:
    python tools/download_corpora.py --corpus cord --limit 400
    python tools/download_corpora.py --corpus funsd --limit 50
    python tools/download_corpora.py --corpus sroie \
        --sroie-archive ~/Downloads/sroie.zip --accept-sroie-terms
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
import urllib.request
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from _corpus import DATA_RAW, Field, Page, manifest_path, write_manifest  # noqa: E402

CORD_HF_REPO = "naver-clova-ix/cord-v2"
FUNSD_URL = "https://guillaumejaume.github.io/FUNSD/dataset.zip"

LICENSES = {
    "cord": (
        "CORD (Consolidated Receipt Dataset), NAVER CLOVA.\n"
        "License: Creative Commons Attribution 4.0 International (CC BY 4.0).\n"
        "Commercial use permitted with attribution.\n"
        "Source: https://github.com/clovaai/cord\n"
    ),
    "funsd": (
        "FUNSD (Form Understanding in Noisy Scanned Documents).\n"
        "License: NON-COMMERCIAL, RESEARCH AND EDUCATIONAL USE ONLY.\n"
        "Images are a subset of RVL-CDIP and carry their own copyright; the\n"
        "licensee is responsible for determining what further licenses apply.\n"
        "NOT usable for any commercial claim, customer demo or marketing use.\n"
        "Source: https://guillaumejaume.github.io/FUNSD/work/\n"
    ),
    "sroie": (
        "SROIE (ICDAR 2019 Robust Reading Challenge, Task 3).\n"
        "License: NOT CONFIRMED as of 2026-09-16. Distributed through a\n"
        "registration-gated competition portal; third-party mirrors do not\n"
        "carry the organizers' terms. Treated as research-only pending written\n"
        "confirmation. Confirm before any use beyond this experiment.\n"
        "Source: https://rrc.cvc.uab.es/?ch=13\n"
    ),
}


def _write_license(corpus: str, out_root: Path) -> None:
    d = out_root / corpus
    d.mkdir(parents=True, exist_ok=True)
    (d / "LICENSE.txt").write_text(LICENSES[corpus], encoding="utf-8")


def _already_have(corpus: str, limit: int | None, out_root: Path) -> bool:
    path = manifest_path(corpus, out_root)
    if not path.exists():
        return False
    n = sum(1 for line in path.open(encoding="utf-8") if line.strip())
    return n >= limit if limit else n > 0


# --------------------------------------------------------------------------- CORD


def fetch_cord(out_root: Path, limit: int | None) -> list[Page]:
    """CORD via Hugging Face. Test split first, then train, up to `limit`.

    The test split leads deliberately: it is the split the published results are
    quoted on, so an accuracy number here is comparable to the literature, and
    any gap is informative rather than ambiguous.
    """
    try:
        from datasets import load_dataset
    except ImportError as exc:  # pragma: no cover - environment-dependent
        raise SystemExit(
            "CORD needs the `datasets` package: uv sync (it is in pyproject)."
        ) from exc

    images_dir = out_root / "cord" / "images"
    ann_dir = out_root / "cord" / "annotations"
    images_dir.mkdir(parents=True, exist_ok=True)
    ann_dir.mkdir(parents=True, exist_ok=True)

    pages: list[Page] = []
    for split in ("test", "train"):
        if limit is not None and len(pages) >= limit:
            break
        ds = load_dataset(CORD_HF_REPO, split=split)
        for idx, row in enumerate(ds):
            if limit is not None and len(pages) >= limit:
                break
            doc_id = f"cord-{split}-{idx:05d}"
            image = row["image"]
            image_path = images_dir / f"{doc_id}.jpg"
            if not image_path.exists():
                image.convert("RGB").save(image_path, quality=95)

            gt = row["ground_truth"]
            gt = json.loads(gt) if isinstance(gt, str) else gt
            (ann_dir / f"{doc_id}.json").write_text(
                json.dumps(gt, ensure_ascii=False), encoding="utf-8"
            )

            pages.append(
                Page(
                    doc_id=doc_id,
                    corpus="cord",
                    split=split,
                    image=str(image_path.relative_to(out_root.parent.parent)),
                    width=image.width,
                    height=image.height,
                    fields=_cord_fields(gt),
                )
            )
    return pages


def _cord_fields(gt: dict) -> list[Field]:
    """Flatten CORD's valid_line structure into labeled quads.

    CORD publishes per-word quads grouped into lines that carry the entity
    label. Words of one entity are merged into a single quad by hull, because a
    field claim points at a value, not at its words.
    """
    out: list[Field] = []
    for line in gt.get("valid_line", []):
        label = line.get("category", "unknown")
        words = line.get("words", [])
        if not words:
            continue
        xs: list[float] = []
        ys: list[float] = []
        texts: list[str] = []
        for w in words:
            q = w.get("quad", {})
            for i in (1, 2, 3, 4):
                if f"x{i}" in q:
                    xs.append(float(q[f"x{i}"]))
                    ys.append(float(q[f"y{i}"]))
            texts.append(str(w.get("text", "")))
        if not xs:
            continue
        x0, x1, y0, y1 = min(xs), max(xs), min(ys), max(ys)
        out.append(
            Field(
                label=label,
                text=" ".join(t for t in texts if t),
                quad=[[x0, y0], [x1, y0], [x1, y1], [x0, y1]],
            )
        )
    return out


# -------------------------------------------------------------------------- FUNSD


def fetch_funsd(out_root: Path, limit: int | None) -> list[Page]:
    """FUNSD from its official zip, so the terms travel with the data."""
    corpus_dir = out_root / "funsd"
    corpus_dir.mkdir(parents=True, exist_ok=True)
    archive = corpus_dir / "dataset.zip"

    if not archive.exists():
        print(f"downloading {FUNSD_URL}")
        with urllib.request.urlopen(FUNSD_URL) as resp, archive.open("wb") as fh:
            shutil.copyfileobj(resp, fh)

    extract_dir = corpus_dir / "extracted"
    if not extract_dir.exists():
        with zipfile.ZipFile(archive) as zf:
            zf.extractall(extract_dir)

    ann_files = sorted(extract_dir.rglob("annotations/*.json"))
    pages: list[Page] = []
    for path in ann_files:
        if limit is not None and len(pages) >= limit:
            break
        image_path = _funsd_image_for(path)
        if image_path is None:
            print(f"  skip {path.name}: no matching image", file=sys.stderr)
            continue
        ann = json.loads(path.read_text(encoding="utf-8"))
        width, height = _image_size(image_path)
        fields = [
            Field(
                label=item.get("label", "other"),
                text=item.get("text", ""),
                quad=_box_to_quad(item["box"]),
            )
            for item in ann.get("form", [])
            if item.get("box")
        ]
        pages.append(
            Page(
                doc_id=f"funsd-{path.stem}",
                corpus="funsd",
                split="all",
                image=str(image_path.relative_to(out_root.parent.parent)),
                width=width,
                height=height,
                fields=fields,
            )
        )
    return pages


def _funsd_image_for(ann_path: Path) -> Path | None:
    base = ann_path.parent.parent / "images"
    for ext in (".png", ".jpg", ".jpeg", ".tif", ".tiff"):
        candidate = base / f"{ann_path.stem}{ext}"
        if candidate.exists():
            return candidate
    return None


def _box_to_quad(box: list[float]) -> list[list[float]]:
    x0, y0, x1, y1 = (float(v) for v in box)
    return [[x0, y0], [x1, y0], [x1, y1], [x0, y1]]


def _image_size(path: Path) -> tuple[int, int]:
    from PIL import Image

    with Image.open(path) as im:
        return im.width, im.height


# -------------------------------------------------------------------------- SROIE


def fetch_sroie(
    out_root: Path, limit: int | None, archive: Path | None, accepted: bool
) -> list[Page]:
    if archive is None or not accepted:
        raise SystemExit(
            "SROIE is gated (ADR-0005).\n\n"
            "Its license could not be confirmed: the ICDAR Robust Reading\n"
            "Competition site was unreachable and no clear terms were found\n"
            "elsewhere. This tool will not fetch it for you.\n\n"
            "If you have registered with the organizers and accepted their\n"
            "terms, supply the archive yourself:\n\n"
            "  --sroie-archive PATH --accept-sroie-terms\n"
        )
    if not archive.exists():
        raise SystemExit(f"archive not found: {archive}")

    corpus_dir = out_root / "sroie"
    extract_dir = corpus_dir / "extracted"
    corpus_dir.mkdir(parents=True, exist_ok=True)
    if not extract_dir.exists():
        with zipfile.ZipFile(archive) as zf:
            zf.extractall(extract_dir)

    pages: list[Page] = []
    for image_path in sorted(extract_dir.rglob("*.jpg")):
        if limit is not None and len(pages) >= limit:
            break
        entities_path = image_path.with_suffix(".txt")
        fields: list[Field] = []
        if entities_path.exists():
            try:
                entities = json.loads(entities_path.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                entities = {}
            # SROIE task-3 entities are page-level: no boxes are published for
            # them. An empty quad is honest - stratify reports these as
            # provenance-less, which is exactly the weakness that makes SROIE
            # the secondary corpus.
            fields = [Field(label=k, text=str(v), quad=[]) for k, v in entities.items()]
        width, height = _image_size(image_path)
        pages.append(
            Page(
                doc_id=f"sroie-{image_path.stem}",
                corpus="sroie",
                split="all",
                image=str(image_path.relative_to(out_root.parent.parent)),
                width=width,
                height=height,
                fields=fields,
            )
        )
    return pages


# ---------------------------------------------------------------------------- CLI


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("--corpus", choices=["cord", "sroie", "funsd", "all"], required=True)
    ap.add_argument("--limit", type=int, default=None, help="max pages (CORD: 400, FUNSD: 50)")
    ap.add_argument("--out", type=Path, default=DATA_RAW)
    ap.add_argument(
        "--force", action="store_true", help="re-fetch even if the manifest is complete"
    )
    ap.add_argument("--sroie-archive", type=Path, default=None)
    ap.add_argument("--accept-sroie-terms", action="store_true")
    args = ap.parse_args(argv)

    corpora = ["cord", "sroie", "funsd"] if args.corpus == "all" else [args.corpus]
    for corpus in corpora:
        if not args.force and _already_have(corpus, args.limit, args.out):
            print(f"{corpus}: already present, skipping (use --force to refetch)")
            continue

        print(f"{corpus}: fetching...")
        _write_license(corpus, args.out)
        if corpus == "cord":
            pages = fetch_cord(args.out, args.limit)
        elif corpus == "funsd":
            pages = fetch_funsd(args.out, args.limit)
        else:
            pages = fetch_sroie(args.out, args.limit, args.sroie_archive, args.accept_sroie_terms)

        path = write_manifest(corpus, pages, args.out)
        print(f"{corpus}: {len(pages)} pages -> {path}")
        print(f"{corpus}: license recorded at {args.out / corpus / 'LICENSE.txt'}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
