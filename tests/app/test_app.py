"""Tests for SubGuard AI web app, Gmail sanitization, storage, and worker."""

from __future__ import annotations

import base64
from datetime import datetime, timedelta, timezone
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.gmail_client import (
    ScanOutput,
    _extract_body_from_payload,
    make_opaque_source_id,
    sanitize_body_text,
)
from app.intelligence_adapter import IntelligenceBackend, process_scan_output
from app.main import create_app
from app.storage import LocalStore


def _test_settings(service_mode: str = "web") -> Settings:
    return Settings(
        google_cloud_project="",
        app_base_url="http://localhost:8000",
        google_oauth_client_id="test-client-id",
        google_oauth_client_secret="test-client-secret",
        session_secret="test-session-secret-1234567890",
        token_encryption_key="test-encryption-key-1234567890",
        service_mode=service_mode,
        gemini_model="gemini-2.5-flash",
        google_api_key="",
    )


def test_demo_optimizer_uses_fixed_catalog_and_gemini_is_opt_in(monkeypatch) -> None:
    from intelligence import api

    snapshots = []

    async def review(snapshot, goal):
        snapshots.append(snapshot)
        assert "lowest monthly cost" in goal
        return {"status": "complete", "trace": [{"tool": "optimize_subscription_features", "outcome": "ok"}]}

    monkeypatch.setattr(api, "run_review", review)
    store = LocalStore(":memory:")
    app = create_app(settings=_test_settings(), store=store, intelligence=_mock_intelligence())
    client = TestClient(app)
    assert client.post("/api/optimizer").status_code == 401
    assert client.post("/demo/start").status_code == 200
    assert client.post("/api/optimizer").status_code == 403
    before = client.get("/api/dashboard").json()
    csrf = {"X-CSRF-Token": before["csrf_token"]}
    response = client.post("/api/optimizer", headers=csrf, json={"plans": []})
    assert response.status_code == 200
    calculation = response.json()
    assert calculation["agent"] is None and snapshots == []
    group = calculation["result"]["currencies"]["PKR"]
    assert group["retained_plan_ids"] == ["A", "C"]
    assert group["current_monthly_minor"] == 900_000
    assert group["minimum_monthly_minor"] == group["monthly_reduction_minor"] == 450_000

    live = client.post("/api/optimizer", headers=csrf, json={"run_with_gemini": True}).json()
    assert live["agent"]["completed"] is True and live["result"] == calculation["result"]
    assert snapshots[0]["optimizer_plans"] == calculation["plans"]
    assert snapshots[0]["timelines"] == {} and snapshots[0]["subscriptions"] == []
    after = client.get("/api/dashboard").json()
    assert after["portfolio"] == before["portfolio"] and after["review"] == before["review"]


def test_optimizer_rejects_nonfictional_sessions() -> None:
    store = LocalStore(":memory:")
    app = create_app(settings=_test_settings(), store=store, intelligence=_mock_intelligence())
    store.upsert_account("acct_live", is_demo=False)
    security = app.state.security
    client = TestClient(app)
    client.cookies.set(security.SESSION_COOKIE_NAME, security.create_session_token("sid_live", account_id="acct_live"))
    response = client.post("/api/optimizer", headers={"X-CSRF-Token": security.create_csrf_token("sid_live")})
    assert response.status_code == 403


def _mock_intelligence() -> IntelligenceBackend:
    """Test double implementing §2 contract for §3 fixture."""

    def extract_events(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
        events: list[dict[str, Any]] = []
        for m in messages:
            sid = m["source_id"]
            if sid == "m1":
                events.append({
                    "event_id": "m1:0", "source_id": "m1", "received_at": m["received_at"],
                    "subscription_key": "writing-plus", "kind": "payment", "currency": "PKR",
                    "amount_minor": 200000, "cycle": "monthly", "transaction_ref": "W-101",
                    "event_date": "2026-11-26", "effective_date": None,
                    "next_charge_date": None, "date_basis": "unknown",
                })
            elif sid == "m2":
                events.append({
                    "event_id": "m2:0", "source_id": "m2", "received_at": m["received_at"],
                    "subscription_key": "writing-plus", "kind": "payment", "currency": "PKR",
                    "amount_minor": 200000, "cycle": "monthly", "transaction_ref": "W-101",
                    "event_date": "2026-11-26", "effective_date": None,
                    "next_charge_date": None, "date_basis": "unknown",
                })
            elif sid == "m3":
                events.append({
                    "event_id": "m3:0", "source_id": "m3", "received_at": m["received_at"],
                    "subscription_key": "design-pro", "kind": "payment", "currency": "PKR",
                    "amount_minor": 1200000, "cycle": "annual", "transaction_ref": "D-201",
                    "event_date": "2026-11-26", "effective_date": None,
                    "next_charge_date": None, "date_basis": "unknown",
                })
            elif sid == "m4":
                events.append({
                    "event_id": "m4:0", "source_id": "m4", "received_at": m["received_at"],
                    "subscription_key": "design-pro", "kind": "renewal", "currency": "PKR",
                    "amount_minor": 1200000, "cycle": "annual", "transaction_ref": None,
                    "event_date": "2026-11-26", "effective_date": None,
                    "next_charge_date": "2026-12-01", "date_basis": "confirmed",
                })
            elif sid == "m5":
                events.append({
                    "event_id": "m5:0", "source_id": "m5", "received_at": m["received_at"],
                    "subscription_key": "sketch-trial", "kind": "trial_conversion", "currency": "PKR",
                    "amount_minor": 70000, "cycle": "monthly", "transaction_ref": None,
                    "event_date": "2026-11-26", "effective_date": None,
                    "next_charge_date": "2026-11-29", "date_basis": "confirmed",
                })
            elif sid == "m6":
                events.append({
                    "event_id": "m6:0", "source_id": "m6", "received_at": m["received_at"],
                    "subscription_key": "promo-bundle", "kind": "promo", "currency": None,
                    "amount_minor": None, "cycle": None, "transaction_ref": None,
                    "event_date": "2026-11-26", "effective_date": None,
                    "next_charge_date": None, "date_basis": "unknown",
                })
            elif sid == "m7":
                events.append({
                    "event_id": "m7:0", "source_id": "m7", "received_at": m["received_at"],
                    "subscription_key": "design-pro", "kind": "failed", "currency": "PKR",
                    "amount_minor": 50000, "cycle": None, "transaction_ref": None,
                    "event_date": "2026-11-26", "effective_date": None,
                    "next_charge_date": None, "date_basis": "unknown",
                })
            elif sid == "m8":
                events.append({
                    "event_id": "m8:0", "source_id": "m8", "received_at": m["received_at"],
                    "subscription_key": "design-pro", "kind": "cancellation_confirmed", "currency": None,
                    "amount_minor": None, "cycle": "annual", "transaction_ref": None,
                    "event_date": "2026-11-26", "effective_date": "2026-12-01",
                    "next_charge_date": None, "date_basis": "unknown",
                })
        return events

    def build_portfolio(events: list[dict[str, Any]], as_of: str, timezone_name: str) -> dict[str, Any]:
        has_m8 = any(e["kind"] == "cancellation_confirmed" and e["subscription_key"] == "design-pro" for e in events)
        monthly_eq = 200000 if has_m8 else 300000
        next_7d = 70000 if has_m8 else 1270000
        due = [
            {
                "subscription_key": "sketch-trial",
                "date": "2026-11-29",
                "amount_minor": 70000,
                "currency": "PKR",
                "kind": "trial_conversion",
                "date_basis": "confirmed",
                "evidence_ids": ["m5"],
            }
        ]
        if not has_m8:
            due.append({
                "subscription_key": "design-pro",
                "date": "2026-12-01",
                "amount_minor": 1200000,
                "currency": "PKR",
                "kind": "renewal",
                "date_basis": "confirmed",
                "evidence_ids": ["m4"],
            })
        return {
            "as_of": as_of,
            "timezone": timezone_name,
            "totals": {
                "PKR": {
                    "paid_minor": 1400000,
                    "monthly_equivalent_minor": monthly_eq,
                    "next_7d_minor": next_7d,
                }
            },
            "subscriptions": [
                {
                    "subscription_key": "writing-plus",
                    "status": "active",
                    "paid_through": "2026-12-26",
                    "auto_renew": True,
                    "evidence_ids": ["m1", "m2"],
                },
                {
                    "subscription_key": "design-pro",
                    "status": "cancelled" if has_m8 else "active",
                    "paid_through": "2026-12-01",
                    "auto_renew": not has_m8,
                    "evidence_ids": ["m3", "m4", "m8"] if has_m8 else ["m3", "m4"],
                },
                {
                    "subscription_key": "sketch-trial",
                    "status": "trial",
                    "paid_through": None,
                    "auto_renew": True,
                    "evidence_ids": ["m5"],
                },
            ],
            "due": due,
            "timelines": {},
        }

    async def run_review(portfolio: dict[str, Any], goal: str) -> dict[str, Any]:
        return {
            "status": "complete",
            "summary": "Sketch Trial converts to a paid PKR 700 plan on 2026-11-29.",
            "items": [
                {
                    "subscription_key": "sketch-trial",
                    "kind": "trial_conversion",
                    "target_date": "2026-11-29",
                    "state": "open",
                    "evidence_ids": ["m5"],
                    "explanation": "Trial converts in 3 days; decide before 2026-11-29.",
                }
            ],
            "trace": [
                {"tool": "inspect_due_charges", "outcome": "ok", "source_ids": ["m5"]}
            ],
        }

    return IntelligenceBackend(
        extract_events=extract_events,
        build_portfolio=build_portfolio,
        run_review=run_review,
    )


def test_health_and_service_modes() -> None:
    web_app = create_app(settings=_test_settings("web"), store=LocalStore(":memory:"))
    web_client = TestClient(web_app)
    assert web_client.get("/health").json() == {"status": "ok", "service_mode": "web"}
    assert web_client.get("/").status_code == 200
    assert web_client.post("/jobs/deliver").status_code == 404

    worker_app = create_app(settings=_test_settings("worker"), store=LocalStore(":memory:"))
    worker_client = TestClient(worker_app)
    assert worker_client.get("/health").json() == {"status": "ok", "service_mode": "worker"}
    assert worker_client.post("/jobs/deliver").status_code == 401
    ok_resp = worker_client.post("/jobs/deliver", headers={"Authorization": "Bearer valid-oidc-token"})
    assert ok_resp.status_code == 200
    assert ok_resp.json()["delivered"] == 0


def test_oauth_start_and_denied_callback() -> None:
    app = create_app(settings=_test_settings(), store=LocalStore(":memory:"))
    client = TestClient(app)

    start_resp = client.get("/auth/google/start", follow_redirects=False)
    assert start_resp.status_code == 302
    assert "accounts.google.com" in start_resp.headers["location"]
    assert "gmail.readonly" in start_resp.headers["location"]

    denied_resp = client.get("/auth/google/callback?error=access_denied", follow_redirects=False)
    assert denied_resp.status_code == 302
    assert "auth_error=access_denied" in denied_resp.headers["location"]

    bad_state = client.get("/auth/google/callback?code=abc&state=wrong", follow_redirects=False)
    assert bad_state.status_code == 302
    assert "auth_error=invalid_state" in bad_state.headers["location"]


def test_gmail_sanitization_and_multipart_extraction() -> None:
    html_b64 = base64.urlsafe_b64encode(b"<p>Paid <b>PKR 2,000</b></p>").decode("ascii")
    payload = {
        "mimeType": "multipart/mixed",
        "parts": [
            {"mimeType": "text/html", "body": {"data": html_b64}},
            {"filename": "invoice.pdf", "mimeType": "application/pdf", "body": {"data": html_b64}},
        ],
    }
    extracted = _extract_body_from_payload(payload)
    assert "Paid" in extracted and "PKR 2,000" in extracted
    assert "<p>" not in extracted

    raw = "Receipt W-101 for user@example.com\nhttps://track.example.com/pixel\nOn Mon, Alice wrote:\n> old quote"
    cleaned = sanitize_body_text(raw)
    assert "user@example.com" not in cleaned
    assert "https://track.example.com" not in cleaned
    assert "old quote" not in cleaned
    assert "Receipt W-101" in cleaned


@pytest.mark.asyncio
async def test_scan_states_and_stale_version_protection() -> None:
    store = LocalStore(":memory:")
    intel = _mock_intelligence()
    acct = "acct_test_1"

    res_empty = await process_scan_output(
        store, acct, ScanOutput(messages=[], evidence_records=[], partial=False), "2026-11-26", "Asia/Karachi", intel
    )
    assert res_empty["scan_status"] == "empty"

    res_fail = await process_scan_output(
        store, acct, ScanOutput(messages=[], evidence_records=[], partial=True, error="timeout"), "2026-11-26", "Asia/Karachi", intel
    )
    assert res_fail["scan_status"] == "failed"

    # Stale scan version cannot overwrite newer version
    v_old = store.next_scan_version(acct)
    v_new = store.next_scan_version(acct)
    assert v_new > v_old
    assert store.save_portfolio(acct, v_old, {"stale": True}) is False
    assert store.save_portfolio(acct, v_new, {"stale": False}) is True


def test_demo_fixture_reminders_worker_and_isolation() -> None:
    store = LocalStore(":memory:")
    app = create_app(settings=_test_settings(), store=store, intelligence=_mock_intelligence())
    client = TestClient(app)

    # Start fictional demo
    demo_resp = client.post("/demo/start")
    assert demo_resp.status_code == 200

    dash = client.get("/api/dashboard").json()
    assert dash["connected"] is True
    assert dash["is_demo"] is True
    assert dash["portfolio"]["totals"]["PKR"] == {
        "paid_minor": 1400000,
        "monthly_equivalent_minor": 300000,
        "next_7d_minor": 1270000,
    }
    csrf = dash["csrf_token"]

    # Schedule 1-minute reminder for sketch-trial
    rem_resp = client.post(
        "/api/reminders",
        headers={"X-CSRF-Token": csrf},
        json={"subscription_key": "sketch-trial", "mode": "one_minute"},
    )
    assert rem_resp.status_code == 200

    # Schedule reminder for design-pro, then introduce m8 cancellation via refresh
    rem_dp = client.post(
        "/api/reminders",
        headers={"X-CSRF-Token": csrf},
        json={"subscription_key": "design-pro", "mode": "one_minute"},
    )
    assert rem_dp.status_code == 200

    ref_resp = client.post(
        "/api/refresh",
        headers={"X-CSRF-Token": csrf},
        json={"include_m8": True},
    )
    assert ref_resp.status_code == 200

    dash2 = client.get("/api/dashboard").json()
    assert dash2["portfolio"]["totals"]["PKR"] == {
        "paid_minor": 1400000,
        "monthly_equivalent_minor": 200000,
        "next_7d_minor": 70000,
    }

    # Scheduling cancelled renewal is rejected
    rem_cancelled = client.post(
        "/api/reminders",
        headers={"X-CSRF-Token": csrf},
        json={"subscription_key": "design-pro", "mode": "one_minute"},
    )
    assert rem_cancelled.status_code == 400

    # Simulate worker delivery once due time passes; retry twice -> only 1 notification
    future_iso = (datetime.now(timezone.utc) + timedelta(minutes=2)).strftime("%Y-%m-%dT%H:%M:%SZ")
    assert store.deliver_due_jobs(now_iso=future_iso) == 1
    assert store.deliver_due_jobs(now_iso=future_iso) == 0

    dash3 = client.get("/api/dashboard").json()
    assert len(dash3["notifications"]) == 1
    assert dash3["notifications"][0]["subscription_key"] == "sketch-trial"

    # Cross-account isolation: fresh client cannot read demo evidence
    other_client = TestClient(app)
    assert other_client.get("/api/evidence/m1").status_code == 401
    other_client.post("/demo/start")
    assert other_client.get("/api/evidence/m1").status_code == 200

    # Delete data removes only session owner's data
    del_resp = client.delete("/api/data", headers={"X-CSRF-Token": csrf})
    assert del_resp.status_code == 200
    assert client.get("/api/dashboard").json()["connected"] is False


def test_user_cycle_choice_is_saved_and_estimated() -> None:
    store = LocalStore(":memory:")
    app = create_app(settings=_test_settings(), store=store, intelligence=_mock_intelligence())
    client = TestClient(app)

    acct = "acct_lookup_test"
    store.upsert_account(acct, is_demo=True)
    portfolio = {
        "as_of": "2026-11-26",
        "timezone": "Asia/Karachi",
        "totals": {"PKR": {"paid_minor": 200000, "monthly_equivalent_minor": 0, "next_7d_minor": 0}},
        "subscriptions": [
            {
                "subscription_key": "google-play-order",
                "status": "unknown",
                "paid_through": None,
                "auto_renew": None,
                "evidence_ids": ["m1"],
            }
        ],
        "due": [],
        "timelines": {
            "google-play-order": [
                {
                    "event_id": "m1:0",
                    "source_id": "m1",
                    "received_at": "2026-11-26T08:00:00Z",
                    "subscription_key": "google-play-order",
                    "kind": "payment",
                    "currency": "PKR",
                    "amount_minor": 200000,
                    "cycle": None,
                    "transaction_ref": None,
                    "event_date": "2026-11-26",
                    "effective_date": None,
                    "next_charge_date": None,
                    "date_basis": "unknown",
                }
            ]
        },
    }
    ver = store.next_scan_version(acct)
    store.save_portfolio(acct, ver, portfolio)

    # Set session cookie
    token = app.state.security.create_session_token("sid1", account_id=acct, is_demo=True)
    csrf = app.state.security.create_csrf_token("sid1")
    client.cookies.set(app.state.security.SESSION_COOKIE_NAME, token)

    # Public lookup route was removed from the app
    lp = client.post("/api/plan-lookup", headers={"X-CSRF-Token": csrf}, json={})
    assert lp.status_code in (404, 405)

    # User says "monthly" -> saved, estimated date 1 calendar month after receipt
    est = client.post(
        "/api/cycle-choice",
        headers={"X-CSRF-Token": csrf},
        json={"subscription_key": "google-play-order", "cycle": "monthly"},
    )
    assert est.status_code == 200
    assert est.json()["cycle"] == "monthly"
    assert est.json()["estimate"]["date"] == "2026-12-26"
    assert est.json()["estimate"]["date_basis"] == "estimated"

    # Choice survives a dashboard reload; totals and reminders untouched
    dash = client.get("/api/dashboard").json()
    assert dash["user_estimates"]["google-play-order"]["estimate"]["date"] == "2026-12-26"
    assert store.get_portfolio(acct)["totals"]["PKR"]["next_7d_minor"] == 0
    assert store.list_reminders(acct) == []

    # Switching to annual recalculates; invalid inputs rejected; clear removes it
    ann = client.post(
        "/api/cycle-choice",
        headers={"X-CSRF-Token": csrf},
        json={"subscription_key": "google-play-order", "cycle": "annual"},
    )
    assert ann.json()["estimate"]["date"] == "2027-11-26"
    assert client.post(
        "/api/cycle-choice", headers={"X-CSRF-Token": csrf},
        json={"subscription_key": "google-play-order", "cycle": "weekly"},
    ).status_code == 400
    assert client.post(
        "/api/cycle-choice", headers={"X-CSRF-Token": csrf},
        json={"subscription_key": "not-mine", "cycle": "monthly"},
    ).status_code == 404
    assert client.post(
        "/api/cycle-choice", json={"subscription_key": "google-play-order", "cycle": "monthly"},
    ).status_code == 403
    client.post(
        "/api/cycle-choice", headers={"X-CSRF-Token": csrf},
        json={"subscription_key": "google-play-order", "cycle": "clear"},
    )
    assert client.get("/api/dashboard").json()["user_estimates"] == {}


def test_auto_5d_1d_reminders_and_email_delivery(monkeypatch: pytest.MonkeyPatch) -> None:
    sent_emails: list[dict[str, str]] = []

    def _fake_smtp_send(settings, to_email, subscription_key, target_date, reminder_type, currency=None, amount_minor=None):
        sent_emails.append({
            "to": to_email,
            "sub": subscription_key,
            "date": target_date,
            "type": reminder_type,
            "currency": currency,
            "amount_minor": amount_minor,
        })
        return True

    import app.routes_api as routes_api
    monkeypatch.setattr(routes_api, "send_reminder_email", _fake_smtp_send)

    store = LocalStore(":memory:")
    app = create_app(settings=_test_settings(), store=store, intelligence=_mock_intelligence())
    client = TestClient(app)

    acct = "acct_live_email_test"
    enc_email = app.state.security.encrypt_token("student@example.com")
    store.upsert_account(acct, is_demo=False, encrypted_email=enc_email)
    future_date = (datetime.now(timezone.utc) + timedelta(days=10)).strftime("%Y-%m-%d")
    portfolio = {
        "as_of": "2026-11-26",
        "timezone": "Asia/Karachi",
        "totals": {"PKR": {"paid_minor": 200000, "monthly_equivalent_minor": 200000, "next_7d_minor": 0}},
        "subscriptions": [
            {
                "subscription_key": "writing-plus",
                "status": "active",
                "paid_through": future_date,
                "auto_renew": True,
                "evidence_ids": ["m1"],
            }
        ],
        "due": [
            {
                "subscription_key": "writing-plus",
                "date": future_date,
                "amount_minor": 200000,
                "currency": "PKR",
                "kind": "renewal",
                "date_basis": "confirmed",
                "evidence_ids": ["m1"],
            }
        ],
        "timelines": {"writing-plus": []},
    }
    ver = store.next_scan_version(acct)
    store.save_portfolio(acct, ver, portfolio)

    from app.intelligence_adapter import auto_schedule_5d_and_1d_reminders
    auto_schedule_5d_and_1d_reminders(store, acct, "writing-plus", future_date)
    reminders = store.list_reminders(acct)
    assert {r["reminder_type"] for r in reminders} == {"five_days", "one_day"}

    # Deliver when due time arrives -> sends email to student@example.com
    far_future = (datetime.now(timezone.utc) + timedelta(days=11)).strftime("%Y-%m-%dT%H:%M:%SZ")
    delivered = routes_api.deliver_due_jobs_with_email(app, now_iso=far_future)
    assert delivered == 2
    assert len(sent_emails) == 2
    assert sent_emails[0]["to"] == "student@example.com"
    assert sent_emails[0]["currency"] == "PKR"
    assert sent_emails[0]["amount_minor"] == 200000

    # Custom next_charge_date without cycle also delivers instead of cancelling
    store.set_cycle_choice(acct, "writing-plus", "", next_charge_date=future_date)
    portfolio["due"] = []
    store.save_portfolio(acct, ver, portfolio)
    store.create_reminder_job(acct, "writing-plus", "one_minute", far_future, future_date)
    delivered2 = routes_api.deliver_due_jobs_with_email(app, now_iso=far_future)
    assert delivered2 == 1
    assert len(sent_emails) == 3

    from app.mailer import build_reminder_message
    msg = build_reminder_message(
        "sender@example.com",
        "student@example.com",
        "writing-plus",
        future_date,
        "five_days",
        currency="PKR",
        amount_minor=200000,
    )
    assert msg["Subject"] == "SubGuard-AI: writing-plus"
    assert "PKR 2,000" in msg.get_content()
    assert future_date in msg.get_content()
    assert "5 days before renewal" in msg.get_content()


def test_subscription_basis_reprocess_and_confirm_endpoint() -> None:
    from intelligence.api import build_portfolio

    store = LocalStore(":memory:")
    app = create_app(settings=_test_settings(), store=store)
    client = TestClient(app)

    acct = "acct_confirm_test"
    store.upsert_account(acct, is_demo=True)
    ver = store.next_scan_version(acct)

    # First insert a stale event and an uncertain event
    store.upsert_events(
        acct,
        [
            {
                "event_id": "s1:0",
                "source_id": "s1",
                "received_at": "2026-11-01T08:00:00Z",
                "subscription_key": "stale-shop",
                "kind": "payment",
                "currency": "PKR",
                "amount_minor": 100000,
                "cycle": None,
                "transaction_ref": None,
                "event_date": "2026-11-01",
                "effective_date": None,
                "next_charge_date": None,
                "date_basis": "unknown",
                "subscription_basis": "subscription",
            },
            {
                "event_id": "s2:0",
                "source_id": "s2",
                "received_at": "2026-11-02T08:00:00Z",
                "subscription_key": "bank-charge",
                "kind": "payment",
                "currency": "PKR",
                "amount_minor": 120000,
                "cycle": None,
                "transaction_ref": None,
                "event_date": "2026-11-02",
                "effective_date": None,
                "next_charge_date": None,
                "date_basis": "unknown",
                "subscription_basis": "uncertain",
            },
        ],
    )
    # Reprocessing s1 with [] removes stale-shop
    store.replace_events_for_sources(acct, ["s1"], [])
    events = store.list_events(acct)
    assert len(events) == 1
    assert events[0]["subscription_basis"] == "uncertain"

    portfolio = build_portfolio(events, "2026-11-26", "Asia/Karachi")
    store.save_portfolio(acct, ver, portfolio)
    assert len(portfolio["needs_confirmation"]) == 1
    assert portfolio["subscriptions"] == []

    token = app.state.security.create_session_token("sid_c", account_id=acct, is_demo=True)
    csrf = app.state.security.create_csrf_token("sid_c")
    client.cookies.set(app.state.security.SESSION_COOKIE_NAME, token)

    # Confirm s2 as a subscription -> moves from needs_confirmation to subscriptions
    resp = client.post(
        "/api/confirm-subscription",
        headers={"X-CSRF-Token": csrf},
        json={"source_id": "s2", "is_subscription": True},
    )
    assert resp.status_code == 200
    dash = client.get("/api/dashboard").json()
    assert dash["portfolio"]["needs_confirmation"] == []
    assert [s["subscription_key"] for s in dash["portfolio"]["subscriptions"]] == ["bank-charge"]
