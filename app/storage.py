"""Account-scoped persistence for SubGuard AI (SQLite local/test + Firestore prod)."""

from __future__ import annotations

import json
import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


class LocalStore:
    """Thread-safe SQLite store for local development and automated tests."""

    def __init__(self, db_path: str = ".subguard_data/subguard.db") -> None:
        self._db_path = db_path
        if db_path != ":memory:":
            Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._conn = sqlite3.connect(db_path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._init_schema()

    def _init_schema(self) -> None:
        with self._lock:
            cur = self._conn.cursor()
            cur.executescript(
                """
                CREATE TABLE IF NOT EXISTS accounts (
                    account_id TEXT PRIMARY KEY,
                    encrypted_token TEXT,
                    token_expires_at INTEGER DEFAULT 0,
                    scan_version INTEGER DEFAULT 0,
                    last_successful_scan TEXT,
                    scan_status TEXT DEFAULT 'never',
                    scan_error TEXT,
                    partial INTEGER DEFAULT 0,
                    is_demo INTEGER DEFAULT 0
                );
                CREATE TABLE IF NOT EXISTS evidence (
                    account_id TEXT NOT NULL,
                    source_id TEXT NOT NULL,
                    gmail_message_id TEXT NOT NULL,
                    received_at TEXT NOT NULL,
                    sender_domain TEXT NOT NULL,
                    subject TEXT NOT NULL,
                    PRIMARY KEY (account_id, source_id)
                );
                CREATE TABLE IF NOT EXISTS events (
                    account_id TEXT NOT NULL,
                    event_id TEXT NOT NULL,
                    source_id TEXT NOT NULL,
                    received_at TEXT NOT NULL,
                    subscription_key TEXT NOT NULL,
                    kind TEXT NOT NULL,
                    currency TEXT,
                    amount_minor INTEGER,
                    cycle TEXT,
                    transaction_ref TEXT,
                    event_date TEXT,
                    effective_date TEXT,
                    next_charge_date TEXT,
                    date_basis TEXT,
                    PRIMARY KEY (account_id, event_id)
                );
                CREATE TABLE IF NOT EXISTS portfolios (
                    account_id TEXT PRIMARY KEY,
                    scan_version INTEGER NOT NULL,
                    portfolio_json TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS review_items (
                    account_id TEXT NOT NULL,
                    item_key TEXT NOT NULL,
                    subscription_key TEXT NOT NULL,
                    kind TEXT NOT NULL,
                    target_date TEXT,
                    state TEXT NOT NULL,
                    evidence_ids_json TEXT NOT NULL,
                    explanation TEXT NOT NULL,
                    scan_version INTEGER NOT NULL,
                    PRIMARY KEY (account_id, item_key)
                );
                CREATE TABLE IF NOT EXISTS review_meta (
                    account_id TEXT PRIMARY KEY,
                    status TEXT NOT NULL,
                    summary TEXT NOT NULL,
                    trace_json TEXT NOT NULL,
                    scan_version INTEGER NOT NULL
                );
                CREATE TABLE IF NOT EXISTS reminder_jobs (
                    job_id TEXT PRIMARY KEY,
                    account_id TEXT NOT NULL,
                    subscription_key TEXT NOT NULL,
                    reminder_type TEXT NOT NULL,
                    due_at TEXT NOT NULL,
                    target_date TEXT NOT NULL,
                    status TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS notifications (
                    notification_id TEXT PRIMARY KEY,
                    account_id TEXT NOT NULL,
                    job_id TEXT NOT NULL,
                    subscription_key TEXT NOT NULL,
                    message TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                """
            )
            self._conn.commit()

    def close(self) -> None:
        with self._lock:
            self._conn.close()

    # --- Accounts & OAuth tokens ---

    def upsert_account(
        self,
        account_id: str,
        encrypted_token: Optional[str] = None,
        token_expires_at: int = 0,
        is_demo: Optional[bool] = None,
    ) -> None:
        with self._lock:
            existing = self.get_account(account_id)
            if existing:
                self._conn.execute(
                    """
                    UPDATE accounts
                    SET encrypted_token = COALESCE(?, encrypted_token),
                        token_expires_at = CASE WHEN ? > 0 THEN ? ELSE token_expires_at END,
                        is_demo = COALESCE(?, is_demo)
                    WHERE account_id = ?
                    """,
                    (
                        encrypted_token,
                        token_expires_at,
                        token_expires_at,
                        int(is_demo) if is_demo is not None else None,
                        account_id,
                    ),
                )
            else:
                self._conn.execute(
                    """
                    INSERT INTO accounts (account_id, encrypted_token, token_expires_at, is_demo)
                    VALUES (?, ?, ?, ?)
                    """,
                    (account_id, encrypted_token, token_expires_at, int(bool(is_demo))),
                )
            self._conn.commit()

    def get_account(self, account_id: str) -> Optional[dict[str, Any]]:
        with self._lock:
            row = self._conn.execute(
                "SELECT * FROM accounts WHERE account_id = ?", (account_id,)
            ).fetchone()
            return dict(row) if row else None

    def clear_account_token(self, account_id: str) -> None:
        with self._lock:
            self._conn.execute(
                "UPDATE accounts SET encrypted_token = NULL, token_expires_at = 0 WHERE account_id = ?",
                (account_id,),
            )
            self._conn.commit()

    def next_scan_version(self, account_id: str) -> int:
        with self._lock:
            self.upsert_account(account_id)
            self._conn.execute(
                "UPDATE accounts SET scan_version = scan_version + 1 WHERE account_id = ?",
                (account_id,),
            )
            self._conn.commit()
            row = self._conn.execute(
                "SELECT scan_version FROM accounts WHERE account_id = ?", (account_id,)
            ).fetchone()
            return int(row["scan_version"])

    def update_scan_status(
        self,
        account_id: str,
        scan_version: int,
        scan_status: str,
        partial: bool = False,
        scan_error: Optional[str] = None,
    ) -> bool:
        with self._lock:
            acct = self.get_account(account_id)
            if not acct or int(acct["scan_version"]) != scan_version:
                return False
            last_ok = utc_now_iso() if scan_status in ("ok", "empty", "partial") else acct["last_successful_scan"]
            self._conn.execute(
                """
                UPDATE accounts
                SET scan_status = ?, partial = ?, scan_error = ?, last_successful_scan = ?
                WHERE account_id = ? AND scan_version = ?
                """,
                (scan_status, int(partial), scan_error, last_ok, account_id, scan_version),
            )
            self._conn.commit()
            return True

    # --- Evidence & Events ---

    def upsert_evidence(self, account_id: str, items: list[dict[str, Any]]) -> None:
        with self._lock:
            for item in items:
                self._conn.execute(
                    """
                    INSERT INTO evidence (account_id, source_id, gmail_message_id, received_at, sender_domain, subject)
                    VALUES (?, ?, ?, ?, ?, ?)
                    ON CONFLICT(account_id, source_id) DO UPDATE SET
                        gmail_message_id = excluded.gmail_message_id,
                        received_at = excluded.received_at,
                        sender_domain = excluded.sender_domain,
                        subject = excluded.subject
                    """,
                    (
                        account_id,
                        item["source_id"],
                        item["gmail_message_id"],
                        item["received_at"],
                        item["sender_domain"],
                        item["subject"],
                    ),
                )
            self._conn.commit()

    def get_evidence(self, account_id: str, source_id: str) -> Optional[dict[str, Any]]:
        with self._lock:
            row = self._conn.execute(
                "SELECT * FROM evidence WHERE account_id = ? AND source_id = ?",
                (account_id, source_id),
            ).fetchone()
            return dict(row) if row else None

    def list_evidence(self, account_id: str) -> list[dict[str, Any]]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT * FROM evidence WHERE account_id = ? ORDER BY received_at DESC",
                (account_id,),
            ).fetchall()
            return [dict(r) for r in rows]

    def upsert_events(self, account_id: str, events: list[dict[str, Any]]) -> None:
        with self._lock:
            for ev in events:
                self._conn.execute(
                    """
                    INSERT INTO events (
                        account_id, event_id, source_id, received_at, subscription_key,
                        kind, currency, amount_minor, cycle, transaction_ref,
                        event_date, effective_date, next_charge_date, date_basis
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(account_id, event_id) DO UPDATE SET
                        source_id = excluded.source_id,
                        received_at = excluded.received_at,
                        subscription_key = excluded.subscription_key,
                        kind = excluded.kind,
                        currency = excluded.currency,
                        amount_minor = excluded.amount_minor,
                        cycle = excluded.cycle,
                        transaction_ref = excluded.transaction_ref,
                        event_date = excluded.event_date,
                        effective_date = excluded.effective_date,
                        next_charge_date = excluded.next_charge_date,
                        date_basis = excluded.date_basis
                    """,
                    (
                        account_id,
                        ev["event_id"],
                        ev["source_id"],
                        ev["received_at"],
                        ev["subscription_key"],
                        ev["kind"],
                        ev.get("currency"),
                        ev.get("amount_minor"),
                        ev.get("cycle"),
                        ev.get("transaction_ref"),
                        ev.get("event_date"),
                        ev.get("effective_date"),
                        ev.get("next_charge_date"),
                        ev.get("date_basis"),
                    ),
                )
            self._conn.commit()

    def list_events(self, account_id: str) -> list[dict[str, Any]]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT * FROM events WHERE account_id = ? ORDER BY received_at ASC, event_id ASC",
                (account_id,),
            ).fetchall()
            result = []
            for r in rows:
                d = dict(r)
                d.pop("account_id", None)
                result.append(d)
            return result

    # --- Portfolio & Review Items ---

    def save_portfolio(self, account_id: str, scan_version: int, portfolio: dict[str, Any]) -> bool:
        with self._lock:
            acct = self.get_account(account_id)
            if not acct or int(acct["scan_version"]) != scan_version:
                return False
            self._conn.execute(
                """
                INSERT INTO portfolios (account_id, scan_version, portfolio_json)
                VALUES (?, ?, ?)
                ON CONFLICT(account_id) DO UPDATE SET
                    scan_version = excluded.scan_version,
                    portfolio_json = excluded.portfolio_json
                """,
                (account_id, scan_version, json.dumps(portfolio)),
            )
            self._conn.commit()
            return True

    def get_portfolio(self, account_id: str) -> Optional[dict[str, Any]]:
        with self._lock:
            row = self._conn.execute(
                "SELECT portfolio_json FROM portfolios WHERE account_id = ?",
                (account_id,),
            ).fetchone()
            return json.loads(row["portfolio_json"]) if row else None

    def commit_review(
        self,
        account_id: str,
        scan_version: int,
        review_result: dict[str, Any],
        valid_subscriptions: set[str],
        valid_evidence: set[str],
    ) -> bool:
        with self._lock:
            acct = self.get_account(account_id)
            if not acct or int(acct["scan_version"]) != scan_version:
                return False

            status = review_result.get("status", "failed")
            summary = review_result.get("summary", "")
            trace = review_result.get("trace", [])

            self._conn.execute(
                """
                INSERT INTO review_meta (account_id, status, summary, trace_json, scan_version)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(account_id) DO UPDATE SET
                    status = excluded.status,
                    summary = excluded.summary,
                    trace_json = excluded.trace_json,
                    scan_version = excluded.scan_version
                """,
                (account_id, status, summary, json.dumps(trace), scan_version),
            )

            # Only persist items whose subscription & evidence belong to the active snapshot
            if status in ("complete", "partial"):
                incoming_keys: set[str] = set()
                for item in review_result.get("items", []):
                    sub_key = item.get("subscription_key", "")
                    ev_ids = item.get("evidence_ids", [])
                    if sub_key not in valid_subscriptions:
                        continue
                    if not ev_ids or not all(eid in valid_evidence for eid in ev_ids):
                        continue
                    kind = item.get("kind", "review")
                    target_date = item.get("target_date") or ""
                    item_key = f"{account_id}:{sub_key}:{kind}:{target_date}"
                    incoming_keys.add(item_key)
                    state = item.get("state", "open")
                    self._conn.execute(
                        """
                        INSERT INTO review_items (
                            account_id, item_key, subscription_key, kind, target_date,
                            state, evidence_ids_json, explanation, scan_version
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                        ON CONFLICT(account_id, item_key) DO UPDATE SET
                            state = excluded.state,
                            evidence_ids_json = excluded.evidence_ids_json,
                            explanation = excluded.explanation,
                            scan_version = excluded.scan_version
                        """,
                        (
                            account_id,
                            item_key,
                            sub_key,
                            kind,
                            target_date,
                            state,
                            json.dumps(ev_ids),
                            item.get("explanation", ""),
                            scan_version,
                        ),
                    )
                # Resolve superseded open items on date change or removal
                existing_rows = self._conn.execute(
                    "SELECT item_key FROM review_items WHERE account_id = ? AND state = 'open'",
                    (account_id,),
                ).fetchall()
                for row in existing_rows:
                    if row["item_key"] not in incoming_keys and status == "complete":
                        self._conn.execute(
                            "UPDATE review_items SET state = 'resolved' WHERE account_id = ? AND item_key = ?",
                            (account_id, row["item_key"]),
                        )

            self._conn.commit()
            return True

    def get_review(self, account_id: str) -> dict[str, Any]:
        with self._lock:
            meta = self._conn.execute(
                "SELECT * FROM review_meta WHERE account_id = ?", (account_id,)
            ).fetchone()
            rows = self._conn.execute(
                "SELECT * FROM review_items WHERE account_id = ? ORDER BY target_date ASC",
                (account_id,),
            ).fetchall()
            items = [
                {
                    "item_key": r["item_key"],
                    "subscription_key": r["subscription_key"],
                    "kind": r["kind"],
                    "target_date": r["target_date"],
                    "state": r["state"],
                    "evidence_ids": json.loads(r["evidence_ids_json"]),
                    "explanation": r["explanation"],
                }
                for r in rows
            ]
            if not meta:
                return {"status": "none", "summary": "", "trace": [], "items": items}
            return {
                "status": meta["status"],
                "summary": meta["summary"],
                "trace": json.loads(meta["trace_json"]),
                "items": items,
            }

    # --- Reminders & Notifications ---

    def create_reminder_job(
        self,
        account_id: str,
        subscription_key: str,
        reminder_type: str,
        due_at: str,
        target_date: str,
    ) -> dict[str, Any]:
        job_id = f"{account_id}:{subscription_key}:{reminder_type}"
        now = utc_now_iso()
        with self._lock:
            self._conn.execute(
                """
                INSERT INTO reminder_jobs (
                    job_id, account_id, subscription_key, reminder_type,
                    due_at, target_date, status, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, 'pending', ?)
                ON CONFLICT(job_id) DO UPDATE SET
                    due_at = excluded.due_at,
                    target_date = excluded.target_date,
                    status = CASE WHEN reminder_jobs.status = 'delivered' THEN 'delivered' ELSE 'pending' END
                """,
                (job_id, account_id, subscription_key, reminder_type, due_at, target_date, now),
            )
            self._conn.commit()
            row = self._conn.execute(
                "SELECT * FROM reminder_jobs WHERE job_id = ?", (job_id,)
            ).fetchone()
            return dict(row)

    def list_reminders(self, account_id: str) -> list[dict[str, Any]]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT * FROM reminder_jobs WHERE account_id = ? ORDER BY due_at ASC",
                (account_id,),
            ).fetchall()
            return [dict(r) for r in rows]

    def cancel_reminders_for_subscription(self, account_id: str, subscription_key: str) -> int:
        with self._lock:
            cur = self._conn.execute(
                """
                UPDATE reminder_jobs
                SET status = 'cancelled'
                WHERE account_id = ? AND subscription_key = ? AND status = 'pending'
                """,
                (account_id, subscription_key),
            )
            self._conn.commit()
            return cur.rowcount

    def deliver_due_jobs(self, now_iso: Optional[str] = None) -> int:
        """Atomically deliver due pending jobs if the subscription still has an active/confirmed charge."""
        now = now_iso or utc_now_iso()
        delivered_count = 0
        with self._lock:
            due_rows = self._conn.execute(
                "SELECT * FROM reminder_jobs WHERE status = 'pending' AND due_at <= ?",
                (now,),
            ).fetchall()
            for row in due_rows:
                job_id = row["job_id"]
                account_id = row["account_id"]
                sub_key = row["subscription_key"]
                portfolio = self.get_portfolio(account_id)
                still_due = False
                if portfolio:
                    for due_item in portfolio.get("due", []):
                        if due_item.get("subscription_key") == sub_key:
                            still_due = True
                            break
                if not still_due:
                    self._conn.execute(
                        "UPDATE reminder_jobs SET status = 'cancelled' WHERE job_id = ?",
                        (job_id,),
                    )
                    continue

                notif_id = f"notif:{job_id}"
                msg = f"Reminder: {sub_key} has a confirmed upcoming charge on {row['target_date']}."
                self._conn.execute(
                    """
                    INSERT OR IGNORE INTO notifications (
                        notification_id, account_id, job_id, subscription_key, message, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (notif_id, account_id, job_id, sub_key, msg, now),
                )
                self._conn.execute(
                    "UPDATE reminder_jobs SET status = 'delivered' WHERE job_id = ?",
                    (job_id,),
                )
                delivered_count += 1
            self._conn.commit()
        return delivered_count

    def list_notifications(self, account_id: str) -> list[dict[str, Any]]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT * FROM notifications WHERE account_id = ? ORDER BY created_at DESC",
                (account_id,),
            ).fetchall()
            return [dict(r) for r in rows]

    def delete_account_data(self, account_id: str) -> None:
        with self._lock:
            for table in (
                "notifications",
                "reminder_jobs",
                "review_items",
                "review_meta",
                "portfolios",
                "events",
                "evidence",
                "accounts",
            ):
                self._conn.execute(f"DELETE FROM {table} WHERE account_id = ?", (account_id,))
            self._conn.commit()
