from intelligence import extraction_fallback
from intelligence.api import build_portfolio, estimate_renewal_from_selection, extract_events
from intelligence.fictional import AS_OF, TIMEZONE


def message(source, subject, body, *, domain="example.test", received="2026-11-01"):
    return {
        "source_id": source, "subject": subject, "body_text": body,
        "sender_domain": domain, "received_at": f"{received}T08:00:00Z",
    }


def scan(*messages, gemini_fallback=False):
    events = extract_events(messages, gemini_fallback=gemini_fallback)
    return build_portfolio(events, AS_OF, TIMEZONE)


def test_retail_orders_and_editorial_email_do_not_become_subscriptions():
    messages = [
        message("daraz", "Order Being Processed #123", "Payment received. Paid PKR 2,000.", domain="support.daraz.pk"),
        message("shop", "Order #85569 confirmed", "Paid PKR 1,000. Shipping address follows.", domain="t.shopifyemail.com"),
        message("shop2", "Order 9000965787 confirmation", "Paid PKR 1,000.", domain="t.shopifyemail.com"),
        message("news", "What a new IPO means for your Claude bill", "The next charge will be USD 10 on Dec 1, 2026.", domain="datacamp.com"),
    ]
    assert extract_events(messages, gemini_fallback=False) == []


def test_ambiguous_deductions_thirty_days_apart_do_not_create_a_plan_or_due():
    result = scan(
        message("a", "Payment deduction", "Successfully charged PKR 1,200.", received="2026-10-02"),
        message("b", "Payment deduction", "Successfully charged PKR 1,200."),
    )
    assert [row["source_id"] for row in result["needs_confirmation"]] == ["a", "b"]
    assert result["subscriptions"] == result["due"] == []
    assert result["billing_prompts"] == result["totals"] == {}


def test_dated_receipts_for_an_identified_subscription_can_still_estimate_cadence():
    result = scan(
        message("first", "Orbit Reader subscription", "Subscription payment received: USD 8.", received="2026-10-02"),
        message("second", "Orbit Reader subscription", "Subscription payment received: USD 8."),
    )
    due, = result["due"]
    assert (due["date"], due["date_basis"], due["cycle_basis"]) == ("2026-12-01", "estimated", "payment_history")
    assert result["billing_prompts"] == {}
    assert result["totals"]["USD"]["next_7d_minor"] == 0


def test_processor_receipts_use_product_and_keep_genuine_order_subscriptions():
    result = scan(
        message("play", "Your Google Play Order Receipt from Nov 1, 2026",
                "Item: Orbit Reader Plus\nSubscription: Orbit Reader Plus\nPayment successful. Paid USD 8.", domain="google.com"),
        message("shop", "Order #1234 confirmed", "Product: Coffee Club\nMonthly subscription.\nPaid PKR 1,000.",
                domain="t.shopifyemail.com"),
        message("writing", "Your hard work deserves a receipt", "Your subscription payment was successful. Paid USD 8.",
                domain="mail.grammarly.com"),
        message("one-time", "Your Google Play Order Receipt from Nov 1, 2026", "One-time purchase. Paid USD 2.",
                domain="google.com"),
    )
    assert [row["subscription_key"] for row in result["subscriptions"]] == ["coffee-club", "grammarly", "orbit-reader-plus"]
    assert result["billing_prompts"]["orbit-reader-plus"] == {"field": "cycle", "can_estimate_from_payment": True}
    assert result["totals"]["USD"]["paid_minor"] == 1600


def test_google_one_trial_failure_and_suspension_share_a_timeline():
    trial = message("trial", "Your trial for Google One will end on Nov 30, 2026", "Manage your plan.", domain="google.com")
    failed = message("failed", "Payment declined for Google One subscription", "Payment declined. USD 10.",
                     domain="google.com", received="2026-11-02")
    suspended = message("paused", "Google One subscription suspended due to payment issue", "Payment declined.",
                        domain="google.com", received="2026-11-03")
    for evidence in (trial, failed):
        result = scan(evidence)
        assert result["billing_prompts"] == {"google-one": {"field": "cycle", "can_estimate_from_payment": False}}
        assert not any(row["date"] for row in result["due"])
    result = scan(trial, failed, suspended)
    sub, = result["subscriptions"]
    assert (sub["subscription_key"], sub["status"], sub["evidence_ids"]) == (
        "google-one", "suspended", ["failed", "paused", "trial"],
    )
    assert result["due"] == [] and result["billing_prompts"] == {}
    receipt = message("paid", "Google One Subscription", "Your subscription payment was successful. Paid USD 10.",
                      domain="google.com", received="2026-10-28")
    assert estimate_renewal_from_selection(scan(receipt, suspended), "google-one", "monthly") is None


def test_known_cycle_without_billing_date_asks_for_date():
    result = scan(message("receipt", "Reader Club annual subscription", "Your annual subscription payment was successful. Paid USD 12.",
                          received="2024-11-01"))
    assert result["billing_prompts"] == {"reader-club": {"field": "next_charge_date"}}


def test_gemini_can_resolve_ambiguous_receipt_with_a_verified_recurring_charge(monkeypatch):
    monkeypatch.setenv("GOOGLE_API_KEY", "fixture-only")
    receipt = message("odd", "Paper Reader receipt", "Paid USD 5. Billed each month.")
    assert scan(receipt)["subscriptions"] == []

    def response(candidates, key):
        assert len(candidates) == 1
        return [{"id": 0, "cycle_line": "Billed each month.", "amount_line": None}]

    monkeypatch.setattr(extraction_fallback, "_ask", response)
    assert scan(receipt, gemini_fallback=True)["due"][0]["date"] == "2026-12-01"
    unsupported = message("odd", "Paper Reader receipt", "Paid USD 5. Billed once.")
    assert scan(unsupported, gemini_fallback=True)["due"] == []
