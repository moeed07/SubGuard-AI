"""Session signing, CSRF tokens, OAuth state, and token encryption."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import secrets
import time
from typing import Optional

from cryptography.fernet import Fernet, InvalidToken


def _derive_fernet_key(raw_key: str) -> bytes:
    """Derive a valid 32-byte urlsafe base64 Fernet key from configuration."""
    if raw_key:
        try:
            decoded = base64.urlsafe_b64decode(raw_key.encode("utf-8"))
            if len(decoded) == 32:
                return raw_key.encode("utf-8")
        except Exception:
            pass
        digest = hashlib.sha256(raw_key.encode("utf-8")).digest()
        return base64.urlsafe_b64encode(digest)
    return Fernet.generate_key()


class SecurityManager:
    """Handles signed sessions, CSRF protection, OAuth state, and token encryption."""

    SESSION_COOKIE_NAME = "subguard_session"
    STATE_TTL_SECONDS = 600
    SESSION_TTL_SECONDS = 86400

    def __init__(self, session_secret: str, token_encryption_key: str) -> None:
        self._session_secret = (
            session_secret.encode("utf-8")
            if session_secret
            else secrets.token_bytes(32)
        )
        self._fernet = Fernet(_derive_fernet_key(token_encryption_key))
        self._oauth_states: dict[str, tuple[str, float]] = {}

    def _sign(self, payload_b64: str) -> str:
        sig = hmac.new(
            self._session_secret,
            payload_b64.encode("ascii"),
            hashlib.sha256,
        ).digest()
        return base64.urlsafe_b64encode(sig).decode("ascii").rstrip("=")

    def create_session_token(
        self,
        session_id: str,
        account_id: Optional[str] = None,
        is_demo: bool = False,
    ) -> str:
        payload = {
            "sid": session_id,
            "aid": account_id,
            "demo": is_demo,
            "exp": int(time.time()) + self.SESSION_TTL_SECONDS,
        }
        raw = json.dumps(payload, separators=(",", ":")).encode("utf-8")
        payload_b64 = base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")
        return f"{payload_b64}.{self._sign(payload_b64)}"

    def verify_session_token(self, token: Optional[str]) -> Optional[dict]:
        if not token or "." not in token:
            return None
        payload_b64, sig = token.split(".", 1)
        expected = self._sign(payload_b64)
        if not hmac.compare_digest(sig, expected):
            return None
        try:
            padded = payload_b64 + "=" * (-len(payload_b64) % 4)
            payload = json.loads(base64.urlsafe_b64decode(padded).decode("utf-8"))
        except Exception:
            return None
        if payload.get("exp", 0) < int(time.time()):
            return None
        return payload

    def create_csrf_token(self, session_id: str) -> str:
        msg = f"csrf:{session_id}".encode("utf-8")
        sig = hmac.new(self._session_secret, msg, hashlib.sha256).digest()
        return base64.urlsafe_b64encode(sig).decode("ascii").rstrip("=")

    def verify_csrf_token(self, session_id: str, token: Optional[str]) -> bool:
        if not session_id or not token:
            return False
        expected = self.create_csrf_token(session_id)
        return hmac.compare_digest(token, expected)

    def create_oauth_state(self, session_id: str) -> str:
        now = int(time.time())
        expired = [k for k, exp in self._oauth_states.items() if exp < now]
        for k in expired:
            self._oauth_states.pop(k, None)
        payload = {
            "sid": session_id,
            "nonce": secrets.token_urlsafe(12),
            "exp": now + self.STATE_TTL_SECONDS,
        }
        raw = json.dumps(payload, separators=(",", ":")).encode("utf-8")
        b64 = base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")
        return f"{b64}.{self._sign(b64)}"

    def consume_oauth_state(self, state: Optional[str], session_id: Optional[str]) -> bool:
        if not state or not session_id or "." not in state:
            return False
        b64, sig = state.split(".", 1)
        if not hmac.compare_digest(sig, self._sign(b64)):
            return False
        try:
            padded = b64 + "=" * (-len(b64) % 4)
            payload = json.loads(base64.urlsafe_b64decode(padded).decode("utf-8"))
        except Exception:
            return False
        now = int(time.time())
        if payload.get("exp", 0) < now:
            return False
        if not hmac.compare_digest(str(payload.get("sid", "")), session_id):
            return False
        nonce = str(payload.get("nonce", ""))
        if not nonce or nonce in self._oauth_states:
            return False
        self._oauth_states[nonce] = payload["exp"]
        return True

    def encrypt_token(self, plaintext: str) -> str:
        return self._fernet.encrypt(plaintext.encode("utf-8")).decode("ascii")

    def decrypt_token(self, ciphertext: str) -> Optional[str]:
        try:
            return self._fernet.decrypt(ciphertext.encode("ascii")).decode("utf-8")
        except InvalidToken:
            return None

    @staticmethod
    def hash_account_id(email_or_sub: str) -> str:
        digest = hashlib.sha256(email_or_sub.strip().lower().encode("utf-8")).hexdigest()
        return f"acct_{digest[:20]}"
