"""
catalog_linkage unit tests (in-memory fake collections).

Covers:
  - link_correction_to_catalog: exact case-insensitive match → 'linked'
  - contains-match → 'linked'
  - no-match → 'suggested' (creates new canonical_item with is_suggested=True)
  - creates item_aliases row on both link and suggest paths
  - alias upsert increments usage_count on subsequent link
  - skipped when corrected_name is empty
  - tenant isolation (different restaurant never matches)
"""
import asyncio
import pytest


def sync(coro):
    return asyncio.new_event_loop().run_until_complete(coro)


class _FakeCollection:
    def __init__(self):
        self.docs = []

    def _match(self, d, q):
        for k, v in q.items():
            if isinstance(v, dict):
                if "$regex" in v:
                    import re
                    opts = v.get("$options", "")
                    flags = re.IGNORECASE if "i" in opts else 0
                    if not re.search(v["$regex"], str(d.get(k, "") or ""), flags):
                        return False
                elif "$in" in v:
                    if d.get(k) not in v["$in"]:
                        return False
                else:
                    if d.get(k) != v:
                        return False
            else:
                if d.get(k) != v:
                    return False
        return True

    async def insert_one(self, doc):
        self.docs.append(dict(doc))
        return type("R", (), {"inserted_id": "x"})()

    async def find_one(self, q, proj=None):
        for d in self.docs:
            if self._match(d, q):
                r = dict(d)
                if proj and proj.get("_id") == 0:
                    r.pop("_id", None)
                return r
        return None

    async def update_one(self, q, upd):
        for d in self.docs:
            if self._match(d, q):
                if "$set" in upd:
                    d.update(upd["$set"])
                if "$inc" in upd:
                    for k, v in upd["$inc"].items():
                        d[k] = (d.get(k) or 0) + v
                return type("R", (), {"matched_count": 1, "modified_count": 1})()
        return type("R", (), {"matched_count": 0, "modified_count": 0})()


@pytest.fixture
def fake_db(monkeypatch):
    import services.catalog_linkage as mod
    fake = type("DB", (), {
        "canonical_items": _FakeCollection(),
        "item_aliases":   _FakeCollection(),
    })()
    monkeypatch.setattr(mod, "db", fake)
    return fake


def test_exact_case_insensitive_link(fake_db):
    from services.catalog_linkage import link_correction_to_catalog
    # Seed a canonical item
    sync(fake_db.canonical_items.insert_one({
        "id": "ci-1", "restaurant_id": "r1", "name": "Chicken Breast",
    }))
    res = sync(link_correction_to_catalog(
        restaurant_id="r1", user_id="u1",
        original_raw_name="CHCKN BRST", corrected_name="chicken breast",  # case differs
        unit="lb", category="Meat",
    ))
    assert res["action"] == "linked"
    assert res["canonical_item_id"] == "ci-1"
    # Alias was created
    aliases = fake_db.item_aliases.docs
    assert len(aliases) == 1
    assert aliases[0]["alias"] == "CHCKN BRST"
    assert aliases[0]["canonical_item_id"] == "ci-1"
    assert aliases[0]["source"] == "user_edit"
    assert aliases[0]["usage_count"] == 1


def test_contains_match_link(fake_db):
    from services.catalog_linkage import link_correction_to_catalog
    sync(fake_db.canonical_items.insert_one({
        "id": "ci-2", "restaurant_id": "r1", "name": "Heavy Cream 40% Gallon",
    }))
    res = sync(link_correction_to_catalog(
        restaurant_id="r1", user_id="u1",
        original_raw_name="HVY CRM", corrected_name="Heavy Cream",
    ))
    assert res["action"] == "linked"
    assert res["canonical_item_id"] == "ci-2"


def test_no_match_creates_suggested(fake_db):
    from services.catalog_linkage import link_correction_to_catalog
    res = sync(link_correction_to_catalog(
        restaurant_id="r1", user_id="u1",
        original_raw_name="BURRATA 8oz", corrected_name="Burrata",
        unit="each", category="Dairy",
    ))
    assert res["action"] == "suggested"
    assert res["canonical_name"] == "Burrata"

    # New canonical_item exists with is_suggested=True
    cis = fake_db.canonical_items.docs
    assert len(cis) == 1
    assert cis[0]["is_suggested"] is True
    assert cis[0]["suggested_source"] == "user_edit"
    assert cis[0]["unit"] == "each"
    assert cis[0]["category"] == "Dairy"
    # Alias also traces the linkage
    assert len(fake_db.item_aliases.docs) == 1


def test_repeat_same_correction_increments_alias(fake_db):
    from services.catalog_linkage import link_correction_to_catalog
    sync(fake_db.canonical_items.insert_one({
        "id": "ci-3", "restaurant_id": "r1", "name": "Salmon Fillet",
    }))
    sync(link_correction_to_catalog(
        restaurant_id="r1", user_id="u1",
        original_raw_name="SLMN FLT", corrected_name="salmon fillet",
    ))
    sync(link_correction_to_catalog(
        restaurant_id="r1", user_id="u1",
        original_raw_name="SLMN FLT", corrected_name="Salmon Fillet",
    ))
    aliases = fake_db.item_aliases.docs
    assert len(aliases) == 1, "must not duplicate on same alias"
    assert aliases[0]["usage_count"] == 2


def test_empty_corrected_name_is_skipped(fake_db):
    from services.catalog_linkage import link_correction_to_catalog
    res = sync(link_correction_to_catalog(
        restaurant_id="r1", user_id="u1",
        original_raw_name="X", corrected_name="   ",
    ))
    assert res["action"] == "skipped"
    assert res["canonical_item_id"] is None
    assert len(fake_db.canonical_items.docs) == 0


def test_tenant_isolation(fake_db):
    from services.catalog_linkage import link_correction_to_catalog
    # r2 has "Tomato Paste"
    sync(fake_db.canonical_items.insert_one({
        "id": "ci-r2", "restaurant_id": "r2", "name": "Tomato Paste",
    }))
    # r1 correcting "Tomato Paste" must NOT match r2's entry — should create a suggested for r1.
    res = sync(link_correction_to_catalog(
        restaurant_id="r1", user_id="u1",
        original_raw_name="TMT PST", corrected_name="Tomato Paste",
    ))
    assert res["action"] == "suggested"
    # r1 gets its own new canonical_item
    r1_items = [c for c in fake_db.canonical_items.docs if c["restaurant_id"] == "r1"]
    assert len(r1_items) == 1
    r2_items = [c for c in fake_db.canonical_items.docs if c["restaurant_id"] == "r2"]
    assert len(r2_items) == 1
