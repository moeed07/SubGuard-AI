"""Google OAuth 2.0 read-only Gmail connection routes."""

from __future__ import annotations

import secrets
import time
from datetime import datetime
from typing import Optional
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Request, Response
from fastapi.responses import JSONResponse, RedirectResponse

from app.config import Settings
from app.gmail_client import (
    GMAIL_READONLY_SCOPE,
    build_google_auth_url,
    exchange_code_for_token,
    fetch_gmail_profile,
    revoke_google_token,
    scan_gmail_messages,
)
from app.intelligence_adapter import IntelligenceUnavailableError, process_scan_output
from app.security import SecurityManager
from app.storage import LocalStore

router = APIRouter()


def _get_or_create_session_id(request: Request, security: SecurityManager) -> tuple[str, Optional[dict]]:
    raw = request.cookies.get(SecurityManager.SESSION_COOKIE_NAME)
    payload = security.verify_session_token(raw)
    if payload and payload.get("sid"):
        return payload["sid"], payload
    return secrets.token_urlsafe(16), None


def _set_session_cookie(
    response: Response,
    security: SecurityManager,
    settings: Settings,
    session_id: str,
    account_id: Optional[str] = None,
    is_demo: bool = False,
) -> None:
    token = security.create_session_token(session_id, account_id=account_id, is_demo=is_demo)
    response.set_cookie(
        key=SecurityManager.SESSION_COOKIE_NAME,
        value=token,
        httponly=True,
        samesite="lax",
        secure=settings.is_production,
        max_age=SecurityManager.SESSION_TTL_SECONDS,
        path="/",
    )


@router.get("/auth/google/start")
async def auth_google_start(request: Request) -> Response:
    settings: Settings = request.app.state.settings
    security: SecurityManager = request.app.state.security

    if not settings.oauth_configured:
        return RedirectResponse(url="/?auth_error=oauth_not_configured", status_code=302)

    if request.url.hostname == "127.0.0.1" and "localhost" in settings.app_base_url:
        return RedirectResponse(
            url=f"{settings.app_base_url.rstrip('/')}/auth/google/start",
            status_code=302,
        )

    session_id, existing = _get_or_create_session_id(request, security)
    state = security.create_oauth_state(session_id)
    auth_url = build_google_auth_url(
        client_id=settings.google_oauth_client_id,
        redirect_uri=settings.oauth_redirect_uri,
        state=state,
    )
    resp = RedirectResponse(url=auth_url, status_code=302)
    _set_session_cookie(
        resp,
        security,
        settings,
        session_id,
        account_id=existing.get("aid") if existing else None,
        is_demo=bool(existing.get("demo")) if existing else False,
    )
    return resp


@router.get("/auth/google/callback")
async def auth_google_callback(
    request: Request,
    code: Optional[str] = None,
    state: Optional[str] = None,
    error: Optional[str] = None,
) -> Response:
    settings: Settings = request.app.state.settings
    security: SecurityManager = request.app.state.security
    store: LocalStore = request.app.state.store

    if error:
        return RedirectResponse(url=f"/?auth_error={error}", status_code=302)

    raw_cookie = request.cookies.get(SecurityManager.SESSION_COOKIE_NAME)
    payload = security.verify_session_token(raw_cookie)
    session_id = payload.get("sid") if payload else None

    if not security.consume_oauth_state(state, session_id):
        return RedirectResponse(url="/?auth_error=invalid_state", status_code=302)

    if not code:
        return RedirectResponse(url="/?auth_error=missing_code", status_code=302)

    try:
        token_data = await exchange_code_for_token(
            code=code,
            client_id=settings.google_oauth_client_id,
            client_secret=settings.google_oauth_client_secret,
            redirect_uri=settings.oauth_redirect_uri,
        )
    except Exception:
        return RedirectResponse(url="/?auth_error=token_exchange_failed", status_code=302)

    granted_scopes = (token_data.get("scope") or "").split()
    if GMAIL_READONLY_SCOPE not in granted_scopes:
        return RedirectResponse(url="/?auth_error=scope_denied", status_code=302)

    access_token = token_data.get("access_token", "")
    expires_in = int(token_data.get("expires_in", 3600))
    expires_at = int(time.time()) + expires_in

    try:
        profile = await fetch_gmail_profile(access_token)
    except Exception:
        return RedirectResponse(url="/?auth_error=profile_failed", status_code=302)

    email = profile.get("emailAddress", "")
    if not email:
        return RedirectResponse(url="/?auth_error=missing_email", status_code=302)

    account_id = security.hash_account_id(email)
    encrypted_token = security.encrypt_token(access_token)
    store.upsert_account(account_id, encrypted_token=encrypted_token, token_expires_at=expires_at, is_demo=False)

    # Run first scan automatically on successful callback
    scan_out = await scan_gmail_messages(
        access_token=access_token,
        account_id=account_id,
        max_pages=settings.gmail_max_pages,
        max_messages=settings.gmail_max_messages,
    )
    as_of = datetime.now(ZoneInfo("Asia/Karachi")).strftime("%Y-%m-%d")
    intel = getattr(request.app.state, "intelligence", None)
    try:
        await process_scan_output(
            store=store,
            account_id=account_id,
            scan_output=scan_out,
            as_of=as_of,
            timezone_name="Asia/Karachi",
            intelligence=intel,
        )
    except IntelligenceUnavailableError:
        ver = store.next_scan_version(account_id)
        store.update_scan_status(
            account_id,
            ver,
            "failed",
            partial=True,
            scan_error="Intelligence module not yet integrated.",
        )

    resp = RedirectResponse(url="/", status_code=302)
    _set_session_cookie(resp, security, settings, session_id, account_id=account_id, is_demo=False)
    return resp


@router.post("/api/disconnect")
async def disconnect_account(request: Request) -> Response:
    security: SecurityManager = request.app.state.security
    store: LocalStore = request.app.state.store

    payload = security.verify_session_token(request.cookies.get(SecurityManager.SESSION_COOKIE_NAME))
    if not payload or not payload.get("sid"):
        return JSONResponse({"detail": "Not authenticated"}, status_code=401)

    csrf = request.headers.get("X-CSRF-Token")
    if not security.verify_csrf_token(payload["sid"], csrf):
        return JSONResponse({"detail": "Invalid CSRF token"}, status_code=403)

    account_id = payload.get("aid")
    if account_id:
        acct = store.get_account(account_id)
        if acct and acct.get("encrypted_token"):
            token = security.decrypt_token(acct["encrypted_token"])
            if token:
                await revoke_google_token(token)
        store.clear_account_token(account_id)

    resp = JSONResponse({"ok": True, "disconnected": True})
    resp.delete_cookie(SecurityManager.SESSION_COOKIE_NAME, path="/")
    return resp
