"""
Milestone 20 — Analytics identity-based grouping tests.

Covers:
  • identity_group_key uses canonical_item_id when present
  • falls back to normalized raw_name (never raw item_name) when absent
  • merge hop: a line linked to a merged suggestion rolls up into the
    target canonical's group
  • variants stay separate (male vs female on same canonical)
  • tenant isolation of the index
"""
from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from services.identity_resolver import (
    CanonicalIndex, GROUP_PREFIX_CANON, GROUP_PREFIX_NORM,
)


def _mk_index(
    canonicals: list[dict] | None = None,
    aliases: list[dict] | None = None,
):
    by_id = {c["id"]: c for c in (canonicals or [])}
    merge_targets = {
        c["id"]: c["merged_into_item_id"]
        for c in (canonicals or [])
        if c.get("is_merged") and c.get("merged_into_item_id")
    }
    from services.item_identity import normalize_name
    name_lookup = {}
    for c in (canonicals or []):
        n = normalize_name(c.get("name"))
        if n and n not in name_lookup:
            name_lookup[n] = c["id"]
    alias_lookup = {}
    for a in (aliases or []):
        txt = a.get("alias") or a.get("alias_name") or ""
        n = normalize_name(txt)
        cid = a.get("canonical_item_id")
        if n and cid and n not in alias_lookup:
            alias_lookup[n] = cid
    return CanonicalIndex(by_id, alias_lookup, name_lookup, merge_targets)


def test_canonical_id_wins():
    idx = _mk_index(canonicals=[{"id": "A1", "name": "Live Blue Crab"}])
    key, nm, v = idx.resolve({"raw_name": "whatever", "canonical_item_id": "A1"})
    assert key == f"{GROUP_PREFIX_CANON}A1"
    assert nm == "Live Blue Crab"
    assert v is None


def test_canonical_id_with_variant_separates():
    idx = _mk_index(canonicals=[{"id": "A1", "name": "Live Blue Crab"}])
    k_m, _, v_m = idx.resolve({"canonical_item_id": "A1", "variant_key": "male", "raw_name": "x"})
    k_f, _, v_f = idx.resolve({"canonical_item_id": "A1", "variant_key": "female", "raw_name": "x"})
    assert k_m != k_f
    assert v_m == "male" and v_f == "female"


def test_merge_hop_rolls_up():
    idx = _mk_index(canonicals=[
        {"id": "TARGET1", "name": "Live Blue Crab"},
        {"id": "SUG1", "name": "Blue Crab Live", "is_merged": True, "merged_into_item_id": "TARGET1"},
    ])
    k, nm, _ = idx.resolve({"canonical_item_id": "SUG1", "raw_name": "anything"})
    assert k == f"{GROUP_PREFIX_CANON}TARGET1"
    assert nm == "Live Blue Crab"


def test_alias_fallback_resolves():
    idx = _mk_index(
        canonicals=[{"id": "A1", "name": "Live Blue Crab"}],
        aliases=[{"alias": "LIVE BLUE CRABS", "canonical_item_id": "A1"}],
    )
    # No canonical_item_id on the line, but raw_name matches alias
    k, nm, _ = idx.resolve({"raw_name": "Live Blue Crabs"})
    assert k == f"{GROUP_PREFIX_CANON}A1"
    assert nm == "Live Blue Crab"


def test_name_fallback_resolves():
    idx = _mk_index(canonicals=[{"id": "A1", "name": "Olive Oil"}])
    k, nm, _ = idx.resolve({"raw_name": "olive  oil"})  # normalizes to match
    assert k == f"{GROUP_PREFIX_CANON}A1"
    assert nm == "Olive Oil"


def test_fallback_uses_normalized_not_raw():
    idx = _mk_index(canonicals=[])
    # Variations must collapse to ONE group key via normalization,
    # NOT split by raw_name differences.
    a, _, _ = idx.resolve({"raw_name": "  Funky   WIDGET-X  "})
    b, _, _ = idx.resolve({"raw_name": "funky widget x"})
    c, _, _ = idx.resolve({"raw_name": "FUNKY; widget,  X"})
    assert a == b == c
    assert a.startswith(GROUP_PREFIX_NORM)


def test_empty_input_falls_back_safely():
    idx = _mk_index()
    k, nm, _ = idx.resolve({"raw_name": ""})
    assert k.startswith(GROUP_PREFIX_NORM)
    assert nm is None


def test_missing_canonical_id_stale_reference_falls_back():
    """Line has canonical_item_id pointing to a deleted / archived canonical
    — must not crash; falls back to alias/name/norm."""
    idx = _mk_index(
        canonicals=[{"id": "LIVE1", "name": "Live Thing"}],
    )
    k, nm, _ = idx.resolve({"canonical_item_id": "GHOST", "raw_name": "live thing"})
    assert k == f"{GROUP_PREFIX_CANON}LIVE1"
    assert nm == "Live Thing"


# ─── build_canonical_index DB loader smoke (mocked) ───
@pytest.mark.asyncio
async def test_build_canonical_index_scopes_by_tenant():
    from services.identity_resolver import build_canonical_index

    canon_docs = [{"id": "A", "name": "Thing"}]
    alias_docs = [{"alias": "alias-x", "canonical_item_id": "A"}]

    def _make_cursor(docs):
        cursor = MagicMock()
        async def _aiter(self):
            for d in docs:
                yield d
        cursor.__aiter__ = _aiter
        return cursor

    with patch("services.identity_resolver.db") as mock_db:
        mock_db.canonical_items.find = MagicMock(return_value=_make_cursor(canon_docs))
        mock_db.item_aliases.find = MagicMock(return_value=_make_cursor(alias_docs))
        idx = await build_canonical_index("tenant-42")
        # Scoped query was issued with the correct restaurant_id
        mock_db.canonical_items.find.assert_called_once()
        args, kwargs = mock_db.canonical_items.find.call_args
        assert args[0]["restaurant_id"] == "tenant-42"
        mock_db.item_aliases.find.assert_called_once()
        args2, _ = mock_db.item_aliases.find.call_args
        assert args2[0]["restaurant_id"] == "tenant-42"
        # And the returned index is usable
        k, nm, _ = idx.resolve({"canonical_item_id": "A", "raw_name": "ignored"})
        assert k == f"{GROUP_PREFIX_CANON}A"
        assert nm == "Thing"
