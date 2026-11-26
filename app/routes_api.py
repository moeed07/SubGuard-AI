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
from app.gmail_client import ScanOutput, revoke_google_token, scan_gmail_messages
from app.intelligence_adapter import IntelligenceUnavailableError, process_scan_output
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
                "csrf_token": csrf_token,
            }
        )
        _set_session_cookie(resp, security, settings, session_id)
        return resp

    acct = store.get_account(account_id)
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

    return JSONResponse(
        {
            "connected": True,
            "is_demo": bool(acct.get("is_demo")),
            "demo_date": DEMO_AS_OF if acct.get("is_demo") else None,
            "timezone": DEMO_TIMEZONE,
            "oauth_configured": settings.oauth_configured,
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
        }
    )


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
        scan_out = await scan_gmail_messages(
            access_token=access_token,
            account_id=account_id,
            max_pages=settings.gmail_max_pages,
            max_messages=settings.gmail_max_messages,
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
    if mode not in ("default", "one_minute"):
        return JSONResponse({"detail": "Invalid reminder mode"}, status_code=400)

    portfolio = store.get_portfolio(account_id)
    if not portfolio:
        return JSONResponse({"detail": "No active portfolio found"}, status_code=400)

    confirmed_due = None
    for item in portfolio.get("due", []):
        if item.get("subscription_key") == sub_key and item.get("date_basis") == "confirmed":
            confirmed_due = item
            break

    if not confirmed_due:
        return JSONResponse(
            {"detail": "Reminders can only be scheduled for a confirmed upcoming charge."},
            status_code=400,
        )

    target_date = confirmed_due["date"]
    now_utc = datetime.now(timezone.utc)

    if mode == "one_minute":
        due_at_utc = now_utc + timedelta(minutes=1)
    else:
        karachi_tz = ZoneInfo(DEMO_TIMEZONE)
        target_day = datetime.strptime(target_date, "%Y-%m-%d").replace(tzinfo=karachi_tz)
        default_local = (target_day - timedelta(days=1)).replace(hour=9, minute=0, second=0, microsecond=0)
        due_at_utc = default_local.astimezone(timezone.utc)
        if due_at_utc <= now_utc:
            return JSONResponse(
                {
                    "detail": "Default reminder time (day before at 09:00 Asia/Karachi) is already past. Review now or use the 1-minute test option.",
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


@router.post("/api/plan-lookup")
async def public_plan_lookup(request: Request, body: dict[str, Any] = Body(...)) -> Response:
    _, err = _require_auth_and_csrf(request)
    if err:
        return err

    from intelligence.api import lookup_public_plan  # type: ignore

    result = await lookup_public_plan(
        product=(body.get("product") or "").strip(),
        plan=(body.get("plan") or "").strip(),
        storefront=(body.get("storefront") or "provider").strip(),
        market=(body.get("market") or "PK").strip(),
    )
    return JSONResponse(result)


@router.post("/api/plan-cycle-estimate")
async def plan_cycle_estimate(request: Request, body: dict[str, Any] = Body(...)) -> Response:
    payload, err = _require_auth_and_csrf(request)
    if err:
        return err

    store: LocalStore = request.app.state.store
    portfolio = store.get_portfolio(payload["aid"])
    if not portfolio:
        return JSONResponse({"detail": "No active portfolio found"}, status_code=400)

    sub_key = (body.get("subscription_key") or "").strip()
    cycle = (body.get("cycle") or "").strip().lower()
    if cycle not in ("monthly", "annual"):
        return JSONResponse({"detail": "Cycle must be monthly or annual"}, status_code=400)

    from intelligence.api import estimate_renewal_from_selection  # type: ignore

    estimate = estimate_renewal_from_selection(portfolio, sub_key, cycle)
    if not estimate:
        return JSONResponse(
            {"detail": "Cannot estimate renewal for this subscription (missing dated payment or cycle already known)."},
            status_code=400,
        )
    return JSONResponse({"ok": True, "estimate": estimate})
