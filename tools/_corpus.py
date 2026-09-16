"""Shared corpus IO for the intake tools.

One manifest format across corpora so `augment.py` and `stratify.py` do not each
learn CORD's, SROIE's and FUNSD's native layouts. `download_corpora.py` is the
only place that knows those.

Manifest: one JSON object per line at `data/raw/{corpus}/manifest.jsonl`:

    {"doc_id", "corpus", "split", "image", "width", "height", "fields": [
        {"label", "text", "quad": [[x,y] x4], "field_class"}
    ]}

Coordinates are absolute pixels in the source image, because that is what every
corpus publishes and converting twice loses precision. The claim schema uses
page-normalized coordinates; conversion happens at the adapter boundary, once.
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent
DATA_RAW = REPO_ROOT / "data" / "raw"
DATA_AUGMENTED = REPO_ROOT / "data" / "augmented"

CORPORA = ("cord", "sroie", "funsd")

Quad = list[list[float]]


@dataclass
class Field:
    label: str
    text: str
    quad: Quad
    field_class: str = "text"

    def axis_aligned(self) -> tuple[float, float, float, float]:
        xs = [p[0] for p in self.quad]
        ys = [p[1] for p in self.quad]
        return min(xs), min(ys), max(xs), max(ys)


@dataclass
class Page:
    doc_id: str
    corpus: str
    split: str
    image: str
    width: int
    height: int
    fields: list[Field] = field(default_factory=list)

    @classmethod
    def from_json(cls, obj: dict[str, Any]) -> Page:
        return cls(
            doc_id=obj["doc_id"],
            corpus=obj["corpus"],
            split=obj.get("split", "unknown"),
            image=obj["image"],
            width=int(obj["width"]),
            height=int(obj["height"]),
            fields=[
                Field(
                    label=f["label"],
                    text=f.get("text", ""),
                    quad=f["quad"],
                    field_class=f.get("field_class", "text"),
                )
                for f in obj.get("fields", [])
            ],
        )

    def to_json(self) -> dict[str, Any]:
        return {
            "doc_id": self.doc_id,
            "corpus": self.corpus,
            "split": self.split,
            "image": self.image,
            "width": self.width,
            "height": self.height,
            "fields": [
                {
                    "label": f.label,
                    "text": f.text,
                    "quad": f.quad,
                    "field_class": f.field_class,
                }
                for f in self.fields
            ],
        }

    def image_path(self) -> Path:
        p = Path(self.image)
        return p if p.is_absolute() else REPO_ROOT / p


def manifest_path(corpus: str, root: Path = DATA_RAW) -> Path:
    return root / corpus / "manifest.jsonl"


def read_manifest(corpus: str, root: Path = DATA_RAW) -> Iterator[Page]:
    path = manifest_path(corpus, root)
    if not path.exists():
        raise FileNotFoundError(
            f"no manifest for {corpus!r} at {path}. Run tools/download_corpora.py first."
        )
    with path.open(encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                yield Page.from_json(json.loads(line))


def write_manifest(corpus: str, pages: list[Page], root: Path = DATA_RAW) -> Path:
    path = manifest_path(corpus, root)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        for page in pages:
            fh.write(json.dumps(page.to_json(), ensure_ascii=False) + "\n")
    return path


def load_field_class_map(schema_path: Path) -> dict[str, str]:
    """Invert a class schema's field_class_map into {label: field_class}.

    Unmapped labels are the caller's problem to report - this returns only what
    the schema states, so a missing label surfaces as 'unmapped' rather than
    being guessed into a class that carries a different consequence.
    """
    import yaml

    schema = yaml.safe_load(schema_path.read_text(encoding="utf-8"))
    out: dict[str, str] = {}
    for field_class, labels in (schema.get("field_class_map") or {}).items():
        for label in labels or []:
            out[label] = field_class
    return out
