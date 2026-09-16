"""Field-claim and provenance models.

The unit of verification is a **field claim**, not a document and not a job
(CLAUDE.md §3 rule 2). A claim is one extracted value together with the evidence
needed to check it without redoing the extraction:

    {value, provenance{type, page, bbox, source_text}, field_class, consequence}

Three properties of these models are load-bearing and should not be relaxed
without an ADR:

1. **Provenance is mandatory** (CLAUDE.md §3 rule 5). There is no way to build a
   claim without saying where the value came from. A provider that emits no
   locations gets grounded against our reference layer; a provider that emits a
   value with no source at all is making an `inferred` claim and is marked as
   such, which is exactly the class of claim the evidence stack should distrust.

2. **A claim is an immutable record of what a provider said.** The models are
   frozen and forbid extra fields. Check results, likelihood ratios, posteriors
   and tier decisions do not accumulate on the claim — they belong in the
   per-field evidence log (CLAUDE.md §3 rule 10), so that what the provider
   returned stays separable from what we concluded about it.

3. **Claims round-trip through JSONL without changing type.** Everything in
   this phase is flat files (CLAUDE.md §3 rule 8), so a claim written to a log
   and read back must be the claim that was written. JSON has no `Decimal` and
   no `date`: both serialize to strings and return as `str`, which would make an
   in-memory run and a replay disagree about what a provider said. So neither is
   accepted as a claim value — money and dates are carried in the provider's own
   string form and parsed by Tier 0, which is a check with a recorded outcome
   rather than a silent conversion. `Decimal` remains the type of our own money
   (consequence values), where the field is not a union and round-trips cleanly.

4. **`value` is stored verbatim, never normalized here.** Tier 0 owns the
   authoritative parse, including "the value must parse from `source_text`
   after normalization", which is one of the sharpest rejecting checks available
   (part-2 §4: it catches "$18,381.16" → 18331.16 with no second engine). If
   this module quietly stripped currency symbols and separators, that check
   would be testing its own normalizer rather than the provider's read.
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class FieldClass(StrEnum):
    """What kind of thing a field is. Drives consequence, thresholds and audit strata."""

    MONEY = "money"
    IDENTIFIER = "identifier"  # PO, invoice #, ticket #, routing #, SCAC, DOT, VIN
    QUANTITY = "quantity"
    DATE = "date"
    PARTY = "party"  # names, addresses
    TEXT = "text"  # descriptions, memos
    LINE_ITEM = "line_item"  # composite row


#: Money, identifier, quantity and date, per CLAUDE.md §4. A customer may mark
#: further fields critical; that is a schema property of the document class, so
#: importance is asked of the claim via :meth:`FieldClaim.is_important`, which
#: takes those extras as an argument rather than hardcoding them here.
IMPORTANT_FIELD_CLASSES: frozenset[FieldClass] = frozenset(
    {FieldClass.MONEY, FieldClass.IDENTIFIER, FieldClass.QUANTITY, FieldClass.DATE}
)


class ProvenanceType(StrEnum):
    """Where a value came from — and therefore which checks can confirm it."""

    LOCATED = "located"
    """Read from a specific region of a specific page. Supports every Tier 1/2
    check: bbox grounding, source_text fuzzy match, independent crop reread."""

    DERIVED = "derived"
    """Computed from other claims by a stated rule (a total from line items, a
    unit conversion). Confirmed by recomputation, which is free; it has no
    single location and must not claim one."""

    INFERRED = "inferred"
    """Concluded from context with no single source region — currency from a
    letterhead, a year from a fiscal period. The weakest class: no locality, no
    invariant, nothing for a crop reread to look at. part-3 §5 notes this is
    also where a hallucinating extractor lands once grounding is enforced, so
    inferred claims on important fields deserve a pessimistic prior."""

    ABSENT = "absent"
    """The field is not present in the document. An assertion about the whole
    page, not about a region, and therefore a recall claim — the one thing
    verification cannot check locally (part-3 §1). Requires stated evidence of
    absence so the assertion is at least falsifiable."""


class BoundingBox(BaseModel):
    """Page-relative box, normalized to [0, 1] with the origin top-left.

    Normalized rather than pixel coordinates so a claim survives re-rendering a
    page at a different DPI — the reference layer, the provider and the crop
    reread rarely agree on raster size.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    x0: float = Field(ge=0.0, le=1.0)
    y0: float = Field(ge=0.0, le=1.0)
    x1: float = Field(ge=0.0, le=1.0)
    y1: float = Field(ge=0.0, le=1.0)

    @model_validator(mode="after")
    def _ordered(self) -> BoundingBox:
        if self.x1 <= self.x0 or self.y1 <= self.y0:
            raise ValueError(
                f"bounding box must have positive area with x0<x1 and y0<y1, got {self!r}"
            )
        return self

    @property
    def width(self) -> float:
        return self.x1 - self.x0

    @property
    def height(self) -> float:
        return self.y1 - self.y0

    @property
    def area(self) -> float:
        return self.width * self.height

    def expanded(self, margin: float) -> BoundingBox:
        """Grow the box by ``margin`` on every side, clamped to the page.

        Tier 2 rereads a crop "plus a small margin" (CLAUDE.md §5): a box tight
        to the glyphs often clips the decimal or the minus sign that the whole
        check is about.
        """
        if margin < 0:
            raise ValueError("margin must be non-negative")
        return BoundingBox(
            x0=max(0.0, self.x0 - margin),
            y0=max(0.0, self.y0 - margin),
            x1=min(1.0, self.x1 + margin),
            y1=min(1.0, self.y1 + margin),
        )


class Provenance(BaseModel):
    """Where a claimed value came from.

    Which fields are required depends on ``type``; the validator enforces it so
    an adapter cannot emit a `located` claim with no location, which would make
    the claim look checkable when it is not.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    type: ProvenanceType

    page: int | None = Field(default=None, ge=1, description="1-indexed page number")
    bbox: BoundingBox | None = None
    source_text: str | None = Field(
        default=None,
        description=(
            "The text the provider says it read, verbatim, before any parsing. "
            "Tier 0 checks that `value` parses from this; Tier 1 checks that this "
            "matches the reference layer's words at `bbox`."
        ),
    )

    derivation: str | None = Field(
        default=None,
        description="DERIVED only: the rule, e.g. 'subtotal + tax + freight'.",
    )
    inputs: tuple[str, ...] = Field(
        default=(),
        description="DERIVED only: claim_ids this value was computed from.",
    )
    basis: str | None = Field(
        default=None,
        description="INFERRED only: what the inference rests on, in words.",
    )
    absence_evidence: str | None = Field(
        default=None,
        description=(
            "ABSENT only: what was searched and not found, e.g. 'no PO label in "
            "reference layer on any page'. Without it the claim is unfalsifiable."
        ),
    )

    @model_validator(mode="after")
    def _consistent_with_type(self) -> Provenance:
        t = self.type

        if t is ProvenanceType.LOCATED:
            missing = [
                name
                for name, val in (
                    ("page", self.page),
                    ("bbox", self.bbox),
                    ("source_text", self.source_text),
                )
                if val is None
            ]
            if missing:
                raise ValueError(
                    f"located provenance requires {', '.join(missing)}; "
                    "a value with no location is inferred, not located"
                )
            if self.derivation or self.basis or self.absence_evidence:
                raise ValueError(
                    "located provenance must not carry derivation, basis or absence_evidence"
                )

        elif t is ProvenanceType.DERIVED:
            if not self.derivation:
                raise ValueError("derived provenance requires a derivation rule")
            if self.bbox is not None:
                raise ValueError(
                    "derived provenance must not claim a bbox; a computed value has no "
                    "single location, and asserting one would let Tier 1 grounding "
                    "'confirm' arithmetic it never checked"
                )
            if self.basis or self.absence_evidence:
                raise ValueError("derived provenance must not carry basis or absence_evidence")

        elif t is ProvenanceType.INFERRED:
            if not self.basis:
                raise ValueError("inferred provenance requires a stated basis")
            if self.bbox is not None:
                raise ValueError(
                    "inferred provenance must not claim a bbox; if the value can be "
                    "pointed at, it is located"
                )
            if self.derivation or self.absence_evidence:
                raise ValueError(
                    "inferred provenance must not carry derivation or absence_evidence"
                )

        elif t is ProvenanceType.ABSENT:
            if not self.absence_evidence:
                raise ValueError(
                    "absent provenance requires absence_evidence; an unexplained null is "
                    "indistinguishable from a recall failure"
                )
            if self.bbox is not None or self.source_text is not None:
                raise ValueError("absent provenance must not carry a bbox or source_text")
            if self.derivation or self.basis:
                raise ValueError("absent provenance must not carry derivation or basis")

        if self.inputs and t is not ProvenanceType.DERIVED:
            raise ValueError("only derived provenance may list input claims")

        return self

    @classmethod
    def located(cls, *, page: int, bbox: BoundingBox, source_text: str) -> Provenance:
        return cls(type=ProvenanceType.LOCATED, page=page, bbox=bbox, source_text=source_text)

    @classmethod
    def derived(
        cls, *, derivation: str, inputs: tuple[str, ...] = (), page: int | None = None
    ) -> Provenance:
        return cls(type=ProvenanceType.DERIVED, derivation=derivation, inputs=inputs, page=page)

    @classmethod
    def inferred(cls, *, basis: str, page: int | None = None) -> Provenance:
        return cls(type=ProvenanceType.INFERRED, basis=basis, page=page)

    @classmethod
    def absent(cls, *, absence_evidence: str) -> Provenance:
        return cls(type=ProvenanceType.ABSENT, absence_evidence=absence_evidence)

    @property
    def is_checkable_locally(self) -> bool:
        """True when Tier 1/2 checks have a region to inspect.

        Derived values are checkable, but by recomputation rather than by
        looking; inferred and absent values are neither.
        """
        return self.type is ProvenanceType.LOCATED


class ConsequenceMode(StrEnum):
    VALUE_MULTIPLIER = "value_multiplier"
    """Money fields: the consequence scales with the amount at risk."""

    POLICY_CONSTANT = "policy_constant"
    """Identifiers and the rest: a flat customer-assigned cost."""


class Consequence(BaseModel):
    """The customer-assigned cost of an undetected error on this field.

    This is the term that decides how deep the evidence stack goes. The stopping
    rule (CLAUDE.md §5) passes a field when::

        P(wrong) × consequence < cost(next cheapest check that could change the decision)

    so a $12 freight charge stops at Tier 0 while a $250,000 total keeps climbing.
    Consequence values come from the document source, not from us
    (``config/consequences.yaml``); ``source`` records who set them, because a
    number we invented and a number the customer gave us support very different
    claims in a report.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    mode: ConsequenceMode
    usd: Decimal | None = Field(
        default=None, ge=0, description="POLICY_CONSTANT only: flat cost in USD."
    )
    multiplier: Decimal | None = Field(
        default=None, ge=0, description="VALUE_MULTIPLIER only: cost = value × multiplier."
    )
    source: str = Field(
        description="Who assigned this, e.g. 'customer:elko-contractor' or 'default'."
    )

    @model_validator(mode="after")
    def _mode_fields(self) -> Consequence:
        if self.mode is ConsequenceMode.POLICY_CONSTANT:
            if self.usd is None:
                raise ValueError("policy_constant consequence requires usd")
            if self.multiplier is not None:
                raise ValueError("policy_constant consequence must not set multiplier")
        else:
            if self.multiplier is None:
                raise ValueError("value_multiplier consequence requires multiplier")
            if self.usd is not None:
                raise ValueError("value_multiplier consequence must not set usd")
        return self

    def amount_usd(self, value: Decimal | int | None = None) -> Decimal:
        """Resolve to dollars.

        ``value`` is required for VALUE_MULTIPLIER and must already be numeric —
        this module does not parse money out of provider strings (see the module
        docstring); Tier 0 does, and it is a check with a recorded outcome, not a
        silent conversion.
        """
        if self.mode is ConsequenceMode.POLICY_CONSTANT:
            assert self.usd is not None  # guaranteed by the validator
            return self.usd

        if value is None:
            raise ValueError(
                "value_multiplier consequence needs the field's numeric value; pass the "
                "Tier 0 parse result, do not parse here"
            )
        if isinstance(value, bool) or not isinstance(value, (Decimal, int)):
            raise TypeError(
                f"value must be Decimal or int, got {type(value).__name__}; a money value "
                "still held as a string has not been parsed by Tier 0 yet"
            )
        assert self.multiplier is not None  # guaranteed by the validator
        return Decimal(value) * self.multiplier


#: What a provider may claim. Stored verbatim; no coercion (see module docstring).
#: ``list``/``dict`` carry composite LINE_ITEM rows. Deliberately excludes
#: ``Decimal`` and ``date``: neither survives a JSONL round-trip as itself, and a
#: claim that changes type when replayed from a log is not a record of anything.
ClaimValue = bool | int | float | str | list[Any] | dict[str, Any] | None


class FieldClaim(BaseModel):
    """One extracted value, with where it came from and what it costs to get wrong."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    claim_id: str = Field(
        min_length=1,
        description="Unique within an extraction; referenced by evidence logs and by "
        "derived claims' inputs.",
    )
    field_name: str = Field(
        min_length=1, description="Key in the document class's schema, e.g. 'invoice_total'."
    )
    field_class: FieldClass
    value: ClaimValue = None
    provenance: Provenance
    consequence: Consequence | None = Field(
        default=None,
        description=(
            "Attached from config/consequences.yaml once the source has assigned values. "
            "Optional at extraction time; required before the stopping rule can run."
        ),
    )

    @field_validator("value", mode="before")
    @classmethod
    def _json_native(cls, v: Any) -> Any:
        """Reject values that cannot survive a JSONL round-trip as themselves."""
        if isinstance(v, Decimal):
            raise ValueError(
                "Decimal is not a claim value: it serializes to a JSON string and returns "
                "as str, so a replayed log would disagree with the run. Carry the "
                "provider's text (str) and let Tier 0 parse it"
            )
        if isinstance(v, (date, datetime)):
            raise ValueError(
                "date/datetime is not a claim value: JSON has no such type. Carry the "
                "provider's text (e.g. '2026-07-14') and let Tier 0 parse and sanity-check it"
            )
        if isinstance(v, float):
            if v != v:
                raise ValueError("NaN is not a claim; use None with absent provenance")
            if v in (float("inf"), float("-inf")):
                raise ValueError("infinity is not a claim value")
        return v

    @model_validator(mode="after")
    def _value_matches_provenance(self) -> FieldClaim:
        absent = self.provenance.type is ProvenanceType.ABSENT

        if absent and self.value is not None:
            raise ValueError("absent provenance requires a null value")
        if self.value is None and not absent:
            raise ValueError(
                "a null value must carry absent provenance with stated evidence; an "
                "unexplained null hides a recall failure as a successful read"
            )

        if self.field_class is FieldClass.MONEY and isinstance(self.value, float):
            raise ValueError(
                "money must not be stored as a binary float: 0.1 has no exact "
                "representation, so the amount logged is not the amount read. Adapters "
                "keep the provider's text (parse JSON with parse_float=str)"
            )

        if self.field_class is FieldClass.LINE_ITEM and not absent:
            if not isinstance(self.value, (list, dict)):
                raise ValueError(
                    f"line_item value must be a list or dict, got {type(self.value).__name__}"
                )

        if self.consequence is not None:
            if (
                self.consequence.mode is ConsequenceMode.VALUE_MULTIPLIER
                and self.field_class is not FieldClass.MONEY
            ):
                raise ValueError(
                    "value_multiplier consequence only applies to money fields; other "
                    "classes take a policy constant"
                )

        return self

    def is_important(self, critical_fields: frozenset[str] | set[str] = frozenset()) -> bool:
        """Important fields are money, identifier, quantity, date, plus any the
        customer marked critical for this document class (CLAUDE.md §4)."""
        return self.field_class in IMPORTANT_FIELD_CLASSES or self.field_name in critical_fields

    def consequence_usd(self, parsed_value: Decimal | int | None = None) -> Decimal:
        """Dollars at risk if this field is wrong and nobody catches it.

        Raises when no consequence is attached: running the stopping rule against
        a default would silently decide how much evidence a field deserves, which
        is the customer's call.
        """
        if self.consequence is None:
            raise ValueError(
                f"no consequence attached to claim {self.claim_id!r} ({self.field_name}); "
                "load config/consequences.yaml before running the stopping rule"
            )
        if (
            self.consequence.mode is ConsequenceMode.VALUE_MULTIPLIER
            and parsed_value is None
            and isinstance(self.value, (Decimal, int))
            and not isinstance(self.value, bool)
        ):
            parsed_value = self.value
        return self.consequence.amount_usd(parsed_value)


class ExtractionResult(BaseModel):
    """Everything one provider claimed about one document, in the common schema.

    Adapters return this; nothing downstream sees a provider's native format.
    ``provider_epoch`` is carried from the start even though epochs are not
    detected during the experiment (CLAUDE.md §4) — a residual number whose epoch
    was never recorded cannot be published later, and backfilling it is guesswork.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    document_id: str = Field(min_length=1)
    document_class: str = Field(
        min_length=1, description="Key into config/schemas/, e.g. 'construction_delivery_ticket'."
    )
    provider_id: str = Field(min_length=1, description="Key into config/providers.yaml.")
    provider_epoch: str | None = None
    schema_version: str = Field(min_length=1)
    claims: tuple[FieldClaim, ...] = ()

    @model_validator(mode="after")
    def _unique_claim_ids(self) -> ExtractionResult:
        seen: set[str] = set()
        for claim in self.claims:
            if claim.claim_id in seen:
                raise ValueError(f"duplicate claim_id {claim.claim_id!r} in {self.document_id!r}")
            seen.add(claim.claim_id)
        return self

    def by_name(self, field_name: str) -> tuple[FieldClaim, ...]:
        """All claims for a field. Plural: a value appearing in several places is
        several claims, and their agreement is itself Tier 1 evidence."""
        return tuple(c for c in self.claims if c.field_name == field_name)

    def important_claims(
        self, critical_fields: frozenset[str] | set[str] = frozenset()
    ) -> tuple[FieldClaim, ...]:
        return tuple(c for c in self.claims if c.is_important(critical_fields))
