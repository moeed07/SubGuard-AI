import asyncio
import json

from google.genai._gaos.google_genai import AsyncGeminiNextGenInteractions
from google.genai._gaos.types.interactions.interaction import Interaction

from intelligence.api import (
    build_portfolio, estimate_renewal_from_selection, extract_events, lookup_public_plan,
)
from intelligence.fictional import AS_OF, TIMEZONE, fictional_messages
from intelligence.review_rules import reviewable_charges

PUBLIC_PLAN = {"product": "Orbit Reader", "plan": "Pro", "storefront": "google-play", "market": "pk"}


def test_search_is_opt_in_and_accepts_only_public_lookup_fields(monkeypatch):
    monkeypatch.delenv("SUBGUARD_PUBLIC_PLAN_LOOKUP", raising=False)
    assert asyncio.run(lookup_public_plan(**PUBLIC_PLAN)) == {"status": "disabled"}
    monkeypatch.setenv("SUBGUARD_PUBLIC_PLAN_LOOKUP", "true")
    assert asyncio.run(lookup_public_plan(**dict(PUBLIC_PLAN, product="reader@example.com"))) == {
        "status": "invalid_plan",
    }


def test_lookup_uses_google_search_and_returns_its_display_payload(monkeypatch):
    monkeypatch.setenv("SUBGUARD_PUBLIC_PLAN_LOOKUP", "true")
    monkeypatch.setenv("GOOGLE_API_KEY", "fixture-only")
    monkeypatch.setenv("GEMINI_MODEL", "fixture-model")
    text = "Orbit Reader Pro offers monthly and annual subscriptions."
    citation = {"type": "url_citation", "url": "https://orbit.example/pricing", "title": "Orbit",
                "start_index": 0, "end_index": len(text)}
    suggestions = "<div>Orbit Reader plans</div>"
    result = Interaction.model_validate({"status": "completed", "steps": [
        {"type": "google_search_result", "call_id": "search-1", "result": [{"search_suggestions": suggestions}]},
        {"type": "model_output", "content": [{"type": "text", "text": text, "annotations": [citation]}]},
    ]})
    requests = []

    async def fake_create(self, **kwargs):
        requests.append(kwargs)
        return result

    monkeypatch.setattr(AsyncGeminiNextGenInteractions, "create", fake_create)
    displayed = asyncio.run(lookup_public_plan(**PUBLIC_PLAN))
    assert displayed == {
        "status": "complete", "content": [{"type": "text", "text": text, "annotations": [citation]}],
        "search_suggestions": [suggestions],
    }
    request, = requests
    assert json.loads(request["input"]) == dict(PUBLIC_PLAN, market="PK")
    assert request["model"] == "fixture-model"
    assert request["tools"] == [{"type": "google_search"}]
    assert request["store"] is False


def test_lookup_without_search_suggestions_returns_no_result(monkeypatch):
    monkeypatch.setenv("SUBGUARD_PUBLIC_PLAN_LOOKUP", "true")
    monkeypatch.setenv("GOOGLE_API_KEY", "fixture-only")

    async def fake_create(self, **kwargs):
        return Interaction.model_validate({"status": "completed", "steps": [
            {"type": "model_output", "content": [{"type": "text", "text": "Probably monthly."}]},
        ]})

    monkeypatch.setattr(AsyncGeminiNextGenInteractions, "create", fake_create)
    assert asyncio.run(lookup_public_plan(**PUBLIC_PLAN)) == {"status": "unavailable"}


def test_selected_cycle_estimates_locally_and_respects_cancellation_and_confirmed_due():
    events = extract_events(fictional_messages(canceled=True))
    payment, renewal, cancellation = events[2], events[3], events[-1]
    payment = dict(payment, cycle=None)
    subscription_key = payment["subscription_key"]
    original = build_portfolio([payment], AS_OF, TIMEZONE)
    estimate = estimate_renewal_from_selection(original, subscription_key, "monthly")
    assert estimate == {
        "subscription_key": subscription_key, "date": "2026-12-26", "amount_minor": 1200000,
        "currency": "PKR", "kind": "renewal", "date_basis": "estimated",
        "evidence_ids": ["m3"], "cycle_basis": "user_selected",
    }
    assert original["due"] == []
    assert original["totals"]["PKR"]["next_7d_minor"] == 0
    assert list(reviewable_charges(dict(original, due=[estimate]))) == []
    for override in (renewal, cancellation):
        portfolio = build_portfolio([payment, override], AS_OF, TIMEZONE)
        assert estimate_renewal_from_selection(portfolio, subscription_key, "monthly") is None
