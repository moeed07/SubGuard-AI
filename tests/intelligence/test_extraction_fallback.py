from intelligence import extraction_fallback
from intelligence.api import build_portfolio, extract_events
from intelligence.fictional import AS_OF, TIMEZONE


def receipt(body, source="receipt", subject="Orbit Reader"):
    return {
        "source_id": source, "received_at": "2026-11-26T08:00:00Z",
        "sender_domain": "example.test", "subject": subject, "body_text": body,
    }


def test_only_incomplete_billing_reaches_gemini_when_enabled(monkeypatch):
    monkeypatch.setenv("GOOGLE_API_KEY", "fixture-only")
    messages = [
        receipt("Paid USD 8. Auto-renews monthly.", "complete"),
        receipt("Winter sale. Subscribe today to save.", "promo"),
        receipt("Your subscription is canceled.", "canceled"),
        receipt("Payment failed. Total: USD 10.", "failed"),
        receipt(
            "Payment received.\nOrbit Reader (1 month subscription)\nSubtotal: USD 5.00\n"
            "Total: USD 6.00\nOrder number: GPA.1234-5678-9012-34567\nBilling address: 123 Example Lane",
        ),
    ]
    calls = []

    def ask(candidates, key):
        calls.append(candidates)
        assert key == "fixture-only"
        candidate, = candidates
        assert candidate["need_cycle"] and candidate["need_amount"]
        assert candidate["kind"] == "payment"
        assert not any("Example Lane" in line or "GPA." in line for line in candidate["lines"])
        return [{"id": candidate["id"], "cycle_line": "Orbit Reader (1 month subscription)",
                 "amount_line": "Total: USD 6.00"}]

    monkeypatch.setattr(extraction_fallback, "_ask", ask)
    monkeypatch.delenv("SUBGUARD_GEMINI_EXTRACTION", raising=False)
    baseline = extract_events(messages)
    assert calls == []
    assert baseline[-1]["cycle"] is None and baseline[-1]["amount_minor"] is None

    monkeypatch.setenv("SUBGUARD_GEMINI_EXTRACTION", "true")
    updated = extract_events(messages)
    assert len(calls) == 1
    assert updated[:-1] == baseline[:-1]
    event = updated[-1]
    assert event == dict(baseline[-1], cycle="monthly", amount_minor=600)
    due = build_portfolio([event], AS_OF, TIMEZONE)["due"]
    assert [(row["date"], row["date_basis"], row["amount_minor"]) for row in due] == [
        ("2026-12-26", "estimated", 600),
    ]


def test_fallback_rejects_unsubstantiated_cycles_and_amounts(monkeypatch):
    monkeypatch.setenv("GOOGLE_API_KEY", "fixture-only")
    messages = [
        receipt("Payment received.\nOrbit Reader subscription\n1 month free trial\nTotal: $9.99"),
        receipt("Payment received.\nTotal tax: US$ 0.50\nTotal: US$ 6.00\nTotal: US$ 8.00", "conflict"),
        receipt("Paid USD 5.\n1 year subscription", "known"),
    ]
    monkeypatch.setattr(extraction_fallback, "_ask", lambda candidates, key: [
        {"id": 0, "cycle_line": "1 month free trial", "amount_line": "Total: $9.99"},
        {"id": 1, "cycle_line": "Every year", "amount_line": "Total: US$ 6.00"},
        {"id": 2, "cycle_line": "1 year subscription", "amount_line": "Total: US$ 6.00"},
    ])
    event, conflict, known = extract_events(messages, gemini_fallback=True)
    assert (event["cycle"], event["currency"], event["amount_minor"]) == (None, None, None)
    assert (conflict["cycle"], conflict["amount_minor"]) == (None, None)
    assert (known["cycle"], known["amount_minor"]) == ("annual", 500)


def test_fallback_failure_leaves_deterministic_extraction_available(monkeypatch):
    monkeypatch.setenv("GOOGLE_API_KEY", "fixture-only")

    def fail(candidates, key):
        raise TimeoutError

    monkeypatch.setattr(extraction_fallback, "_ask", fail)
    messages = [receipt("Paid USD 9.\nSubscription billed once per month.")]
    assert extract_events(messages, gemini_fallback=True) == extract_events(messages, gemini_fallback=False)
