"""Multi-variant extraction — Milestone 23."""
from __future__ import annotations

import pytest

from services.item_identity import split_base_and_variants, normalize_name
from services.item_matcher import match_item


# ── split_base_and_variants: MULTIPLE variants at once ──
def test_split_multi_variants():
    variants = [
        {"key": "male",  "label": "Male"},
        {"key": "large", "label": "Large"},
    ]
    base, vs = split_base_and_variants("male live blue crab large", variants)
    assert set(vs) == {"male", "large"}
    assert "male" not in base.split()
    assert "large" not in base.split()


def test_split_multi_variants_returns_base():
    variants = [
        {"key": "male",  "label": "Male"},
        {"key": "large", "label": "Large"},
    ]
    base, vs = split_base_and_variants("Male LARGE Live Blue Crab", variants)
    assert normalize_name(base) == "live blue crab"
    assert set(vs) == {"male", "large"}


# ── matcher: multi-variant match carried through ──
def test_matcher_returns_multi_variants():
    c = {
        "id": "C1", "name": "Live Blue Crab",
        "variants": [
            {"key": "male",  "label": "Male"},
            {"key": "large", "label": "Large"},
            {"key": "female", "label": "Female"},
        ],
        "is_suggested": False, "is_archived": False,
    }
    r = match_item("male live blue crab large", canonical_items=[c], aliases=[])
    assert r.canonical_item_id == "C1"
    assert set(r.variant_keys) == {"male", "large"}
    # Legacy single field is populated too
    assert r.variant_key in {"male", "large"}


def test_matcher_zero_variants_still_works():
    c = {"id": "C1", "name": "Olive Oil",
         "variants": [], "is_suggested": False, "is_archived": False}
    r = match_item("Olive Oil", canonical_items=[c], aliases=[])
    assert r.canonical_item_id == "C1"
    assert r.variant_keys == []
    assert r.variant_key is None


def test_matcher_one_variant_missing_variants_field():
    """Legacy canonical without a variants field must not crash."""
    c = {"id": "C1", "name": "Olive Oil",
         "is_suggested": False, "is_archived": False}
    r = match_item("Olive Oil", canonical_items=[c], aliases=[])
    assert r.canonical_item_id == "C1"
    assert r.variant_keys == []
