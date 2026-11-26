"""Deterministic reconciliation for one account's validated events."""
from calendar import monthrange
from collections import defaultdict
from datetime import date, datetime, timedelta
from fractions import Fraction
from zoneinfo import ZoneInfo


def _totals():
    return {"paid_minor": 0, "monthly_equivalent_minor": 0, "next_7d_minor": 0}


def _received(event):
    return datetime.fromisoformat(event["received_at"].replace("Z", "+00:00"))


def _timeline_order(event, zone):
    received = _received(event)
    # Cancellation takes effect for new charges as soon as it is known.
    business_date = event["event_date"] or received.astimezone(zone).date().isoformat()
    return business_date, received, event["event_id"]


def _sources(events):
    return sorted({event["source_id"] for event in events})


def _payment_key(event):
    ref = event["transaction_ref"]
    if ref:
        normalized = ref.strip().upper()
        if normalized:
            return event["subscription_key"], normalized, event["currency"], event["amount_minor"]
    return event["event_id"]


def _round_half_up(amount):
    return int(amount + Fraction(1, 2))


def _plan_billing(timeline, stop):
    # A subsequent receipt explicitly documenting renewal can reactivate a plan.
    # A re-read renewal notice alone cannot reverse a confirmed cancellation.
    earlier_payments = {
        _payment_key(event) for event in timeline
        if stop and event["kind"] == "payment" and _received(event) <= _received(stop)
    }
    paid_plans = [
        event for event in timeline
        if event["kind"] == "payment"
        and event["cycle"] in {"monthly", "annual"}
        and event["amount_minor"] is not None
        and event["currency"]
        and (stop is None or _received(event) > _received(stop) and event["event_date"]
             and event["event_date"] > _received(stop).date().isoformat()
             and _payment_key(event) not in earlier_payments)
    ]
    return paid_plans[-1] if paid_plans else None


def _due_entries(timeline, stop, plan, as_of):
    charges = defaultdict(list)
    for event in timeline:
        if event["kind"] not in {"renewal", "trial_conversion"}:
            continue
        if stop and (not plan or _received(event) <= _received(stop)):
            continue
        charge_date = event["next_charge_date"]
        if charge_date and charge_date < as_of:
            continue
        key = (event["kind"], charge_date, event["currency"])
        charges[key].append(event)
    for (kind, charge_date, currency), notices in charges.items():
        amounts = {event["amount_minor"] for event in notices if event["amount_minor"] is not None}
        amount = next(iter(amounts)) if len(amounts) == 1 else None
        evidence = [event for event in notices if event["date_basis"] == "confirmed"]
        basis = "confirmed" if charge_date and evidence else (
            "estimated" if charge_date and any(event["date_basis"] == "estimated" for event in notices) else "unknown"
        )
        # An estimate can inform the display but cannot establish a collected or confirmed amount.
        if evidence and not any(event["amount_minor"] == amount for event in evidence):
            amount = None
        yield {
            "subscription_key": notices[0]["subscription_key"],
            "date": charge_date,
            "amount_minor": amount,
            "currency": currency,
            "kind": kind,
            "date_basis": basis,
            "evidence_ids": _sources(evidence or notices),
        }


def _estimated_renewal(plan, timeline, pending, as_of):
    if not plan or any(row["kind"] == "renewal" and row["date"] for row in pending):
        return None

    # A later copy of the same receipt must not shift the estimate.
    payment_key = _payment_key(plan)
    dated_copies = [
        event for event in timeline
        if event["kind"] == "payment" and event["event_date"] and _payment_key(event) == payment_key
    ]
    if not dated_copies:
        return None
    anchor = min(dated_copies, key=lambda event: (_received(event), event["event_id"]))
    paid_on = date.fromisoformat(anchor["event_date"])
    if paid_on.isoformat() > as_of:
        return None
    months = 12 if plan["cycle"] == "annual" else 1
    year, month_index = divmod(paid_on.year * 12 + paid_on.month - 1 + months, 12)
    month = month_index + 1
    next_date = date(year, month, min(paid_on.day, monthrange(year, month)[1])).isoformat()
    if next_date < as_of:
        # A stale receipt alone does not establish that further cycles occurred.
        return None
    return {
        "subscription_key": plan["subscription_key"],
        "date": next_date,
        "amount_minor": plan["amount_minor"],
        "currency": plan["currency"],
        "kind": "renewal",
        "date_basis": "estimated",
        "evidence_ids": _sources([plan, anchor]),
    }


def build_portfolio(events, as_of, timezone):
    """Return the shared JSON-compatible portfolio without any network calls."""
    day = date.fromisoformat(as_of)
    last = (day + timedelta(days=7)).isoformat()
    zone = ZoneInfo(timezone)
    totals = defaultdict(_totals)
    monthly = defaultdict(Fraction)
    timelines = defaultdict(list)
    subscriptions, due = [], []
    paid = set()
    unique = {event["event_id"]: event for event in events if event["kind"] != "promo"}
    for event in sorted(unique.values(), key=lambda row: _timeline_order(row, zone)):
        timelines[event["subscription_key"]].append(dict(event))
        if event["kind"] == "payment" and event["currency"] and event["amount_minor"] is not None:
            key = _payment_key(event)
            if key not in paid:
                totals[event["currency"]]["paid_minor"] += event["amount_minor"]
                paid.add(key)

    for key, timeline in sorted(timelines.items()):
        stop = max(
            (event for event in timeline if event["kind"] == "cancellation_confirmed"),
            key=lambda event: (_received(event), event["event_id"]),
            default=None,
        )
        plan = _plan_billing(timeline, stop)
        pending = list(_due_entries(timeline, stop, plan, as_of))
        estimate = _estimated_renewal(plan, timeline, pending, as_of)
        if estimate:
            pending = [row for row in pending if row["kind"] != "renewal" or row["date"]]
            pending.append(estimate)
        due.extend(pending)
        trial = any(row["kind"] == "trial_conversion" for row in pending)
        renewal = any(row["kind"] == "renewal" for row in pending)
        cancellation_requested = any(event["kind"] == "cancellation_requested" for event in timeline)
        if plan:
            recurring_price = plan
            if not stop:
                # A current notice can supersede a historical price on a documented paid plan.
                recurring_price = next(
                    (event for event in reversed(timeline)
                     if event["kind"] == "renewal" and event["cycle"] == plan["cycle"]
                     and event["currency"] == plan["currency"] and event["amount_minor"] is not None
                     and event["next_charge_date"] and event["next_charge_date"] >= as_of),
                    plan,
                )
            monthly[recurring_price["currency"]] += Fraction(
                recurring_price["amount_minor"], 12 if recurring_price["cycle"] == "annual" else 1
            )
        if stop and not plan:
            status, auto_renew = "canceled", False
        elif cancellation_requested and not stop:
            status, auto_renew = "cancellation_requested", True if plan or renewal else None
        elif plan or renewal:
            status, auto_renew = "active", True
        elif trial:
            status, auto_renew = "trial", None
        else:
            status, auto_renew = "unknown", None
        subscriptions.append({
            "subscription_key": key,
            "status": status,
            "paid_through": stop["effective_date"] if stop and not plan else None,
            "auto_renew": auto_renew,
            "evidence_ids": _sources(timeline),
        })

    for currency, amount in monthly.items():
        totals[currency]["monthly_equivalent_minor"] = _round_half_up(amount)
    for row in due:
        if row["currency"]:
            currency_totals = totals[row["currency"]]
            if (
                row["date_basis"] == "confirmed" and row["date"]
                and as_of <= row["date"] <= last and row["amount_minor"] is not None
            ):
                currency_totals["next_7d_minor"] += row["amount_minor"]

    return {
        "as_of": as_of,
        "timezone": timezone,
        "totals": dict(sorted(totals.items())),
        "subscriptions": subscriptions,
        "due": sorted(due, key=lambda row: (
            row["date"] or "9999-12-31", row["subscription_key"], row["kind"], row["currency"] or ""
        )),
        "timelines": dict(sorted(timelines.items())),
    }
