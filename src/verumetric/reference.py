"""Reference OCR layer and provenance grounding.

The reference layer is one cheap word-box OCR pass per page that we own
(ADR-0006). Grounding matches a provider's `source_text` against the words this
layer read, at the location the provider claimed.

Why this is the load-bearing check: an extractor that invents a value must also
invent a plausible source text and a plausible location for it. Grounding is the
one check a worker cannot satisfy without having actually read the document
(part-3 §8 item 7), which is why the layer stays ours, local, and out of every
extraction arm.

What grounding returns is **evidence, not a verdict**. A high score raises
P(correct); a low score raises risk and sends the field up the ladder. Nothing
here decides a field on its own, and nothing here votes.

Normalization note: matching is done on normalized text, but the provider's
`value` and `source_text` are never mutated. Tier 0 owns the authoritative
parse; this module only decides whether two strings are plausibly the same
reading of the same pixels.
"""

from __future__ import annotations

import json
import re
import unicodedata
from dataclasses import dataclass, field
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any, Protocol, runtime_checkable

from verumetric.schema import BoundingBox

# Characters OCR engines routinely disagree about on receipts and tickets, where
# the disagreement is cosmetic rather than a different reading.
_PUNCT = re.compile(r"[\s,.;:_\-–—'\"`´()\[\]{}|\\/*#]+")
_CURRENCY = re.compile(
    # Standalone codes, and codes written flush against the amount ("Rp66.000"),
    # which is how they actually appear on the receipts in this corpus.
    r"[$€£¥₩₹]|\b(?:rp|idr|usd|myr|sgd|eur|gbp)\b|\b(?:rp|idr|usd|myr)(?=\s*\d)",
    re.IGNORECASE,
)


def normalize(text: str) -> str:
    """Fold a string to its comparable core.

    Deliberately conservative: it removes separators, currency marks and case,
    and nothing else. It does NOT fold O/0 or l/1 — those are exactly the
    confusions the evidence stack exists to catch, and folding them here would
    hide a misread behind a perfect grounding score.
    """
    text = unicodedata.normalize("NFKC", text)
    text = _CURRENCY.sub("", text)
    text = _PUNCT.sub("", text)
    return text.casefold()


def similarity(a: str, b: str) -> float:
    """1.0 for identical normalized strings, 0.0 for nothing in common."""
    na, nb = normalize(a), normalize(b)
    if not na and not nb:
        return 1.0
    if not na or not nb:
        return 0.0
    if na == nb:
        return 1.0
    return SequenceMatcher(None, na, nb).ratio()


@dataclass(frozen=True)
class ReferenceWord:
    """One word the reference engine read, with a page-normalized box."""

    text: str
    bbox: BoundingBox
    confidence: float | None = None

    @property
    def center_y(self) -> float:
        return (self.bbox.y0 + self.bbox.y1) / 2.0


@dataclass(frozen=True)
class GroundingResult:
    """Evidence about whether a claimed reading is present where it was claimed.

    - `score`: text similarity of the best matching span, 0..1.
    - `bbox`: where that span actually is, per the reference layer.
    - `location_agrees`: whether the provider's claimed box overlaps the span it
      matched. A high score with `location_agrees=False` is the interesting
      case — the right value found in the wrong place (part-2 §5's
      "right-value-wrong-location" failure class).
    - `iou`: overlap between the claimed box and the matched span, when a claim
      was supplied.
    """

    score: float
    bbox: BoundingBox | None
    matched_text: str
    word_indices: tuple[int, ...] = ()
    location_agrees: bool | None = None
    iou: float | None = None

    @property
    def found(self) -> bool:
        return self.bbox is not None


@dataclass(frozen=True)
class ReferenceLayer:
    """Everything the reference engine read from one page."""

    doc_id: str
    page: int
    width: int
    height: int
    words: tuple[ReferenceWord, ...] = ()
    engine: str = "unknown"
    engine_version: str = "unknown"

    # --- structure -------------------------------------------------------

    def lines(self, y_tolerance: float = 0.006) -> list[list[int]]:
        """Group word indices into reading-order lines by vertical overlap.

        Needed for the recall problem: when reconciliation fails because a line
        item is missing, the structural row count says which region the
        extractor skipped, so Tier 4 reprocesses that region rather than the
        page (part-3 §3).
        """
        order = sorted(
            range(len(self.words)), key=lambda i: (self.words[i].center_y, self.words[i].bbox.x0)
        )
        out: list[list[int]] = []
        for i in order:
            w = self.words[i]
            placed = False
            for line in out:
                if abs(self.words[line[0]].center_y - w.center_y) <= y_tolerance:
                    line.append(i)
                    placed = True
                    break
            if not placed:
                out.append([i])
        for line in out:
            line.sort(key=lambda i: self.words[i].bbox.x0)
        return out

    def words_in(self, box: BoundingBox, min_overlap: float = 0.3) -> list[int]:
        """Indices of words whose area overlaps `box` by at least `min_overlap`."""
        hits = []
        for i, w in enumerate(self.words):
            inter = _intersection_area(w.bbox, box)
            if w.bbox.area > 0 and inter / w.bbox.area >= min_overlap:
                hits.append(i)
        return hits

    # --- persistence -----------------------------------------------------

    def to_json(self) -> dict[str, Any]:
        return {
            "doc_id": self.doc_id,
            "page": self.page,
            "width": self.width,
            "height": self.height,
            "engine": self.engine,
            "engine_version": self.engine_version,
            "words": [
                {
                    "text": w.text,
                    "bbox": [w.bbox.x0, w.bbox.y0, w.bbox.x1, w.bbox.y1],
                    "confidence": w.confidence,
                }
                for w in self.words
            ],
        }

    @classmethod
    def from_json(cls, obj: dict[str, Any]) -> ReferenceLayer:
        return cls(
            doc_id=obj["doc_id"],
            page=int(obj.get("page", 1)),
            width=int(obj["width"]),
            height=int(obj["height"]),
            engine=obj.get("engine", "unknown"),
            engine_version=obj.get("engine_version", "unknown"),
            words=tuple(
                ReferenceWord(
                    text=w["text"],
                    bbox=BoundingBox(
                        x0=w["bbox"][0], y0=w["bbox"][1], x1=w["bbox"][2], y1=w["bbox"][3]
                    ),
                    confidence=w.get("confidence"),
                )
                for w in obj.get("words", [])
            ),
        )

    def save(self, path: Path) -> Path:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(self.to_json(), ensure_ascii=False), encoding="utf-8")
        return path

    @classmethod
    def load(cls, path: Path) -> ReferenceLayer:
        return cls.from_json(json.loads(path.read_text(encoding="utf-8")))


# --- geometry ---------------------------------------------------------------


def _intersection_area(a: BoundingBox, b: BoundingBox) -> float:
    x0, y0 = max(a.x0, b.x0), max(a.y0, b.y0)
    x1, y1 = min(a.x1, b.x1), min(a.y1, b.y1)
    if x1 <= x0 or y1 <= y0:
        return 0.0
    return (x1 - x0) * (y1 - y0)


def iou(a: BoundingBox, b: BoundingBox) -> float:
    inter = _intersection_area(a, b)
    union = a.area + b.area - inter
    return inter / union if union > 0 else 0.0


def _hull(boxes: list[BoundingBox]) -> BoundingBox:
    return BoundingBox(
        x0=min(b.x0 for b in boxes),
        y0=min(b.y0 for b in boxes),
        x1=max(b.x1 for b in boxes),
        y1=max(b.y1 for b in boxes),
    )


# --- grounding --------------------------------------------------------------


def ground(
    source_text: str,
    layer: ReferenceLayer,
    claimed_bbox: BoundingBox | None = None,
    *,
    max_span: int = 8,
    location_iou_threshold: float = 0.1,
) -> GroundingResult:
    """Find `source_text` in the reference layer; report where and how well.

    Searches spans of consecutive words within each detected line, scoring each
    by normalized similarity, and returns the best. `max_span` bounds the number
    of words a single field may span — without it, a long enough window matches
    anything by accumulating characters.

    When `claimed_bbox` is given, the result also reports whether the claimed
    location overlaps what was actually matched. The two signals stay separate on
    purpose: "the text is on this page" and "the text is where you said" are
    different pieces of evidence, and collapsing them would hide the
    right-value-wrong-location failure class entirely.
    """
    if not source_text.strip() or not layer.words:
        return GroundingResult(score=0.0, bbox=None, matched_text="")

    best_score = 0.0
    best_indices: tuple[int, ...] = ()
    best_text = ""

    for line in layer.lines():
        for start in range(len(line)):
            for length in range(1, min(max_span, len(line) - start) + 1):
                indices = tuple(line[start : start + length])
                candidate = " ".join(layer.words[i].text for i in indices)
                score = similarity(source_text, candidate)
                if score > best_score:
                    best_score, best_indices, best_text = score, indices, candidate
                    if score == 1.0:
                        break
            if best_score == 1.0:
                break
        if best_score == 1.0:
            break

    if not best_indices:
        return GroundingResult(score=0.0, bbox=None, matched_text="")

    bbox = _hull([layer.words[i].bbox for i in best_indices])
    overlap = iou(claimed_bbox, bbox) if claimed_bbox is not None else None
    agrees = None if overlap is None else overlap >= location_iou_threshold

    return GroundingResult(
        score=best_score,
        bbox=bbox,
        matched_text=best_text,
        word_indices=best_indices,
        location_agrees=agrees,
        iou=overlap,
    )


def read_region(layer: ReferenceLayer, box: BoundingBox, min_overlap: float = 0.3) -> str:
    """What the reference layer itself read inside a region.

    This is the second half of Tier 1: not "is the provider's text here" but
    "what do we independently read here". A disagreement between this and the
    provider's value is evidence; it is not a decision.
    """
    indices = layer.words_in(box, min_overlap)
    indices.sort(key=lambda i: (layer.words[i].center_y, layer.words[i].bbox.x0))
    return " ".join(layer.words[i].text for i in indices)


# --- engines ----------------------------------------------------------------


@runtime_checkable
class ReferenceEngine(Protocol):
    """A word-box OCR engine. Adapters are thin; the evidence logic is above."""

    name: str
    version: str

    def read(self, image_path: Path, doc_id: str, page: int = 1) -> ReferenceLayer: ...


@dataclass
class PaddleOCREngine:
    """PaddleOCR, local (ADR-0006). Reference-only — never an extraction arm."""

    lang: str = "en"
    name: str = "paddleocr"
    version: str = "unknown"
    _ocr: Any = field(default=None, repr=False)

    def _engine(self):
        if self._ocr is None:
            try:
                from paddleocr import PaddleOCR
            except ImportError as exc:  # pragma: no cover - environment-dependent
                raise RuntimeError(
                    "PaddleOCR is not installed. Install it, or use TesseractEngine "
                    "(ADR-0006 fallback). The grounding logic needs neither."
                ) from exc
            self._ocr = PaddleOCR(use_angle_cls=True, lang=self.lang, show_log=False)
            try:
                import paddleocr as _p

                self.version = getattr(_p, "__version__", "unknown")
            except Exception:  # pragma: no cover
                pass
        return self._ocr

    def read(self, image_path: Path, doc_id: str, page: int = 1) -> ReferenceLayer:
        from PIL import Image

        with Image.open(image_path) as im:
            width, height = im.width, im.height

        raw = self._engine().ocr(str(image_path), cls=True)
        words: list[ReferenceWord] = []
        for block in raw or []:
            for entry in block or []:
                quad, (text, conf) = entry[0], entry[1]
                xs = [p[0] for p in quad]
                ys = [p[1] for p in quad]
                words.append(
                    ReferenceWord(
                        text=str(text),
                        bbox=_normalized_box(min(xs), min(ys), max(xs), max(ys), width, height),
                        confidence=float(conf),
                    )
                )
        return ReferenceLayer(
            doc_id=doc_id,
            page=page,
            width=width,
            height=height,
            words=tuple(words),
            engine=self.name,
            engine_version=self.version,
        )


@dataclass
class TesseractEngine:
    """Tesseract TSV fallback (ADR-0006). Weaker on photographed pages."""

    lang: str = "eng"
    name: str = "tesseract"
    version: str = "unknown"

    def read(self, image_path: Path, doc_id: str, page: int = 1) -> ReferenceLayer:
        import csv
        import subprocess

        from PIL import Image

        with Image.open(image_path) as im:
            width, height = im.width, im.height

        proc = subprocess.run(
            ["tesseract", str(image_path), "stdout", "-l", self.lang, "tsv"],
            capture_output=True,
            text=True,
            check=True,
        )
        words: list[ReferenceWord] = []
        for row in csv.DictReader(proc.stdout.splitlines(), delimiter="\t"):
            text = (row.get("text") or "").strip()
            if not text:
                continue
            try:
                left, top = float(row["left"]), float(row["top"])
                w, h = float(row["width"]), float(row["height"])
                conf = float(row.get("conf", -1))
            except (KeyError, ValueError):
                continue
            if w <= 0 or h <= 0:
                continue
            words.append(
                ReferenceWord(
                    text=text,
                    bbox=_normalized_box(left, top, left + w, top + h, width, height),
                    confidence=conf / 100.0 if conf >= 0 else None,
                )
            )
        return ReferenceLayer(
            doc_id=doc_id,
            page=page,
            width=width,
            height=height,
            words=tuple(words),
            engine=self.name,
            engine_version=self.version,
        )


def _normalized_box(
    x0: float, y0: float, x1: float, y1: float, width: int, height: int
) -> BoundingBox:
    """Pixels -> page-normalized, clamped, with a minimum positive area.

    Engines occasionally emit a zero-width box for a single character; the claim
    schema requires positive area, so a degenerate box is widened by one pixel
    rather than dropped. Losing the word would silently remove evidence.
    """
    eps = 1.0
    if x1 <= x0:
        x1 = x0 + eps
    if y1 <= y0:
        y1 = y0 + eps
    return BoundingBox(
        x0=max(0.0, min(1.0, x0 / width)),
        y0=max(0.0, min(1.0, y0 / height)),
        x1=max(0.0, min(1.0, x1 / width)),
        y1=max(0.0, min(1.0, y1 / height)),
    )
