"""Refresh downloads only Gmail messages that are not already saved for the account."""

from __future__ import annotations

import base64

import httpx
import pytest

import app.gmail_client as gmail_client


def _fake_gmail(fetched: list[str]):
    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path.endswith("/messages"):
            return httpx.Response(200, json={"messages": [{"id": "a"}, {"id": "b"}, {"id": "c"}]})
        msg_id = path.rsplit("/", 1)[-1]
        fetched.append(msg_id)
        body = base64.urlsafe_b64encode(b"Paid PKR 100 today. Receipt R-1.").decode()
        return httpx.Response(
            200,
            json={
                "id": msg_id,
                "internalDate": "1795680000000",
                "payload": {
                    "mimeType": "text/plain",
                    "headers": [{"name": "Subject", "value": "Receipt"}, {"name": "From", "value": "x@shop.example"}],
                    "body": {"data": body},
                },
            },
        )

    return handler


@pytest.mark.asyncio
async def test_known_messages_are_skipped_and_cap_counts_only_new(monkeypatch: pytest.MonkeyPatch) -> None:
    fetched: list[str] = []
    transport = httpx.MockTransport(_fake_gmail(fetched))
    real_client = httpx.AsyncClient
    monkeypatch.setattr(
        gmail_client.httpx, "AsyncClient", lambda *a, **kw: real_client(transport=transport, **kw)
    )
    monkeypatch.setattr(gmail_client.asyncio, "sleep", lambda *_: _noop())

    out = await gmail_client.scan_gmail_messages("tok", "acct", max_messages=10, known_message_ids={"a", "b"})
    assert fetched == ["c"]
    assert [e["gmail_message_id"] for e in out.evidence_records] == ["c"]
    assert out.partial is False

    fetched.clear()
    capped = await gmail_client.scan_gmail_messages("tok", "acct", max_messages=1, known_message_ids={"a"})
    assert fetched == ["b"]
    assert capped.partial is True


async def _noop() -> None:
    return None


@pytest.mark.asyncio
async def test_self_reminder_emails_are_skipped_and_purged(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    from app.storage import LocalStore

    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path.endswith("/messages"):
            return httpx.Response(200, json={"messages": [{"id": "rem1"}, {"id": "real1"}]})
        msg_id = path.rsplit("/", 1)[-1]
        subj = "SubGuard-AI: chatgpt-plus" if msg_id == "rem1" else "Netflix receipt"
        body = base64.urlsafe_b64encode(b"Next renewal on 2026-12-01 for PKR 800.").decode()
        return httpx.Response(
            200,
            json={
                "id": msg_id,
                "internalDate": "1795680000000",
                "payload": {
                    "mimeType": "text/plain",
                    "headers": [{"name": "Subject", "value": subj}, {"name": "From", "value": "billing@example.com"}],
                    "body": {"data": body},
                },
            },
        )

    transport = httpx.MockTransport(handler)
    real_client = httpx.AsyncClient
    monkeypatch.setattr(gmail_client.httpx, "AsyncClient", lambda *a, **kw: real_client(transport=transport, **kw))
    monkeypatch.setattr(gmail_client.asyncio, "sleep", lambda *_: _noop())

    out = await gmail_client.scan_gmail_messages("tok", "acct_test", max_messages=10)
    assert [e["gmail_message_id"] for e in out.evidence_records] == ["real1"]

    store = LocalStore(str(tmp_path / "test.db"))
    store.upsert_account("acct_test")
    store.upsert_evidence(
        "acct_test",
        [
            {"source_id": "src_rem", "gmail_message_id": "g1", "received_at": "2026-11-27T00:00:00Z", "sender_domain": "gmail.com", "subject": "SubGuard-AI: netflix-standard"},
            {"source_id": "src_real", "gmail_message_id": "g2", "received_at": "2026-11-27T00:00:00Z", "sender_domain": "netflix.com", "subject": "Netflix receipt"},
        ],
    )
    store.upsert_events(
        "acct_test",
        [
            {"event_id": "src_rem:0", "source_id": "src_rem", "received_at": "2026-11-27T00:00:00Z", "subscription_key": "netflix-standard", "kind": "renewal", "amount_minor": None, "currency": None, "next_charge_date": "2026-12-01", "date_basis": "confirmed", "subscription_basis": "explicit"},
            {"event_id": "src_real:0", "source_id": "src_real", "received_at": "2026-11-27T00:00:00Z", "subscription_key": "netflix-standard", "kind": "renewal", "amount_minor": 80000, "currency": "PKR", "next_charge_date": "2026-12-01", "date_basis": "confirmed", "subscription_basis": "explicit"},
        ],
    )
    assert store.purge_self_reminder_evidence("acct_test") is True
    assert store.purge_self_reminder_evidence("acct_test") is False
    assert [e["source_id"] for e in store.list_evidence("acct_test")] == ["src_real"]
    assert [ev["event_id"] for ev in store.list_events("acct_test")] == ["src_real:0"]
