"""
Milestone 6 — Controlled Action Layer tests (sync, asyncio.run under the hood).
"""
import asyncio
import pytest
from services.procurement_suggestions import (
    log_event, save_suggestion, list_suggestions,
    suggested_quantity_hint, ALLOWED_EVENT_TYPES,
)


def sync(coro):
    return asyncio.new_event_loop().run_until_complete(coro)


class _FakeCollection:
    def __init__(self):
        self.docs = []

    async def insert_one(self, doc):
        self.docs.append(dict(doc))
        return type("X", (), {"inserted_id": "x"})()

    def find(self, q, proj=None):
        rows = [d for d in self.docs if all(d.get(k) == v for k, v in q.items())]
        class _Cursor:
            def __init__(self, rows): self.rows = rows
            def sort(self, *a, **kw):
                key = a[0] if a else "observed_at"
                direction = a[1] if len(a) > 1 else -1
                self.rows = sorted(self.rows, key=lambda r: r.get(key) or "", reverse=direction == -1)
                return self
            async def to_list(self, n): return self.rows[:n]
        return _Cursor(rows)


@pytest.fixture
def patched_db(monkeypatch):
    import services.procurement_suggestions as mod
    fake = type("DB", (), {
        "procurement_suggestion_events": _FakeCollection(),
        "procurement_suggestions": _FakeCollection(),
        "price_history": _FakeCollection(),
    })()
    monkeypatch.setattr(mod, "db", fake)
    return fake


USER = {"id": "u1", "restaurant_id": "r1", "name": "Demo"}


def test_event_allowed_types_enumerated():
    assert ALLOWED_EVENT_TYPES == {
        "suggestion_opened", "draft_viewed", "acknowledgment_checked",
        "action_confirmed", "action_canceled",
    }


def test_log_event_happy_path(patched_db):
    ev = sync(log_event(
        user=USER, canonical_product_id="p1",
        recommendation_type="switch_vendor", event_type="suggestion_opened",
    ))
    assert ev["event_type"] == "suggestion_opened"
    assert ev["user_id"] == "u1"
    assert ev["restaurant_id"] == "r1"
    assert ev["canonical_product_id"] == "p1"
    assert "timestamp" in ev
    assert patched_db.procurement_suggestion_events.docs[0]["event_type"] == "suggestion_opened"


def test_log_event_rejects_invalid_type(patched_db):
    with pytest.raises(ValueError):
        sync(log_event(
            user=USER, canonical_product_id="p1",
            recommendation_type="switch_vendor", event_type="pay_now",
        ))


def test_save_suggestion_requires_acknowledgment(patched_db):
    with pytest.raises(PermissionError):
        sync(save_suggestion(
            user=USER, canonical_product_id="p1", canonical_unit="lb",
            recommendation_type="switch_vendor", recommended_vendor="USFoods",
            reference_price_per_unit=3.50, current_price_per_unit=4.25,
            decision_confidence=0.98, confidence_level="high", risk_level="medium",
            reason_summary="High likelihood...", evidence=[], uncertainty=[],
            acknowledgment_confirmed=False,
        ))


def test_save_suggestion_persists_and_logs_confirm(patched_db):
    doc = sync(save_suggestion(
        user=USER, canonical_product_id="p1", canonical_unit="lb",
        recommendation_type="switch_vendor", recommended_vendor="USFoods",
        reference_price_per_unit=3.50, current_price_per_unit=4.25,
        decision_confidence=0.98, confidence_level="high", risk_level="medium",
        reason_summary="High likelihood of savings ...",
        evidence=["Sysco at $4.25/lb", "USFoods 17% cheaper"],
        uncertainty=["Alt based on 3 obs"],
        acknowledgment_confirmed=True,
    ))
    assert doc["status"] == "saved_for_review"
    assert doc["acknowledgment_confirmed"] is True
    assert doc["acknowledged_at"]
    events = patched_db.procurement_suggestion_events.docs
    assert any(e["event_type"] == "action_confirmed" for e in events)
    stored = patched_db.procurement_suggestions.docs
    assert len(stored) == 1
    assert stored[0]["reference_price_per_unit"] == 3.50


def test_save_suggestion_never_uses_execution_words(patched_db):
    doc = sync(save_suggestion(
        user=USER, canonical_product_id="p1", canonical_unit="lb",
        recommendation_type="switch_vendor", recommended_vendor="USFoods",
        reference_price_per_unit=3.50, current_price_per_unit=4.25,
        decision_confidence=0.98, confidence_level="high", risk_level="medium",
        reason_summary="High likelihood of savings ...", evidence=[], uncertainty=[],
        acknowledgment_confirmed=True,
    ))
    banned = {"order_placed", "submitted", "executed", "purchased", "bought"}
    assert doc["status"] not in banned
    assert doc["status"] == "saved_for_review"


def test_quantity_hint_returns_advisory_payload(patched_db):
    for i, q in enumerate([2.0, 3.0, 4.0, 5.0, 6.0]):
        patched_db.price_history.docs.append({
            "restaurant_id": "r1", "canonical_product_id": "p1",
            "canonical_unit": "lb", "quantity": q,
            "observed_at": f"2026-04-{10+i:02d}",
            "data_quality_flag": "good",
        })
    patched_db.price_history.docs.append({
        "restaurant_id": "r1", "canonical_product_id": "p1",
        "canonical_unit": "lb", "quantity": 999,
        "observed_at": "2026-04-16", "data_quality_flag": "poor",
    })
    hint = sync(suggested_quantity_hint(
        restaurant_id="r1", canonical_product_id="p1", canonical_unit="lb",
    ))
    assert hint["lookback"] == 3
    assert hint["quantities"] == [6.0, 5.0, 4.0]
    assert "Suggestion only" in hint["disclaimer"]
    assert "not a recommended order quantity" in hint["disclaimer"].lower()
    assert "Based on your last" in hint["helper_text"]


def test_list_suggestions_scoped_per_restaurant(patched_db):
    sync(save_suggestion(
        user=USER, canonical_product_id="p1", canonical_unit="lb",
        recommendation_type="switch_vendor", recommended_vendor="X",
        reference_price_per_unit=1, current_price_per_unit=1,
        decision_confidence=0.9, confidence_level="high", risk_level="low",
        reason_summary="x", evidence=[], uncertainty=[],
        acknowledgment_confirmed=True,
    ))
    items = sync(list_suggestions("r1"))
    assert len(items) == 1
    items2 = sync(list_suggestions("r2"))
    assert items2 == []
