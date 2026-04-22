"""
Decision Audit Log unit tests (async, with in-memory fake collection).

Covers:
  - record_recommendation_generated: creates one record, upserts on repeat
  - record_interaction: stamps first occurrence only, refreshes status
  - link_suggestion: attaches suggestion_id to open record
  - finalize_outcome: closes record, creates minimal record if missing
  - aggregate_audit_stats: correct shape, rates, sample queries
  - tenant isolation: other tenant's records never leak
  - invalid outcome_type rejected
"""
import asyncio
import uuid
import pytest


def sync(coro):
    return asyncio.new_event_loop().run_until_complete(coro)


class _FakeCollection:
    def __init__(self):
        self.docs: list[dict] = []

    def _match(self, d, q):
        for k, v in q.items():
            if isinstance(v, dict) and "$in" in v:
                if d.get(k) not in v["$in"]:
                    return False
            else:
                if d.get(k) != v:
                    return False
        return True

    async def insert_one(self, doc):
        self.docs.append(dict(doc))
        return type("X", (), {"inserted_id": "x"})()

    async def find_one(self, q, proj=None, sort=None):
        rows = [d for d in self.docs if self._match(d, q)]
        if sort:
            k, direction = sort[0]
            rows = sorted(rows, key=lambda r: r.get(k) or "", reverse=(direction == -1))
        if not rows:
            return None
        r = dict(rows[0])
        if proj and "_id" in proj and proj["_id"] == 0:
            r.pop("_id", None)
        return r

    async def update_one(self, q, upd):
        matched = 0
        for d in self.docs:
            if self._match(d, q):
                if "$set" in upd:
                    d.update(upd["$set"])
                if "$inc" in upd:
                    for k, v in upd["$inc"].items():
                        d[k] = (d.get(k) or 0) + v
                matched += 1
                break  # update_one
        return type("R", (), {"matched_count": matched, "modified_count": matched})()

    def find(self, q, proj=None):
        rows = [d for d in self.docs if self._match(d, q)]

        class _Cursor:
            def __init__(self, rows): self.rows = rows
            def sort(self, *a, **kw):
                key = a[0] if a else "generated_at"
                direction = a[1] if len(a) > 1 else -1
                self.rows = sorted(self.rows, key=lambda r: r.get(key) or "", reverse=(direction == -1))
                return self
            async def to_list(self, n): return self.rows[:n]
        return _Cursor(rows)


@pytest.fixture
def audit_db(monkeypatch):
    import services.procurement_audit as mod
    fake = type("DB", (), {"procurement_decision_events": _FakeCollection()})()
    monkeypatch.setattr(mod, "db", fake)
    return fake


def _decision(cpid="p1", rtype="switch_vendor", conf=0.9, level="High", risk="medium"):
    return {
        "canonical_product_id": cpid,
        "canonical_name": f"Prod {cpid}",
        "canonical_unit": "lb",
        "recommendation_type": rtype,
        "decision_confidence": conf,
        "confidence_level": level,
        "risk_level": risk,
    }


def test_record_generated_creates_one_record(audit_db):
    from services.procurement_audit import record_recommendation_generated
    d = _decision()
    rec = sync(record_recommendation_generated(
        restaurant_id="r1", user_id="u1", decision=d,
    ))
    assert rec["status"] == "open"
    assert rec["confidence_score"] == 0.9
    assert rec["generation_count"] == 1
    assert len(audit_db.procurement_decision_events.docs) == 1


def test_record_generated_is_idempotent_same_rec_type(audit_db):
    from services.procurement_audit import record_recommendation_generated
    sync(record_recommendation_generated(
        restaurant_id="r1", user_id="u1", decision=_decision(conf=0.9),
    ))
    sync(record_recommendation_generated(
        restaurant_id="r1", user_id="u2", decision=_decision(conf=0.95),
    ))
    docs = audit_db.procurement_decision_events.docs
    assert len(docs) == 1, "must not duplicate on re-generation"
    assert docs[0]["confidence_score"] == 0.95, "must refresh confidence"
    assert docs[0]["generation_count"] == 2


def test_different_rec_type_creates_second_record(audit_db):
    from services.procurement_audit import record_recommendation_generated
    sync(record_recommendation_generated(
        restaurant_id="r1", user_id="u1", decision=_decision(rtype="switch_vendor"),
    ))
    sync(record_recommendation_generated(
        restaurant_id="r1", user_id="u1", decision=_decision(rtype="renegotiate"),
    ))
    assert len(audit_db.procurement_decision_events.docs) == 2


def test_record_interaction_stamps_first_occurrence_only(audit_db):
    from services.procurement_audit import (
        record_recommendation_generated, record_interaction,
    )
    sync(record_recommendation_generated(
        restaurant_id="r1", user_id="u1", decision=_decision(),
    ))
    first = sync(record_interaction(
        restaurant_id="r1", canonical_product_id="p1",
        recommendation_type="switch_vendor", event_type="suggestion_opened",
    ))
    ts1 = first["suggestion_opened_at"]
    assert ts1
    assert first["status"] == "interacted"

    # Second call should NOT overwrite the timestamp
    second = sync(record_interaction(
        restaurant_id="r1", canonical_product_id="p1",
        recommendation_type="switch_vendor", event_type="suggestion_opened",
    ))
    assert second["suggestion_opened_at"] == ts1


def test_link_suggestion_attaches_id(audit_db):
    from services.procurement_audit import (
        record_recommendation_generated, link_suggestion,
    )
    sync(record_recommendation_generated(
        restaurant_id="r1", user_id="u1", decision=_decision(),
    ))
    sid = str(uuid.uuid4())
    sync(link_suggestion(
        restaurant_id="r1", canonical_product_id="p1",
        recommendation_type="switch_vendor", suggestion_id=sid,
    ))
    doc = audit_db.procurement_decision_events.docs[0]
    assert doc["suggestion_id"] == sid


def test_finalize_outcome_closes_record(audit_db):
    from services.procurement_audit import (
        record_recommendation_generated, link_suggestion, finalize_outcome,
    )
    sync(record_recommendation_generated(
        restaurant_id="r1", user_id="u1", decision=_decision(),
    ))
    sid = str(uuid.uuid4())
    sync(link_suggestion(
        restaurant_id="r1", canonical_product_id="p1",
        recommendation_type="switch_vendor", suggestion_id=sid,
    ))
    res = sync(finalize_outcome(
        restaurant_id="r1", canonical_product_id="p1",
        recommendation_type="switch_vendor", suggestion_id=sid,
        outcome_type="acted_on", outcome_note="switched to USF", user_id="u1",
    ))
    assert res["status"] == "finalized"
    assert res["outcome_type"] == "acted_on"
    assert res["outcome_note"] == "switched to USF"
    assert res["outcome_at"]


def test_finalize_outcome_invalid_type_rejected(audit_db):
    from services.procurement_audit import finalize_outcome
    with pytest.raises(ValueError):
        sync(finalize_outcome(
            restaurant_id="r1", canonical_product_id="p1",
            recommendation_type="switch_vendor", suggestion_id=None,
            outcome_type="purchased",
        ))


def test_finalize_outcome_creates_minimal_record_when_missing(audit_db):
    from services.procurement_audit import finalize_outcome
    res = sync(finalize_outcome(
        restaurant_id="r1", canonical_product_id="p_orphan",
        recommendation_type="renegotiate", suggestion_id="orphan-sid",
        outcome_type="not_pursued", outcome_note="", user_id="u1",
    ))
    assert res is not None
    assert res["status"] == "finalized"
    assert res["outcome_type"] == "not_pursued"
    assert res["suggestion_id"] == "orphan-sid"


def test_tenant_isolation(audit_db):
    from services.procurement_audit import (
        record_recommendation_generated, list_audit_events,
    )
    sync(record_recommendation_generated(
        restaurant_id="r1", user_id="u1", decision=_decision(cpid="a"),
    ))
    sync(record_recommendation_generated(
        restaurant_id="r2", user_id="u2", decision=_decision(cpid="b"),
    ))
    r1 = sync(list_audit_events(restaurant_id="r1"))
    r2 = sync(list_audit_events(restaurant_id="r2"))
    assert len(r1) == 1 and r1[0]["canonical_product_id"] == "a"
    assert len(r2) == 1 and r2[0]["canonical_product_id"] == "b"


def test_aggregate_stats_shape_and_rates(audit_db):
    from services.procurement_audit import (
        record_recommendation_generated, link_suggestion, finalize_outcome,
        aggregate_audit_stats,
    )
    # 3 switch_vendor — 2 acted_on, 1 not_pursued
    for i, out in enumerate(["acted_on", "acted_on", "not_pursued"]):
        d = _decision(cpid=f"sv{i}", rtype="switch_vendor")
        sync(record_recommendation_generated(restaurant_id="r1", user_id="u1", decision=d))
        sid = f"sid-sv{i}"
        sync(link_suggestion(restaurant_id="r1", canonical_product_id=f"sv{i}",
                             recommendation_type="switch_vendor", suggestion_id=sid))
        sync(finalize_outcome(restaurant_id="r1", canonical_product_id=f"sv{i}",
                              recommendation_type="switch_vendor",
                              suggestion_id=sid, outcome_type=out, user_id="u1"))
    # 1 high-confidence renegotiate not_pursued (should appear in high_confidence_not_pursued)
    d = _decision(cpid="rn1", rtype="renegotiate", level="High")
    sync(record_recommendation_generated(restaurant_id="r1", user_id="u1", decision=d))
    sync(link_suggestion(restaurant_id="r1", canonical_product_id="rn1",
                         recommendation_type="renegotiate", suggestion_id="sid-rn1"))
    sync(finalize_outcome(restaurant_id="r1", canonical_product_id="rn1",
                          recommendation_type="renegotiate",
                          suggestion_id="sid-rn1", outcome_type="not_pursued",
                          outcome_note="vendor relationship", user_id="u1"))

    stats = sync(aggregate_audit_stats(restaurant_id="r1"))

    assert stats["total"] == 4
    assert stats["finalized"] == 4
    sv = stats["by_recommendation_type"]["switch_vendor"]
    assert sv["generated"] == 3
    assert sv["acted_on"] == 2
    assert sv["not_pursued"] == 1
    assert sv["acted_on_rate"] == round(2 / 3, 4)
    assert stats["sample_queries"]["switch_vendor_acted_on_rate"] == round(2 / 3, 4)
    # high-confidence not_pursued: 1 switch_vendor (sv2) + 1 renegotiate (rn1)
    assert stats["sample_queries"]["high_confidence_not_pursued_count"] == 2
    names = {h["canonical_product_id"] for h in stats["high_confidence_not_pursued"]}
    assert "sv2" in names and "rn1" in names


def test_list_audit_events_filters(audit_db):
    from services.procurement_audit import (
        record_recommendation_generated, finalize_outcome, list_audit_events,
    )
    sync(record_recommendation_generated(
        restaurant_id="r1", user_id="u1", decision=_decision(cpid="x1"),
    ))
    sync(record_recommendation_generated(
        restaurant_id="r1", user_id="u1", decision=_decision(cpid="x2", rtype="renegotiate"),
    ))
    sync(finalize_outcome(
        restaurant_id="r1", canonical_product_id="x1",
        recommendation_type="switch_vendor", suggestion_id=None,
        outcome_type="acted_on", user_id="u1",
    ))
    finalized = sync(list_audit_events(restaurant_id="r1", status="finalized"))
    assert len(finalized) == 1 and finalized[0]["canonical_product_id"] == "x1"

    rn = sync(list_audit_events(restaurant_id="r1", recommendation_type="renegotiate"))
    assert len(rn) == 1 and rn[0]["canonical_product_id"] == "x2"

    acted = sync(list_audit_events(restaurant_id="r1", outcome_type="acted_on"))
    assert len(acted) == 1
