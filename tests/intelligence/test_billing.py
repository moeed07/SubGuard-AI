from copy import deepcopy

from intelligence.api import build_portfolio, extract_events
from intelligence.fictional import AS_OF, TIMEZONE, fictional_messages


def portfolio(events):
    return build_portfolio(events, AS_OF, TIMEZONE)


def test_shared_fixture_scans_and_idempotence():
    before = extract_events(fictional_messages())
    after = extract_events(fictional_messages(canceled=True))
    assert [(row["source_id"], row["kind"]) for row in after] == [
        ("m1", "payment"), ("m2", "payment"), ("m3", "payment"), ("m4", "renewal"),
        ("m5", "trial_conversion"), ("m6", "promo"), ("m7", "failed"), ("m8", "cancellation_confirmed"),
    ]
    assert before == after[:-1]
    assert before[0] == {
        "event_id": "m1:0", "source_id": "m1", "received_at": "2026-11-26T08:00:00Z",
        "subscription_key": "writing-plus", "kind": "payment", "currency": "PKR",
        "amount_minor": 200000, "cycle": "monthly", "transaction_ref": "W-101",
        "event_date": AS_OF, "effective_date": None, "next_charge_date": None,
        "date_basis": "unknown",
    }
    assert before[1]["transaction_ref"] == "W-101"
    assert before[1]["amount_minor"] == 200000
    assert portfolio(before)["totals"]["PKR"] == {
        "paid_minor": 1400000, "monthly_equivalent_minor": 300000, "next_7d_minor": 1270000,
    }
    result = portfolio(after)
    assert portfolio(list(reversed(after)) + before) == result
    assert result["totals"]["PKR"] == {
        "paid_minor": 1400000, "monthly_equivalent_minor": 200000, "next_7d_minor": 70000,
    }
    design = next(row for row in result["subscriptions"] if row["subscription_key"] == "design-pro")
    assert design == {
        "subscription_key": "design-pro", "status": "canceled", "paid_through": "2026-12-01",
        "auto_renew": False, "evidence_ids": ["m3", "m4", "m8"],
    }
    assert result["due"][0]["evidence_ids"] == ["m5"]


def test_inclusive_window_duplicates_and_uncertainty():
    receipt = extract_events(fictional_messages())[3]
    dates = [(AS_OF, 300), ("2026-12-03", 400), ("2026-12-04", 500), ("2026-11-29", None)]
    entries = [
        dict(receipt, event_id=f"d{index}:0", source_id=f"d{index}",
             next_charge_date=day, amount_minor=amount)
        for index, (day, amount) in enumerate(dates)
    ]
    entries.append(dict(entries[1], source_id="repeat", event_id="repeat:0"))
    entries.append(dict(entries[0], source_id="estimate", event_id="estimate:0",
                        next_charge_date="2026-11-28", date_basis="estimated"))
    result = portfolio(entries)
    assert result["totals"]["PKR"]["next_7d_minor"] == 700
    assert [row["date_basis"] for row in result["due"]] == [
        "confirmed", "estimated", "confirmed", "confirmed", "confirmed",
    ]
    assert result["due"][3]["evidence_ids"] == ["d1", "repeat"]


def test_currency_payment_identity_and_rounding():
    first = extract_events(fictional_messages())[0]
    repeated_with_different_reference = dict(first, event_id="r:0", source_id="r", transaction_ref="W-102")
    annual = dict(first, event_id="y:0", source_id="y", currency="USD",
                  amount_minor=6, cycle="annual", subscription_key="small-annual")
    other_annual = dict(annual, event_id="z:0", source_id="z", subscription_key="other-annual")
    result = portfolio([first, deepcopy(first), repeated_with_different_reference, annual, other_annual])
    assert result["totals"]["PKR"]["paid_minor"] == 400000
    assert result["totals"]["USD"] == {
        "paid_minor": 12, "monthly_equivalent_minor": 1, "next_7d_minor": 0,
    }
    assert portfolio([annual])["totals"]["USD"]["monthly_equivalent_minor"] == 1


def test_stale_notice_or_duplicate_receipt_does_not_reactivate_canceled_plan():
    events = extract_events(fictional_messages(canceled=True))
    old_receipt, renewal = events[2:4]
    later = {"received_at": "2026-11-29T08:00:00Z"}
    stale = dict(renewal, **later, event_id="stale:0", source_id="stale")
    duplicate = dict(old_receipt, **later, event_id="duplicate:0", source_id="duplicate",
                     event_date="2026-11-29")
    assert portfolio(events + [stale, duplicate])["totals"]["PKR"] == portfolio(events)["totals"]["PKR"]


def test_app_demo_subjects_keep_receipt_and_renewal_on_the_same_plans():
    messages = fictional_messages(canceled=True)
    messages[0]["subject"] = "Writing Plus monthly receipt W-101"
    messages[1]["subject"] = "Duplicate confirmation: Writing Plus W-101"
    messages[3]["subject"] = "Design Pro upcoming annual renewal"
    messages[7]["subject"] = "Design Pro auto-renewal turned OFF"
    events = extract_events(messages)
    assert portfolio(events[:-1])["totals"]["PKR"]["next_7d_minor"] == 1270000
    result = portfolio(events)
    assert result["totals"]["PKR"] == {
        "paid_minor": 1400000, "monthly_equivalent_minor": 200000, "next_7d_minor": 70000,
    }
    assert [row["source_id"] for row in result["timelines"]["writing-plus"]] == ["m1", "m2"]
    assert [row["source_id"] for row in result["timelines"]["design-pro"]] == ["m3", "m4", "m8"]
