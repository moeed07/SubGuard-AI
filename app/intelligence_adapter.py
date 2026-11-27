"""Adapter to Ahmed's intelligence package (never implements a competing version)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Optional
from zoneinfo import ZoneInfo

from app.gmail_client import ScanOutput
from app.storage import LocalStore


def auto_schedule_5d_and_1d_reminders(
    store: LocalStore,
    account_id: str,
    subscription_key: str,
    target_date: Optional[str],
    timezone_name: str = "Asia/Karachi",
) -> None:
    """Automatically schedule 5-day before and 1-day before reminders when in the future."""
    if not target_date:
        return
    try:
        tz = ZoneInfo(timezone_name)
        target_day = datetime.strptime(target_date, "%Y-%m-%d").replace(tzinfo=tz)
    except Exception:
        return
    now_utc = datetime.now(timezone.utc)
    for days_before, rtype in ((5, "five_days"), (1, "one_day")):
        local_dt = (target_day - timedelta(days=days_before)).replace(
            hour=9, minute=0, second=0, microsecond=0
        )
        due_utc = local_dt.astimezone(timezone.utc)
        if due_utc > now_utc:
            store.create_reminder_job(
                account_id=account_id,
                subscription_key=subscription_key,
                reminder_type=rtype,
                due_at=due_utc.strftime("%Y-%m-%dT%H:%M:%SZ"),
                target_date=target_date,
            )


class IntelligenceUnavailableError(RuntimeError):
    """Raised when Ahmed's intelligence.api package is not yet available."""


@dataclass
class IntelligenceBackend:
    extract_events: Callable[[list[dict[str, Any]]], list[dict[str, Any]]]
    build_portfolio: Callable[[list[dict[str, Any]], str, str], dict[str, Any]]
    run_review: Callable[..., Any]


def get_default_intelligence() -> IntelligenceBackend:
    try:
        from intelligence import api as intel_api  # type: ignore
    except ImportError as exc:
        raise IntelligenceUnavailableError(
            "intelligence.api is not available yet. Merge feat/ahmed-agent or run tests with a mock backend."
        ) from exc

    return IntelligenceBackend(
        extract_events=intel_api.extract_events,
        build_portfolio=intel_api.build_portfolio,
        run_review=intel_api.run_review,
    )


async def process_scan_output(
    store: LocalStore,
    account_id: str,
    scan_output: ScanOutput,
    as_of: str,
    timezone_name: str,
    intelligence: Optional[IntelligenceBackend] = None,
    goal: str = "Find what needs attention before my next charge.",
) -> dict[str, Any]:
    """Run extract_events -> upsert -> build_portfolio -> run_review for one account."""
    scan_version = store.next_scan_version(account_id)

    if scan_output.error:
        store.update_scan_status(
            account_id,
            scan_version,
            "failed",
            partial=True,
            scan_error=scan_output.error,
        )
        return {"scan_version": scan_version, "scan_status": "failed", "error": scan_output.error}

    backend = intelligence or get_default_intelligence()

    if scan_output.evidence_records:
        store.upsert_evidence(account_id, scan_output.evidence_records)

    extracted = backend.extract_events(scan_output.messages) if scan_output.messages else []
    if scan_output.messages:
        scanned_sources = [m["source_id"] for m in scan_output.messages]
        store.replace_events_for_sources(account_id, scanned_sources, extracted)

    all_events = store.list_events(account_id)

    if not scan_output.messages and not all_events:
        store.update_scan_status(account_id, scan_version, "empty", partial=scan_output.partial)
        return {"scan_version": scan_version, "scan_status": "empty"}

    portfolio = backend.build_portfolio(all_events, as_of, timezone_name)
    saved_portfolio = store.save_portfolio(account_id, scan_version, portfolio)
    if not saved_portfolio:
        return {"scan_version": scan_version, "scan_status": "stale"}

    # Cancel pending reminders for any subscription that no longer has an active renewal/due charge
    due_keys = {d.get("subscription_key") for d in portfolio.get("due", [])}
    for sub in portfolio.get("subscriptions", []):
        skey = sub.get("subscription_key")
        if skey and (sub.get("auto_renew") is False or sub.get("status") in ("canceled", "cancelled")) and skey not in due_keys:
            store.cancel_reminders_for_subscription(account_id, skey)

    # Automatically schedule 5-day and 1-day reminders for upcoming renewals/charges
    for due_item in portfolio.get("due", []):
        skey = due_item.get("subscription_key")
        tdate = due_item.get("date")
        if skey and tdate:
            auto_schedule_5d_and_1d_reminders(store, account_id, skey, tdate, timezone_name)

    if not all_events:
        store.update_scan_status(account_id, scan_version, "zero_results", partial=scan_output.partial)
        return {"scan_version": scan_version, "scan_status": "zero_results"}

    scan_status = "partial" if scan_output.partial else "ok"
    store.update_scan_status(account_id, scan_version, scan_status, partial=scan_output.partial)

    valid_subs = {s.get("subscription_key", "") for s in portfolio.get("subscriptions", [])}
    valid_subs.update(due_keys)
    valid_evidence = {e["source_id"] for e in store.list_evidence(account_id)}

    try:
        review_result = await backend.run_review(portfolio, goal)
    except Exception as exc:
        review_result = {
            "status": "failed",
            "summary": f"Review agent failed: {exc}",
            "items": [],
            "trace": [],
        }

    store.commit_review(account_id, scan_version, review_result, valid_subs, valid_evidence)
    return {"scan_version": scan_version, "scan_status": scan_status}
