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
