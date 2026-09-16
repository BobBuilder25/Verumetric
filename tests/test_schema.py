"""Unit tests for the field-claim and provenance models.

All values below are SYNTHETIC. No real customer document has been seen by this
repository. The numbers are chosen to exercise validation rules, not to
represent any contractor's, supplier's or carrier's paper.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest
from pydantic import ValidationError

from verumetric.schema import (
    IMPORTANT_FIELD_CLASSES,
    BoundingBox,
    ClaimValue,  # noqa: F401  (imported to assert the alias is exported)
    Consequence,
    ConsequenceMode,
    ExtractionResult,
    FieldClaim,
    FieldClass,
    Provenance,
    ProvenanceType,
)

# --- SYNTHETIC fixtures -----------------------------------------------------

BBOX = BoundingBox(x0=0.55, y0=0.80, x1=0.72, y1=0.84)
LOCATED = Provenance.located(page=3, bbox=BBOX, source_text="$18,381.16")  # SYNTHETIC


def money_claim(**overrides) -> FieldClaim:
    """A SYNTHETIC located money claim."""
    kwargs = dict(
        claim_id="c1",
        field_name="invoice_total",
        field_class=FieldClass.MONEY,
        value="18381.16",  # provider text; Tier 0 owns the parse
        provenance=LOCATED,
    )
    kwargs.update(overrides)
    return FieldClaim(**kwargs)


# --- BoundingBox ------------------------------------------------------------


def test_bbox_geometry():
    assert BBOX.width == pytest.approx(0.17)
    assert BBOX.height == pytest.approx(0.04)
    assert BBOX.area == pytest.approx(0.17 * 0.04)


@pytest.mark.parametrize(
    "coords",
    [
        dict(x0=0.7, y0=0.1, x1=0.2, y1=0.2),  # x reversed
        dict(x0=0.1, y0=0.5, x1=0.2, y1=0.4),  # y reversed
        dict(x0=0.1, y0=0.1, x1=0.1, y1=0.2),  # zero width
    ],
)
def test_bbox_rejects_non_positive_area(coords):
    with pytest.raises(ValidationError, match="positive area"):
        BoundingBox(**coords)


def test_bbox_rejects_out_of_page_coordinates():
    with pytest.raises(ValidationError):
        BoundingBox(x0=0.1, y0=0.1, x1=1.4, y1=0.2)


def test_bbox_expanded_clamps_to_page():
    grown = BoundingBox(x0=0.01, y0=0.01, x1=0.2, y1=0.2).expanded(0.05)
    assert (grown.x0, grown.y0) == (0.0, 0.0)
    assert grown.x1 == pytest.approx(0.25)


def test_bbox_expanded_rejects_negative_margin():
    with pytest.raises(ValueError, match="non-negative"):
        BBOX.expanded(-0.01)


def test_bbox_is_frozen():
    with pytest.raises(ValidationError):
        BBOX.x0 = 0.2


# --- Provenance: one rule per type -----------------------------------------


def test_located_requires_page_bbox_and_source_text():
    with pytest.raises(ValidationError, match="located provenance requires"):
        Provenance(type=ProvenanceType.LOCATED, page=1, source_text="x")
    with pytest.raises(ValidationError, match="located provenance requires"):
        Provenance(type=ProvenanceType.LOCATED, page=1, bbox=BBOX)


def test_located_rejects_page_zero():
    with pytest.raises(ValidationError):
        Provenance(type=ProvenanceType.LOCATED, page=0, bbox=BBOX, source_text="x")


def test_derived_requires_a_rule_and_forbids_a_bbox():
    with pytest.raises(ValidationError, match="requires a derivation rule"):
        Provenance(type=ProvenanceType.DERIVED)
    with pytest.raises(ValidationError, match="must not claim a bbox"):
        Provenance(type=ProvenanceType.DERIVED, derivation="a + b", bbox=BBOX)


def test_derived_carries_input_claims():
    p = Provenance.derived(derivation="subtotal + tax + freight", inputs=("c2", "c3", "c4"))
    assert p.inputs == ("c2", "c3", "c4")


def test_only_derived_may_list_inputs():
    with pytest.raises(ValidationError, match="only derived provenance"):
        Provenance(
            type=ProvenanceType.LOCATED,
            page=1,
            bbox=BBOX,
            source_text="x",
            inputs=("c2",),
        )


def test_inferred_requires_basis_and_forbids_location():
    with pytest.raises(ValidationError, match="requires a stated basis"):
        Provenance(type=ProvenanceType.INFERRED)
    with pytest.raises(ValidationError, match="if the value can be pointed at"):
        Provenance(type=ProvenanceType.INFERRED, basis="letterhead currency", bbox=BBOX)


def test_absent_requires_evidence_and_forbids_location():
    with pytest.raises(ValidationError, match="requires absence_evidence"):
        Provenance(type=ProvenanceType.ABSENT)
    with pytest.raises(ValidationError, match="must not carry a bbox or source_text"):
        Provenance(
            type=ProvenanceType.ABSENT,
            absence_evidence="no PO label found",
            source_text="PO",
        )


def test_located_rejects_foreign_fields():
    with pytest.raises(ValidationError, match="must not carry derivation"):
        Provenance(
            type=ProvenanceType.LOCATED,
            page=1,
            bbox=BBOX,
            source_text="x",
            derivation="a + b",
        )


def test_provenance_forbids_unknown_fields():
    with pytest.raises(ValidationError):
        Provenance(type=ProvenanceType.INFERRED, basis="context", confidence=0.9)


def test_only_located_is_locally_checkable():
    assert LOCATED.is_checkable_locally is True
    assert Provenance.derived(derivation="a + b").is_checkable_locally is False
    assert Provenance.inferred(basis="letterhead").is_checkable_locally is False
    assert Provenance.absent(absence_evidence="no label").is_checkable_locally is False


def test_all_four_provenance_types_are_constructible():
    assert {
        p.type
        for p in (
            Provenance.located(page=1, bbox=BBOX, source_text="x"),
            Provenance.derived(derivation="a + b"),
            Provenance.inferred(basis="letterhead"),
            Provenance.absent(absence_evidence="searched all pages"),
        )
    } == set(ProvenanceType)


# --- FieldClaim -------------------------------------------------------------


def test_value_is_stored_verbatim_and_never_normalized():
    """Tier 0 owns parsing. If the model normalized '$18,381.16' itself, the
    'value parses from source_text' check would test our normalizer instead."""
    raw = money_claim(value="$18,381.16")
    assert raw.value == "$18,381.16"
    assert isinstance(raw.value, str)


def test_null_value_requires_absent_provenance():
    with pytest.raises(ValidationError, match="must carry absent provenance"):
        money_claim(value=None)


def test_absent_provenance_requires_null_value():
    with pytest.raises(ValidationError, match="requires a null value"):
        money_claim(
            value="1",
            provenance=Provenance.absent(absence_evidence="no total on ticket"),
        )


def test_absent_claim_is_valid():
    claim = money_claim(
        value=None,
        provenance=Provenance.absent(absence_evidence="no total row in reference layer"),
    )
    assert claim.value is None


def test_line_item_value_must_be_composite():
    with pytest.raises(ValidationError, match="line_item value must be"):
        FieldClaim(
            claim_id="c9",
            field_name="rows",
            field_class=FieldClass.LINE_ITEM,
            value="3 ea crushed rock",  # SYNTHETIC
            provenance=LOCATED,
        )


def test_line_item_accepts_a_row_list():
    claim = FieldClaim(
        claim_id="c9",
        field_name="rows",
        field_class=FieldClass.LINE_ITEM,
        # SYNTHETIC row
        value=[{"qty": "3", "unit_price": "12.50", "extended": "37.50"}],
        provenance=LOCATED,
    )
    assert isinstance(claim.value, list)


def test_nan_is_rejected():
    with pytest.raises(ValidationError, match="NaN is not a claim"):
        money_claim(value=float("nan"))


def test_infinity_is_rejected():
    with pytest.raises(ValidationError, match="infinity is not a claim"):
        money_claim(value=float("inf"))


def test_decimal_is_refused_as_a_claim_value():
    """It serializes to a JSON string and returns as str; a replayed log would
    disagree with the run that wrote it."""
    with pytest.raises(ValidationError, match="Decimal is not a claim value"):
        money_claim(value=Decimal("18381.16"))


def test_date_object_is_refused_as_a_claim_value():
    with pytest.raises(ValidationError, match="date/datetime is not a claim value"):
        FieldClaim(
            claim_id="c5",
            field_name="ticket_date",
            field_class=FieldClass.DATE,
            value=date(2026, 7, 14),
            provenance=LOCATED,
        )


def test_money_must_not_be_a_binary_float():
    """0.1 has no exact binary representation, so the amount logged would not be
    the amount read."""
    with pytest.raises(ValidationError, match="must not be stored as a binary float"):
        money_claim(value=18381.16)


def test_non_money_floats_are_fine():
    q = FieldClaim(
        claim_id="c10",
        field_name="net_weight_tons",
        field_class=FieldClass.QUANTITY,
        value=24.5,  # SYNTHETIC
        provenance=LOCATED,
    )
    assert q.value == 24.5


def test_claim_is_frozen_and_forbids_extras():
    claim = money_claim()
    with pytest.raises(ValidationError):
        claim.value = "1"
    with pytest.raises(ValidationError):
        money_claim(posterior=0.99)


def test_date_and_party_values_pass_through():
    d = FieldClaim(
        claim_id="c5",
        field_name="ticket_date",
        field_class=FieldClass.DATE,
        value="2026-07-14",  # SYNTHETIC
        provenance=LOCATED,
    )
    assert d.value == "2026-07-14"


def test_a_garbage_date_survives_to_be_rejected_by_tier_0():
    """The schema does not sanity-check dates; Tier 0 does, with a recorded
    outcome. A model that rejected this would hide a provider's error."""
    claim = FieldClaim(
        claim_id="c6",
        field_name="ticket_date",
        field_class=FieldClass.DATE,
        value="2026-13-45",  # SYNTHETIC, deliberately invalid
        provenance=LOCATED,
    )
    assert claim.value == "2026-13-45"


# --- Importance -------------------------------------------------------------


def test_important_field_classes_are_the_four_from_the_spec():
    assert IMPORTANT_FIELD_CLASSES == {
        FieldClass.MONEY,
        FieldClass.IDENTIFIER,
        FieldClass.QUANTITY,
        FieldClass.DATE,
    }


def test_customer_marked_fields_are_important_too():
    memo = FieldClaim(
        claim_id="c7",
        field_name="job_number_memo",
        field_class=FieldClass.TEXT,
        value="job 41B",  # SYNTHETIC
        provenance=LOCATED,
    )
    assert memo.is_important() is False
    assert memo.is_important({"job_number_memo"}) is True


# --- Consequence ------------------------------------------------------------


def test_policy_constant_resolves_without_a_value():
    c = Consequence(mode=ConsequenceMode.POLICY_CONSTANT, usd=Decimal("40"), source="customer:x")
    assert c.amount_usd() == Decimal("40")


def test_value_multiplier_scales_with_the_amount_at_risk():
    c = Consequence(
        mode=ConsequenceMode.VALUE_MULTIPLIER, multiplier=Decimal("1.5"), source="customer:x"
    )
    assert c.amount_usd(Decimal("18381.16")) == Decimal("27571.740")


def test_mode_and_fields_must_agree():
    with pytest.raises(ValidationError, match="requires usd"):
        Consequence(mode=ConsequenceMode.POLICY_CONSTANT, source="s")
    with pytest.raises(ValidationError, match="requires multiplier"):
        Consequence(mode=ConsequenceMode.VALUE_MULTIPLIER, source="s")
    with pytest.raises(ValidationError, match="must not set multiplier"):
        Consequence(
            mode=ConsequenceMode.POLICY_CONSTANT,
            usd=Decimal("1"),
            multiplier=Decimal("2"),
            source="s",
        )


def test_value_multiplier_refuses_an_unparsed_money_string():
    """A money value still held as a string has not been through Tier 0."""
    c = Consequence(
        mode=ConsequenceMode.VALUE_MULTIPLIER, multiplier=Decimal("1"), source="customer:x"
    )
    with pytest.raises(TypeError, match="not been parsed by Tier 0"):
        c.amount_usd("$18,381.16")


def test_value_multiplier_requires_a_value():
    c = Consequence(
        mode=ConsequenceMode.VALUE_MULTIPLIER, multiplier=Decimal("1"), source="customer:x"
    )
    with pytest.raises(ValueError, match="needs the field's numeric value"):
        c.amount_usd()


def test_value_multiplier_only_applies_to_money_fields():
    with pytest.raises(ValidationError, match="only applies to money fields"):
        FieldClaim(
            claim_id="c8",
            field_name="po_number",
            field_class=FieldClass.IDENTIFIER,
            value="PO-4471",  # SYNTHETIC
            provenance=LOCATED,
            consequence=Consequence(
                mode=ConsequenceMode.VALUE_MULTIPLIER,
                multiplier=Decimal("2"),
                source="customer:x",
            ),
        )


def test_claim_consequence_takes_the_tier_0_parse():
    claim = money_claim(
        consequence=Consequence(
            mode=ConsequenceMode.VALUE_MULTIPLIER,
            multiplier=Decimal("1"),
            source="customer:x",
        )
    )
    assert claim.consequence_usd(Decimal("18381.16")) == Decimal("18381.16")


def test_claim_consequence_uses_an_integer_value_directly():
    claim = money_claim(
        value=18381,
        consequence=Consequence(
            mode=ConsequenceMode.VALUE_MULTIPLIER,
            multiplier=Decimal("2"),
            source="customer:x",
        ),
    )
    assert claim.consequence_usd() == Decimal("36762")


def test_claim_consequence_refuses_to_guess_at_unparsed_text():
    claim = money_claim(
        consequence=Consequence(
            mode=ConsequenceMode.VALUE_MULTIPLIER,
            multiplier=Decimal("1"),
            source="customer:x",
        )
    )
    with pytest.raises(ValueError, match="needs the field's numeric value"):
        claim.consequence_usd()


def test_missing_consequence_is_an_error_not_a_default():
    """Defaulting would silently decide how much evidence a field deserves."""
    with pytest.raises(ValueError, match="no consequence attached"):
        money_claim().consequence_usd()


# --- ExtractionResult -------------------------------------------------------


def _result(**overrides) -> ExtractionResult:
    kwargs = dict(
        document_id="doc-1",
        document_class="construction_delivery_ticket",
        provider_id="openweights-local",
        provider_epoch=None,
        schema_version="0.1.0",
        claims=(
            money_claim(),
            money_claim(claim_id="c2", field_name="subtotal", value="17000.00"),
            FieldClaim(
                claim_id="c3",
                field_name="vendor_name",
                field_class=FieldClass.PARTY,
                value="Synthetic Aggregate Supply",  # SYNTHETIC
                provenance=LOCATED,
            ),
        ),
    )
    kwargs.update(overrides)
    return ExtractionResult(**kwargs)


def test_duplicate_claim_ids_are_rejected():
    with pytest.raises(ValidationError, match="duplicate claim_id"):
        _result(claims=(money_claim(), money_claim()))


def test_by_name_returns_every_occurrence():
    """Multi-occurrence agreement is Tier 1 evidence, so repeats are kept."""
    r = _result(
        claims=(
            money_claim(),
            money_claim(claim_id="c2", value="18381.16"),
        )
    )
    assert len(r.by_name("invoice_total")) == 2
    assert r.by_name("nothing_here") == ()


def test_important_claims_filters_by_class_and_customer_marks():
    r = _result()
    assert {c.claim_id for c in r.important_claims()} == {"c1", "c2"}
    assert {c.claim_id for c in r.important_claims({"vendor_name"})} == {"c1", "c2", "c3"}


def test_round_trips_through_json_without_losing_money_precision():
    original = _result(
        claims=(
            money_claim(
                value="18381.16",
                consequence=Consequence(
                    mode=ConsequenceMode.VALUE_MULTIPLIER,
                    multiplier=Decimal("1.5"),
                    source="customer:x",
                ),
            ),
        )
    )
    restored = ExtractionResult.model_validate_json(original.model_dump_json())
    assert restored == original
    assert restored.claims[0].consequence_usd(Decimal("18381.16")) == Decimal("27571.740")


@pytest.mark.parametrize(
    "value",
    ["18381.16", 24, 24.5, True, None, ["a", {"b": 1}], {"qty": "3"}],
)
def test_every_claim_value_kind_round_trips_as_itself(value):
    """A log replay must produce the claim that was written, type included."""
    provenance = Provenance.absent(absence_evidence="no total row") if value is None else LOCATED
    field_class = FieldClass.LINE_ITEM if isinstance(value, (list, dict)) else FieldClass.TEXT
    claim = FieldClaim(
        claim_id="rt",
        field_name="f",
        field_class=field_class,
        value=value,
        provenance=provenance,
    )
    restored = FieldClaim.model_validate_json(claim.model_dump_json())
    assert restored == claim
    assert type(restored.value) is type(claim.value)


def test_epoch_is_carried_even_when_unknown():
    assert _result().provider_epoch is None
    assert _result(provider_epoch="2026-09-16/a").provider_epoch == "2026-09-16/a"
