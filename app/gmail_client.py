"""Gmail read-only OAuth and billing-email extraction/redaction."""

from __future__ import annotations

import asyncio
import base64
import hashlib
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from typing import Any, Optional
from urllib.parse import urlencode

import httpx
from bs4 import BeautifulSoup

GMAIL_READONLY_SCOPE = "https://www.googleapis.com/auth/gmail.readonly"
GOOGLE_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
GOOGLE_REVOKE_URL = "https://oauth2.googleapis.com/revoke"
GMAIL_API_BASE = "https://gmail.googleapis.com/gmail/v1/users/me"

DEFAULT_GMAIL_QUERY = (
    'newer_than:13m -category:promotions -category:social '
    '{receipt invoice renewal trial subscription payment cancellation "auto-renew"}'
)

_URL_RE = re.compile(r"https?://\S+", re.IGNORECASE)
_EMAIL_RE = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")
_QUOTED_REPLY_RE = re.compile(r"(?m)^>.*$")
_ON_WROTE_RE = re.compile(r"(?is)\nOn .+wrote:\s*\n.*$")
_SIGNATURE_RE = re.compile(r"(?is)\n--\s*\n.*$")


@dataclass
class ScanOutput:
    messages: list[dict[str, Any]]
    evidence_records: list[dict[str, Any]]
    partial: bool
    error: Optional[str] = None


def build_google_auth_url(client_id: str, redirect_uri: str, state: str) -> str:
    params = {
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "scope": GMAIL_READONLY_SCOPE,
        "state": state,
        "access_type": "online",
        "include_granted_scopes": "true",
        "prompt": "select_account consent",
    }
    return f"{GOOGLE_AUTH_URL}?{urlencode(params)}"


async def exchange_code_for_token(
    code: str,
    client_id: str,
    client_secret: str,
    redirect_uri: str,
) -> dict[str, Any]:
    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.post(
            GOOGLE_TOKEN_URL,
            data={
                "code": code,
                "client_id": client_id,
                "client_secret": client_secret,
                "redirect_uri": redirect_uri,
                "grant_type": "authorization_code",
            },
        )
        resp.raise_for_status()
        return resp.json()


async def revoke_google_token(token: str) -> None:
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            await client.post(GOOGLE_REVOKE_URL, params={"token": token})
    except Exception:
        pass


async def fetch_gmail_profile(access_token: str) -> dict[str, Any]:
    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.get(
            f"{GMAIL_API_BASE}/profile",
            headers={"Authorization": f"Bearer {access_token}"},
        )
        resp.raise_for_status()
        return resp.json()


def _decode_base64url(data: str) -> str:
    if not data:
        return ""
    padded = data + "=" * (-len(data) % 4)
    return base64.urlsafe_b64decode(padded.encode("ascii")).decode("utf-8", errors="replace")


def _extract_body_from_payload(payload: dict[str, Any]) -> str:
    """Walk multipart payload, prefer text/plain, fallback to stripped HTML, skip attachments."""
    plain_parts: list[str] = []
    html_parts: list[str] = []

    def _walk(part: dict[str, Any]) -> None:
        filename = part.get("filename") or ""
        if filename:
            return
        mime = (part.get("mimeType") or "").lower()
        body_data = (part.get("body") or {}).get("data")
        if body_data:
            decoded = _decode_base64url(body_data)
            if mime == "text/plain":
                plain_parts.append(decoded)
            elif mime == "text/html":
                html_parts.append(decoded)
        for sub in part.get("parts") or []:
            _walk(sub)

    _walk(payload)
    if plain_parts:
        return "\n".join(plain_parts)
    if html_parts:
        soup = BeautifulSoup("\n".join(html_parts), "html.parser")
        for tag in soup(["script", "style"]):
            tag.decompose()
        return soup.get_text(separator="\n")
    return ""


def sanitize_body_text(raw_text: str) -> str:
    """Redact quoted replies, signatures, tracking URLs, and personal email addresses."""
    text = _ON_WROTE_RE.sub("", raw_text)
    text = _SIGNATURE_RE.sub("", text)
    text = _QUOTED_REPLY_RE.sub("", text)
    text = _URL_RE.sub("[link-removed]", text)
    text = _EMAIL_RE.sub("[email-removed]", text)
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    return "\n".join(lines)[:4000]


def make_opaque_source_id(account_id: str, gmail_message_id: str) -> str:
    digest = hashlib.sha256(f"{account_id}:{gmail_message_id}".encode("utf-8")).hexdigest()
    return f"src_{digest[:16]}"


def _parse_header_map(headers: list[dict[str, str]]) -> dict[str, str]:
    return {h["name"].lower(): h["value"] for h in headers if "name" in h and "value" in h}


def _extract_sender_domain(from_header: str) -> str:
    match = re.search(r"@([A-Za-z0-9.-]+)", from_header)
    return match.group(1).lower() if match else "unknown"


def _parse_received_at(headers_map: dict[str, str], internal_date_ms: Optional[str]) -> str:
    if internal_date_ms and internal_date_ms.isdigit():
        dt = datetime.fromtimestamp(int(internal_date_ms) / 1000.0, tz=timezone.utc)
        return dt.strftime("%Y-%m-%dT%H:%M:%SZ")
    date_hdr = headers_map.get("date", "")
    if date_hdr:
        try:
            dt = parsedate_to_datetime(date_hdr)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        except Exception:
            pass
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


async def scan_gmail_messages(
    access_token: str,
    account_id: str,
    max_pages: int = 5,
    max_messages: int = 100,
    query: str = DEFAULT_GMAIL_QUERY,
    known_message_ids: Optional[set[str]] = None,
) -> ScanOutput:
    """List candidate billing messages and fetch only ones not already saved for this account.

    Already-processed messages keep their saved events, so each refresh only downloads
    new mail. Because the cap counts only new messages, repeated refreshes also
    backfill older mail that an earlier capped scan did not reach.
    """
    headers = {"Authorization": f"Bearer {access_token}"}
    known = known_message_ids or set()
    message_ids: list[str] = []
    partial = False
    page_token: Optional[str] = None

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            for _ in range(max_pages):
                params: dict[str, Any] = {"q": query, "maxResults": 50}
                if page_token:
                    params["pageToken"] = page_token
                resp = await client.get(f"{GMAIL_API_BASE}/messages", headers=headers, params=params)
                resp.raise_for_status()
                data = resp.json()
                for item in data.get("messages", []):
                    if item["id"] in known:
                        continue
                    message_ids.append(item["id"])
                    if len(message_ids) >= max_messages:
                        partial = True
                        break
                if len(message_ids) >= max_messages:
                    break
                page_token = data.get("nextPageToken")
                if not page_token:
                    break
            else:
                if page_token:
                    partial = True

            envelopes: list[dict[str, Any]] = []
            evidence: list[dict[str, Any]] = []
            for msg_id in message_ids:
                msg_resp = await client.get(
                    f"{GMAIL_API_BASE}/messages/{msg_id}",
                    headers=headers,
                    params={"format": "full"},
                )
                if msg_resp.status_code in (403, 429):
                    await asyncio.sleep(0.5)
                    msg_resp = await client.get(
                        f"{GMAIL_API_BASE}/messages/{msg_id}",
                        headers=headers,
                        params={"format": "full"},
                    )
                if msg_resp.status_code >= 400:
                    partial = True
                    continue
                await asyncio.sleep(0.03)
                msg_data = msg_resp.json()
                payload = msg_data.get("payload", {})
                hdrs = _parse_header_map(payload.get("headers", []))
                subject = hdrs.get("subject", "(No subject)")
                sender_domain = _extract_sender_domain(hdrs.get("from", ""))
                received_at = _parse_received_at(hdrs, msg_data.get("internalDate"))
                body_text = sanitize_body_text(_extract_body_from_payload(payload))
                source_id = make_opaque_source_id(account_id, msg_id)

                envelopes.append(
                    {
                        "source_id": source_id,
                        "received_at": received_at,
                        "sender_domain": sender_domain,
                        "subject": subject,
                        "body_text": body_text,
                    }
                )
                evidence.append(
                    {
                        "source_id": source_id,
                        "gmail_message_id": msg_id,
                        "received_at": received_at,
                        "sender_domain": sender_domain,
                        "subject": subject,
                    }
                )
            return ScanOutput(messages=envelopes, evidence_records=evidence, partial=partial)
    except Exception as exc:
        return ScanOutput(messages=[], evidence_records=[], partial=True, error=str(exc))
