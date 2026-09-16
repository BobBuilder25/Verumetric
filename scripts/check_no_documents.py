#!/usr/bin/env python3
"""Refuse to commit document content.

Customer paper — tickets, invoices, POs, scans, photographs, gold sets,
extraction outputs, master-data exports — never enters git history. Once a page
of someone's paper is committed it is in every clone forever, and no .gitignore
added later removes it.

The guard runs on staged content, not on the working tree, so a file that is
gitignored but force-added is still caught. It checks three things:

1. Path prefix   — anything under a data tree (data/, gold/, ...).
2. Extension     — document, image and tabular-export extensions.
3. Magic bytes   — the staged blob itself, so `notes.md` holding a PDF is caught.

Escape hatch: add a glob to .documentguard-allow, with a comment saying why.
`--no-verify` is not the escape hatch; it skips the check for everyone.

Usage:
    check_no_documents.py           # staged files (pre-commit hook)
    check_no_documents.py --all     # every tracked file (CI)
    check_no_documents.py PATH...   # explicit paths
"""

from __future__ import annotations

import fnmatch
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
ALLOWLIST_FILE = REPO_ROOT / ".documentguard-allow"

# Directories that only ever hold customer content or run artifacts.
BLOCKED_PREFIXES = (
    "data/",
    "documents/",
    "gold/",
    "samples/",
    "runs/",
    "out/",
    "results/",
)

# Document, image and tabular-export extensions.
BLOCKED_SUFFIXES = {
    # page images and scans
    ".pdf", ".png", ".jpg", ".jpeg", ".tif", ".tiff", ".bmp", ".gif",
    ".webp", ".heic", ".heif", ".jp2", ".pnm", ".ppm",
    # office documents
    ".doc", ".docx", ".xls", ".xlsx", ".xlsm", ".ppt", ".pptx", ".odt", ".ods",
    # tabular exports (master data, extraction dumps, gold sheets)
    ".csv", ".tsv", ".parquet", ".arrow", ".feather",
    # archives, which hide all of the above
    ".zip", ".tar", ".gz", ".tgz", ".bz2", ".7z", ".rar",
}

# (magic bytes, human name). Checked against the staged blob.
MAGIC = (
    (b"%PDF-", "PDF"),
    (b"\x89PNG\r\n\x1a\n", "PNG image"),
    (b"\xff\xd8\xff", "JPEG image"),
    (b"GIF87a", "GIF image"),
    (b"GIF89a", "GIF image"),
    (b"II*\x00", "TIFF image"),
    (b"MM\x00*", "TIFF image"),
    (b"BM", "BMP image"),
    (b"PK\x03\x04", "zip archive or OOXML document"),
    (b"\xd0\xcf\x11\xe0", "legacy Office document"),
    (b"\x1f\x8b", "gzip archive"),
)


def _git(*args: str) -> bytes:
    return subprocess.run(
        ["git", *args], cwd=REPO_ROOT, capture_output=True, check=True
    ).stdout


def load_allowlist() -> list[str]:
    if not ALLOWLIST_FILE.exists():
        return []
    patterns = []
    for line in ALLOWLIST_FILE.read_text(encoding="utf-8").splitlines():
        line = line.split("#", 1)[0].strip()
        if line:
            patterns.append(line)
    return patterns


def staged_paths() -> list[str]:
    out = _git("diff", "--cached", "--name-only", "--diff-filter=ACM", "-z")
    return [p for p in out.decode("utf-8").split("\0") if p]


def tracked_paths() -> list[str]:
    out = _git("ls-files", "-z")
    return [p for p in out.decode("utf-8").split("\0") if p]


def content_of(path: str, staged: bool) -> bytes:
    """First bytes of the blob that would be committed."""
    if staged:
        try:
            return _git("show", f":{path}")[:512]
        except subprocess.CalledProcessError:
            return b""
    f = REPO_ROOT / path
    if not f.is_file():
        return b""
    with f.open("rb") as fh:
        return fh.read(512)


def reason_blocked(path: str, staged: bool) -> str | None:
    lowered = path.lower()

    for prefix in BLOCKED_PREFIXES:
        if lowered.startswith(prefix):
            return f"lives under {prefix} (customer content or run artifacts)"

    suffix = Path(lowered).suffix
    if suffix in BLOCKED_SUFFIXES:
        return f"has a document/data extension ({suffix})"

    head = content_of(path, staged)
    for magic, name in MAGIC:
        if head.startswith(magic):
            return f"contains {name} content regardless of its filename"

    if b"\x00" in head:
        return "is a binary file"

    return None


def main(argv: list[str]) -> int:
    explicit = [a for a in argv if not a.startswith("-")]
    check_all = "--all" in argv

    if explicit:
        paths, staged = explicit, False
    elif check_all:
        paths, staged = tracked_paths(), False
    else:
        paths, staged = staged_paths(), True

    allowlist = load_allowlist()
    violations: list[tuple[str, str]] = []

    for path in paths:
        if any(fnmatch.fnmatch(path, pattern) for pattern in allowlist):
            continue
        reason = reason_blocked(path, staged)
        if reason:
            violations.append((path, reason))

    if not violations:
        return 0

    print("\nBLOCKED: document content must not be committed.\n", file=sys.stderr)
    for path, reason in violations:
        print(f"  {path}\n      {reason}", file=sys.stderr)
    print(
        "\nCustomer paper, gold sets, extraction outputs and master-data exports\n"
        "belong outside the repository. Keep them under data/, which is ignored.\n"
        "\nIf a file is genuinely not document content (a diagram, a fixture),\n"
        f"add a glob to {ALLOWLIST_FILE.name} with a comment saying why.\n"
        "Do not use --no-verify; it disables this check for everyone.\n",
        file=sys.stderr,
    )
    return 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
