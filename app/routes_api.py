"""Dashboard, refresh, reminders, evidence, delete, and fictional demo routes."""

from __future__ import annotations

import secrets
import time
from datetime import datetime, timedelta, timezone
from typing import Any, Optional
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Body, Request, Response
from fastapi.responses import JSONResponse, RedirectResponse

from app.config import Settings
from app.gmail_client import ScanOutput, fetch_gmail_profile, revoke_google_token, scan_gmail_messages
from app.intelligence_adapter import (
    IntelligenceUnavailableError,
    auto_schedule_5d_and_1d_reminders,
    process_scan_output,
)
from app.mailer import send_reminder_email
from app.routes_auth import _get_or_create_session_id, _set_session_cookie
from app.security import SecurityManager
from app.storage import LocalStore

router = APIRouter()

DEMO_AS_OF = "2026-11-26"
DEMO_TIMEZONE = "Asia/Karachi"


def build_demo_fixture(include_m8: bool = False) -> ScanOutput:
    """Fictional §3 fixture for 'Explore fictional example'."""
    messages = [
        {
            "source_id": "m1",
            "received_at": "2026-11-26T08:00:00Z",
            "sender_domain": "writingplus.example",
            "subject": "Writing Plus monthly receipt W-101",
            "body_text": "Writing Plus monthly subscription. Paid PKR 2,000 today. Receipt W-101. Auto-renews monthly.",
        },
        {
            "source_id": "m2",
            "received_at": "2026-11-26T08:05:00Z",
            "sender_domain": "writingplus.example",
            "subject": "Duplicate confirmation: Writing Plus W-101",
            "body_text": "Duplicate confirmation of the same Writing Plus payment, W-101, PKR 2,000.",
        },
        {
            "source_id": "m3",
            "received_at": "2026-11-26T08:10:00Z",
            "sender_domain": "designpro.example",
            "subject": "Design Pro annual receipt D-201",
            "body_text": "Design Pro annual subscription. Paid PKR 12,000. Receipt D-201. Auto-renews annually.",
        },
        {
            "source_id": "m4",
            "received_at": "2026-11-26T08:15:00Z",
            "sender_domain": "designpro.example",
            "subject": "Design Pro upcoming annual renewal",
            "body_text": "Design Pro annual renewal of PKR 12,000 is scheduled on 2026-12-01.",
        },
        {
            "source_id": "m5",
            "received_at": "2026-11-26T08:20:00Z",
            "sender_domain": "sketchtrial.example",
            "subject": "Sketch Trial converts soon",
            "body_text": "Sketch Trial converts to a paid plan on 2026-11-29. First charge PKR 700.",
        },
        {
            "source_id": "m6",
            "received_at": "2026-11-26T08:25:00Z",
            "sender_domain": "promo.example",
            "subject": "Special promotional offer for a new plan",
            "body_text": "Upgrade today and save 40% on our new Pro Bundle!",
        },
        {
            "source_id": "m7",
            "received_at": "2026-11-26T08:30:00Z",
            "sender_domain": "designpro.example",
            "subject": "Failed debit notice",
            "body_text": "Your recent debit attempt of PKR 500 failed. No charge was collected.",
        },
    ]
    if include_m8:
        messages.append(
            {
                "source_id": "m8",
                "received_at": "2026-11-26T10:00:00Z",
                "sender_domain": "designpro.example",
                "subject": "Design Pro auto-renewal turned OFF",
                "body_text": "Design Pro auto-renewal is OFF. Your access ends 2026-12-01. You will not be billed on 2026-12-01.",
            }
        )
    evidence = [
        {
            "source_id": m["source_id"],
            "gmail_message_id": f"demo_{m['source_id']}",
            "received_at": m["received_at"],
            "sender_domain": m["sender_domain"],
            "subject": m["subject"],
        }
        for m in messages
    ]
    return ScanOutput(messages=messages, evidence_records=evidence, partial=False)


def _require_auth_and_csrf(request: Request) -> tuple[Optional[dict[str, Any]], Optional[JSONResponse]]:
    security: SecurityManager = request.app.state.security
    payload = security.verify_session_token(request.cookies.get(SecurityManager.SESSION_COOKIE_NAME))
    if not payload or not payload.get("sid") or not payload.get("aid"):
        return None, JSONResponse({"detail": "Not authenticated"}, status_code=401)
    csrf = request.headers.get("X-CSRF-Token")
    if not security.verify_csrf_token(payload["sid"], csrf):
        return None, JSONResponse({"detail": "Invalid CSRF token"}, status_code=403)
    return payload, None


def deliver_due_jobs_with_email(app: Any, now_iso: Optional[str] = None) -> int:
    """Deliver due reminder jobs and send Gmail reminder emails when SMTP is configured."""
    store: LocalStore = app.state.store
    settings: Settings = app.state.settings
    security: SecurityManager = app.state.security

    def _on_deliver(job: dict[str, Any]) -> None:
        acct = store.get_account(job["account_id"])
        if not acct or not acct.get("encrypted_email"):
            print(f"[SubGuard SMTP skipped] No email saved for account {job['account_id']}; reconnect Gmail.")
            return
        to_email = security.decrypt_token(acct["encrypted_email"])
        if to_email:
            ok = send_reminder_email(
                settings=settings,
                to_email=to_email,
                subscription_key=job["subscription_key"],
                target_date=job["target_date"],
                reminder_type=job["reminder_type"],
            )
            if ok:
                print(f"[SubGuard SMTP sent] {job['reminder_type']} reminder sent for {job['subscription_key']}")
            elif not settings.smtp_configured:
                print("[SubGuard SMTP skipped] SMTP_EMAIL or SMTP_APP_PASSWORD is missing in .env")

    return store.deliver_due_jobs(now_iso=now_iso, on_deliver=_on_deliver)


@router.get("/api/dashboard")
async def get_dashboard(request: Request) -> Response:
    settings: Settings = request.app.state.settings
    security: SecurityManager = request.app.state.security
    store: LocalStore = request.app.state.store

    session_id, payload = _get_or_create_session_id(request, security)
    csrf_token = security.create_csrf_token(session_id)
    account_id = payload.get("aid") if payload else None

    if not account_id or not store.get_account(account_id):
        resp = JSONResponse(
            {
                "connected": False,
                "oauth_configured": settings.oauth_configured,
                "smtp_configured": settings.smtp_configured,
                "csrf_token": csrf_token,
            }
        )
        _set_session_cookie(resp, security, settings, session_id)
        return resp

    acct = store.get_account(account_id)
    if not acct.get("is_demo"):
        deliver_due_jobs_with_email(request.app)
    portfolio = store.get_portfolio(account_id)
    review = store.get_review(account_id)
    reminders = store.list_reminders(account_id)
    notifications = store.list_notifications(account_id)
    evidence = [
        {
            "source_id": e["source_id"],
            "received_at": e["received_at"],
            "sender_domain": e["sender_domain"],
            "subject": e["subject"],
        }
        for e in store.list_evidence(account_id)
    ]
    user_estimates = _user_cycle_estimates(store, account_id, portfolio)

    return JSONResponse(
        {
            "connected": True,
            "is_demo": bool(acct.get("is_demo")),
            "demo_date": DEMO_AS_OF if acct.get("is_demo") else None,
            "timezone": DEMO_TIMEZONE,
            "oauth_configured": settings.oauth_configured,
            "smtp_configured": settings.smtp_configured,
            "csrf_token": csrf_token,
            "scan_status": acct.get("scan_status", "never"),
            "partial": bool(acct.get("partial")),
            "scan_error": acct.get("scan_error"),
            "last_successful_scan": acct.get("last_successful_scan"),
            "portfolio": portfolio,
            "review": review,
            "reminders": reminders,
            "notifications": notifications,
            "evidence": evidence,
            "user_estimates": user_estimates,
        }
    )


def _user_cycle_estimates(
    store: LocalStore, account_id: str, portfolio: Optional[dict[str, Any]]
) -> dict[str, Any]:
    """Re-apply each saved Monthly/Annual or next_charge_date choice."""
    details_map = store.list_cycle_choice_details(account_id)
    if not details_map or not portfolio:
        return {}
    try:
        from intelligence.api import estimate_renewal_from_selection  # type: ignore
    except ImportError:
        estimate_renewal_from_selection = None
    known = {s.get("subscription_key") for s in portfolio.get("subscriptions", [])}
    timelines = portfolio.get("timelines") or {}
    result: dict[str, Any] = {}
    for sub_key, info in details_map.items():
        if sub_key not in known:
            continue
        cycle = info.get("cycle")
        custom_date = info.get("next_charge_date")
        estimate = None
        if cycle and estimate_renewal_from_selection is not None:
            try:
                estimate = estimate_renewal_from_selection(portfolio, sub_key, cycle)
            except Exception:
                estimate = None
        if custom_date:
            tl = timelines.get(sub_key) or []
            last_ev = next((e for e in reversed(tl) if e.get("amount_minor") is not None), tl[-1] if tl else {})
            estimate = {
                "subscription_key": sub_key,
                "date": custom_date,
                "amount_minor": last_ev.get("amount_minor") if estimate is None else estimate.get("amount_minor"),
                "currency": last_ev.get("currency") if estimate is None else estimate.get("currency"),
                "kind": "renewal",
                "date_basis": "estimated",
                "cycle_basis": "user_selected",
            }
        result[sub_key] = {"cycle": cycle, "next_charge_date": custom_date, "estimate": estimate}
    return result


@router.post("/api/refresh")
async def refresh_scan(request: Request, body: Optional[dict[str, Any]] = Body(default=None)) -> Response:
    payload, err = _require_auth_and_csrf(request)
    if err:
        return err

    settings: Settings = request.app.state.settings
    security: SecurityManager = request.app.state.security
    store: LocalStore = request.app.state.store
    account_id = payload["aid"]
    acct = store.get_account(account_id)
    if not acct:
        return JSONResponse({"detail": "Account not found"}, status_code=404)

    intel = getattr(request.app.state, "intelligence", None)
    if acct.get("is_demo"):
        include_m8 = bool((body or {}).get("include_m8", False))
        scan_out = build_demo_fixture(include_m8=include_m8)
        as_of = DEMO_AS_OF
    else:
        enc_token = acct.get("encrypted_token")
        expires_at = int(acct.get("token_expires_at") or 0)
        access_token = security.decrypt_token(enc_token) if enc_token else None
        if not access_token or expires_at <= int(time.time()):
            return JSONResponse(
                {"detail": "Gmail session expired. Please reconnect Gmail.", "reconnect_required": True},
                status_code=401,
            )
        if not acct.get("encrypted_email"):
            try:
                profile = await fetch_gmail_profile(access_token)
                email = profile.get("emailAddress", "")
                if email:
                    store.upsert_account(account_id, encrypted_email=security.encrypt_token(email))
            except Exception:
                pass
        existing_portfolio = store.get_portfolio(account_id)
        needs_reprocess = (
            bool((body or {}).get("reprocess", False))
            or store.clear_legacy_events_without_basis(account_id)
            or (existing_portfolio is not None and "billing_prompts" not in existing_portfolio)
        )
        if needs_reprocess:
            store.clear_all_events_for_reprocess(account_id)
        known_ids = set() if needs_reprocess else {e["gmail_message_id"] for e in store.list_evidence(account_id)}
        scan_out = await scan_gmail_messages(
            access_token=access_token,
            account_id=account_id,
            max_pages=settings.gmail_max_pages,
            max_messages=settings.gmail_max_messages,
            known_message_ids=known_ids,
        )
        as_of = datetime.now(ZoneInfo(DEMO_TIMEZONE)).strftime("%Y-%m-%d")

    try:
        result = await process_scan_output(
            store=store,
            account_id=account_id,
            scan_output=scan_out,
            as_of=as_of,
            timezone_name=DEMO_TIMEZONE,
            intelligence=intel,
        )
        return JSONResponse({"ok": True, **result})
    except IntelligenceUnavailableError as exc:
        return JSONResponse({"detail": str(exc)}, status_code=503)


@router.post("/api/reminders")
async def create_reminder(request: Request, body: dict[str, Any] = Body(...)) -> Response:
    payload, err = _require_auth_and_csrf(request)
    if err:
        return err

    store: LocalStore = request.app.state.store
    account_id = payload["aid"]
    sub_key = (body.get("subscription_key") or "").strip()
    mode = (body.get("mode") or "default").strip()
    if mode not in ("default", "one_day", "five_days", "one_minute"):
        return JSONResponse({"detail": "Invalid reminder mode"}, status_code=400)

    portfolio = store.get_portfolio(account_id)
    if not portfolio:
        return JSONResponse({"detail": "No active portfolio found"}, status_code=400)

    sub_entry = next(
        (s for s in portfolio.get("subscriptions", []) if s.get("subscription_key") == sub_key),
        None,
    )
    if not sub_entry or sub_entry.get("auto_renew") is False or sub_entry.get("status") in ("canceled", "cancelled"):
        return JSONResponse(
            {"detail": "Reminders cannot be scheduled for a canceled or non-renewing subscription."},
            status_code=400,
        )

    due_target = None
    for item in portfolio.get("due", []):
        if item.get("subscription_key") == sub_key and item.get("date"):
            due_target = item
            break
    if not due_target:
        user_est = _user_cycle_estimates(store, account_id, portfolio).get(sub_key, {}).get("estimate")
        if user_est and user_est.get("date"):
            due_target = user_est

    if not due_target:
        return JSONResponse(
            {"detail": "Reminders can only be scheduled for a subscription with an upcoming renewal date."},
            status_code=400,
        )

    target_date = due_target["date"]
    now_utc = datetime.now(timezone.utc)

    if mode == "one_minute":
        due_at_utc = now_utc + timedelta(minutes=1)
    else:
        days_before = 5 if mode == "five_days" else 1
        karachi_tz = ZoneInfo(DEMO_TIMEZONE)
        target_day = datetime.strptime(target_date, "%Y-%m-%d").replace(tzinfo=karachi_tz)
        default_local = (target_day - timedelta(days=days_before)).replace(hour=9, minute=0, second=0, microsecond=0)
        due_at_utc = default_local.astimezone(timezone.utc)
        if due_at_utc <= now_utc:
            return JSONResponse(
                {
                    "detail": f"Reminder time ({days_before} day(s) before at 09:00 Asia/Karachi) is already past. Review now or use the 1-minute test option.",
                    "already_past": True,
                },
                status_code=409,
            )

    job = store.create_reminder_job(
        account_id=account_id,
        subscription_key=sub_key,
        reminder_type=mode,
        due_at=due_at_utc.strftime("%Y-%m-%dT%H:%M:%SZ"),
        target_date=target_date,
    )
    return JSONResponse({"ok": True, "job": job})


@router.delete("/api/data")
async def delete_my_data(request: Request) -> Response:
    payload, err = _require_auth_and_csrf(request)
    if err:
        return err

    security: SecurityManager = request.app.state.security
    store: LocalStore = request.app.state.store
    account_id = payload["aid"]

    acct = store.get_account(account_id)
    if acct and acct.get("encrypted_token"):
        token = security.decrypt_token(acct["encrypted_token"])
        if token:
            await revoke_google_token(token)

    store.delete_account_data(account_id)
    resp = JSONResponse({"ok": True, "deleted": True})
    resp.delete_cookie(SecurityManager.SESSION_COOKIE_NAME, path="/")
    return resp


@router.post("/demo/start")
async def start_demo(request: Request, body: Optional[dict[str, Any]] = Body(default=None)) -> Response:
    settings: Settings = request.app.state.settings
    security: SecurityManager = request.app.state.security
    store: LocalStore = request.app.state.store

    session_id, _ = _get_or_create_session_id(request, security)
    demo_account_id = f"acct_demo_{secrets.token_hex(8)}"
    store.upsert_account(demo_account_id, is_demo=True)

    include_m8 = bool((body or {}).get("include_m8", False))
    scan_out = build_demo_fixture(include_m8=include_m8)
    intel = getattr(request.app.state, "intelligence", None)

    try:
        await process_scan_output(
            store=store,
            account_id=demo_account_id,
            scan_output=scan_out,
            as_of=DEMO_AS_OF,
            timezone_name=DEMO_TIMEZONE,
            intelligence=intel,
        )
    except IntelligenceUnavailableError as exc:
        return JSONResponse({"detail": str(exc)}, status_code=503)

    resp = JSONResponse({"ok": True, "account_id": demo_account_id, "demo_date": DEMO_AS_OF})
    _set_session_cookie(resp, security, settings, session_id, account_id=demo_account_id, is_demo=True)
    return resp


@router.get("/api/evidence/{source_id}")
async def get_evidence_link(source_id: str, request: Request) -> Response:
    security: SecurityManager = request.app.state.security
    store: LocalStore = request.app.state.store

    payload = security.verify_session_token(request.cookies.get(SecurityManager.SESSION_COOKIE_NAME))
    if not payload or not payload.get("aid"):
        return JSONResponse({"detail": "Not authenticated"}, status_code=401)

    account_id = payload["aid"]
    ev = store.get_evidence(account_id, source_id)
    if not ev:
        return JSONResponse({"detail": "Evidence not found"}, status_code=404)

    msg_id = ev["gmail_message_id"]
    if msg_id.startswith("demo_"):
        return JSONResponse(
            {
                "source_id": ev["source_id"],
                "demo": True,
                "received_at": ev["received_at"],
                "sender_domain": ev["sender_domain"],
                "subject": ev["subject"],
            }
        )
    return RedirectResponse(url=f"https://mail.google.com/mail/u/0/#all/{msg_id}", status_code=302)


@router.post("/api/cycle-choice")
async def save_cycle_choice(request: Request, body: dict[str, Any] = Body(...)) -> Response:
    """Persist the user's Monthly/Annual or next_charge_date answer for a subscription."""
    payload, err = _require_auth_and_csrf(request)
    if err:
        return err

    store: LocalStore = request.app.state.store
    account_id = payload["aid"]
    portfolio = store.get_portfolio(account_id)
    if not portfolio:
        return JSONResponse({"detail": "No active portfolio found"}, status_code=400)

    sub_key = (body.get("subscription_key") or "").strip()
    known = {s.get("subscription_key") for s in portfolio.get("subscriptions", [])}
    if sub_key not in known:
        return JSONResponse({"detail": "Unknown subscription"}, status_code=404)

    cycle = (body.get("cycle") or "").strip().lower()
    next_charge_date = (body.get("next_charge_date") or "").strip() or None
    if cycle == "clear":
        store.clear_cycle_choice(account_id, sub_key)
        return JSONResponse({"ok": True, "cleared": True})
    if cycle and cycle not in ("monthly", "annual"):
        return JSONResponse({"detail": "Cycle must be monthly or annual"}, status_code=400)
    if next_charge_date:
        try:
            datetime.strptime(next_charge_date, "%Y-%m-%d")
        except ValueError:
            return JSONResponse({"detail": "Date must be YYYY-MM-DD"}, status_code=400)
    if not cycle and not next_charge_date:
        return JSONResponse({"detail": "Provide cycle or next_charge_date"}, status_code=400)

    store.set_cycle_choice(account_id, sub_key, cycle, next_charge_date=next_charge_date)
    entry = _user_cycle_estimates(store, account_id, portfolio).get(
        sub_key, {"cycle": cycle or None, "next_charge_date": next_charge_date, "estimate": None}
    )
    acct = store.get_account(account_id)
    est = entry.get("estimate")
    if acct and not acct.get("is_demo") and est and est.get("date"):
        auto_schedule_5d_and_1d_reminders(store, account_id, sub_key, est["date"], DEMO_TIMEZONE)
    return JSONResponse({"ok": True, **entry})


@router.post("/api/confirm-subscription")
async def confirm_subscription_source(request: Request, body: dict[str, Any] = Body(...)) -> Response:
    """Confirm or dismiss an uncertain billing email from portfolio.needs_confirmation."""
    payload, err = _require_auth_and_csrf(request)
    if err:
        return err

    store: LocalStore = request.app.state.store
    account_id = payload["aid"]
    acct = store.get_account(account_id)
    portfolio = store.get_portfolio(account_id)
    if not acct or not portfolio:
        return JSONResponse({"detail": "No active portfolio found"}, status_code=400)

    source_id = (body.get("source_id") or "").strip()
    pending_sources = {item.get("source_id") for item in portfolio.get("needs_confirmation", [])}
    if not source_id or source_id not in pending_sources:
        return JSONResponse({"detail": "Unknown confirmation source"}, status_code=404)

    is_sub = bool(body.get("is_subscription", False))
    store.set_source_subscription_basis(
        account_id, source_id, "subscription" if is_sub else "one_time"
    )

    from app.intelligence_adapter import get_default_intelligence

    intel = getattr(request.app.state, "intelligence", None) or get_default_intelligence()
    all_events = store.list_events(account_id)
    as_of = portfolio.get("as_of") or datetime.now(ZoneInfo(DEMO_TIMEZONE)).strftime("%Y-%m-%d")
    new_portfolio = intel.build_portfolio(all_events, as_of, DEMO_TIMEZONE)
    ver = int(acct.get("scan_version") or 1)
    store.save_portfolio(account_id, ver, new_portfolio)
    if is_sub and not acct.get("is_demo"):
        for due_item in new_portfolio.get("due", []):
            if due_item.get("subscription_key") and due_item.get("date"):
                auto_schedule_5d_and_1d_reminders(
                    store, account_id, due_item["subscription_key"], due_item["date"], DEMO_TIMEZONE
                )
    return JSONResponse({"ok": True, "is_subscription": is_sub})


@router.post("/api/reminders/deliver")
async def trigger_deliver_due_reminders(request: Request) -> Response:
    _, err = _require_auth_and_csrf(request)
    if err:
        return err
    delivered = deliver_due_jobs_with_email(request.app)
    return JSONResponse({"ok": True, "delivered": delivered})
