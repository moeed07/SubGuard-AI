"""Google Cloud Firestore persistence for SubGuard AI production deployment."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional

from google.cloud import firestore


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


class FirestoreStore:
    """Account-scoped Firestore store with transactional job delivery."""

    def __init__(self, project_id: str) -> None:
        self._db = firestore.Client(project=project_id)

    def _acct_ref(self, account_id: str) -> firestore.DocumentReference:
        return self._db.collection("accounts").document(account_id)

    def upsert_account(
        self,
        account_id: str,
        encrypted_token: Optional[str] = None,
        token_expires_at: int = 0,
        is_demo: Optional[bool] = None,
        encrypted_email: Optional[str] = None,
    ) -> None:
        ref = self._acct_ref(account_id)
        data: dict[str, Any] = {"account_id": account_id}
        if is_demo is not None:
            data["is_demo"] = int(is_demo)
        if encrypted_token is not None:
            data["encrypted_token"] = encrypted_token
        if encrypted_email is not None:
            data["encrypted_email"] = encrypted_email
        if token_expires_at > 0:
            data["token_expires_at"] = token_expires_at
        if not ref.get().exists:
            data.setdefault("is_demo", 0)
            data.setdefault("scan_version", 0)
            data.setdefault("scan_status", "never")
            data.setdefault("partial", 0)
        ref.set(data, merge=True)

    def get_account(self, account_id: str) -> Optional[dict[str, Any]]:
        snap = self._acct_ref(account_id).get()
        return snap.to_dict() if snap.exists else None

    def clear_account_token(self, account_id: str) -> None:
        self._acct_ref(account_id).set(
            {"encrypted_token": None, "token_expires_at": 0}, merge=True
        )

    def next_scan_version(self, account_id: str) -> int:
        ref = self._acct_ref(account_id)

        @firestore.transactional
        def _txn(transaction: firestore.Transaction) -> int:
            snap = ref.get(transaction=transaction)
            cur = int((snap.to_dict() or {}).get("scan_version", 0)) if snap.exists else 0
            nxt = cur + 1
            transaction.set(ref, {"account_id": account_id, "scan_version": nxt}, merge=True)
            return nxt

        return _txn(self._db.transaction())

    def update_scan_status(
        self,
        account_id: str,
        scan_version: int,
        scan_status: str,
        partial: bool = False,
        scan_error: Optional[str] = None,
    ) -> bool:
        ref = self._acct_ref(account_id)
        snap = ref.get()
        if not snap.exists or int((snap.to_dict() or {}).get("scan_version", 0)) != scan_version:
            return False
        update: dict[str, Any] = {
            "scan_status": scan_status,
            "partial": int(partial),
            "scan_error": scan_error,
        }
        if scan_status in ("ok", "empty", "partial"):
            update["last_successful_scan"] = _utc_now_iso()
        ref.set(update, merge=True)
        return True

    def upsert_evidence(self, account_id: str, items: list[dict[str, Any]]) -> None:
        col = self._acct_ref(account_id).collection("evidence")
        for item in items:
            col.document(item["source_id"]).set({"account_id": account_id, **item}, merge=True)

    def get_evidence(self, account_id: str, source_id: str) -> Optional[dict[str, Any]]:
        snap = self._acct_ref(account_id).collection("evidence").document(source_id).get()
        return snap.to_dict() if snap.exists else None

    def list_evidence(self, account_id: str) -> list[dict[str, Any]]:
        docs = self._acct_ref(account_id).collection("evidence").stream()
        items = [d.to_dict() for d in docs]
        items.sort(key=lambda x: x.get("received_at", ""), reverse=True)
        return items

    def upsert_events(self, account_id: str, events: list[dict[str, Any]]) -> None:
        col = self._acct_ref(account_id).collection("events")
        for ev in events:
            col.document(ev["event_id"]).set(ev, merge=True)

    def list_events(self, account_id: str) -> list[dict[str, Any]]:
        docs = self._acct_ref(account_id).collection("events").stream()
        items = [d.to_dict() for d in docs]
        items.sort(key=lambda x: (x.get("received_at", ""), x.get("event_id", "")))
        return items

    def save_portfolio(self, account_id: str, scan_version: int, portfolio: dict[str, Any]) -> bool:
        acct = self.get_account(account_id)
        if not acct or int(acct.get("scan_version", 0)) != scan_version:
            return False
        self._acct_ref(account_id).collection("meta").document("portfolio").set(
            {"scan_version": scan_version, "portfolio": portfolio}
        )
        return True

    def get_portfolio(self, account_id: str) -> Optional[dict[str, Any]]:
        snap = self._acct_ref(account_id).collection("meta").document("portfolio").get()
        return (snap.to_dict() or {}).get("portfolio") if snap.exists else None

    def commit_review(
        self,
        account_id: str,
        scan_version: int,
        review_result: dict[str, Any],
        valid_subscriptions: set[str],
        valid_evidence: set[str],
    ) -> bool:
        acct = self.get_account(account_id)
        if not acct or int(acct.get("scan_version", 0)) != scan_version:
            return False

        status = review_result.get("status", "failed")
        self._acct_ref(account_id).collection("meta").document("review").set(
            {
                "status": status,
                "summary": review_result.get("summary", ""),
                "trace": review_result.get("trace", []),
                "scan_version": scan_version,
            }
        )

        if status in ("complete", "partial"):
            col = self._acct_ref(account_id).collection("review_items")
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
                col.document(item_key).set(
                    {
                        "item_key": item_key,
                        "subscription_key": sub_key,
                        "kind": kind,
                        "target_date": target_date,
                        "state": item.get("state", "open"),
                        "evidence_ids": ev_ids,
                        "explanation": item.get("explanation", ""),
                        "scan_version": scan_version,
                    }
                )
            if status == "complete":
                for doc in col.where("state", "==", "open").stream():
                    if doc.id not in incoming_keys:
                        col.document(doc.id).set({"state": "resolved"}, merge=True)
        return True

    def get_review(self, account_id: str) -> dict[str, Any]:
        meta_snap = self._acct_ref(account_id).collection("meta").document("review").get()
        items = [d.to_dict() for d in self._acct_ref(account_id).collection("review_items").stream()]
        items.sort(key=lambda x: x.get("target_date", ""))
        if not meta_snap.exists:
            return {"status": "none", "summary": "", "trace": [], "items": items}
        meta = meta_snap.to_dict() or {}
        return {
            "status": meta.get("status", "none"),
            "summary": meta.get("summary", ""),
            "trace": meta.get("trace", []),
            "items": items,
        }

    def create_reminder_job(
        self,
        account_id: str,
        subscription_key: str,
        reminder_type: str,
        due_at: str,
        target_date: str,
    ) -> dict[str, Any]:
        job_id = f"{account_id}:{subscription_key}:{reminder_type}"
        ref = self._db.collection("reminder_jobs").document(job_id)
        snap = ref.get()
        status = "delivered" if (snap.exists and (snap.to_dict() or {}).get("status") == "delivered") else "pending"
        data = {
            "job_id": job_id,
            "account_id": account_id,
            "subscription_key": subscription_key,
            "reminder_type": reminder_type,
            "due_at": due_at,
            "target_date": target_date,
            "status": status,
            "created_at": _utc_now_iso(),
        }
        ref.set(data, merge=True)
        return data

    def list_reminders(self, account_id: str) -> list[dict[str, Any]]:
        docs = self._db.collection("reminder_jobs").where("account_id", "==", account_id).stream()
        items = [d.to_dict() for d in docs]
        items.sort(key=lambda x: x.get("due_at", ""))
        return items

    def cancel_reminders_for_subscription(self, account_id: str, subscription_key: str) -> int:
        docs = (
            self._db.collection("reminder_jobs")
            .where("account_id", "==", account_id)
            .where("subscription_key", "==", subscription_key)
            .where("status", "==", "pending")
            .stream()
        )
        count = 0
        for d in docs:
            d.reference.set({"status": "cancelled"}, merge=True)
            count += 1
        return count

    def deliver_due_jobs(
        self,
        now_iso: Optional[str] = None,
        on_deliver: Optional[Any] = None,
    ) -> int:
        now = now_iso or _utc_now_iso()
        delivered = 0
        docs = self._db.collection("reminder_jobs").where("status", "==", "pending").stream()
        for doc in docs:
            job = doc.to_dict() or {}
            if job.get("due_at", "") > now:
                continue
            account_id = job["account_id"]
            sub_key = job["subscription_key"]
            portfolio = self.get_portfolio(account_id)
            still_due = bool(
                portfolio and any(d.get("subscription_key") == sub_key and d.get("date") for d in portfolio.get("due", []))
            )
            if not still_due and portfolio:
                choices = self.list_cycle_choices(account_id)
                sub_entry = next(
                    (s for s in portfolio.get("subscriptions", []) if s.get("subscription_key") == sub_key),
                    None,
                )
                if sub_key in choices and sub_entry and sub_entry.get("auto_renew") is not False:
                    still_due = True
            notif_ref = self._acct_ref(account_id).collection("notifications").document(f"notif:{doc.id}")

            @firestore.transactional
            def _deliver_txn(transaction: firestore.Transaction) -> bool:
                fresh = doc.reference.get(transaction=transaction)
                if not fresh.exists or (fresh.to_dict() or {}).get("status") != "pending":
                    return False
                if not still_due:
                    transaction.set(doc.reference, {"status": "cancelled"}, merge=True)
                    return False
                transaction.set(
                    notif_ref,
                    {
                        "notification_id": f"notif:{doc.id}",
                        "account_id": account_id,
                        "job_id": doc.id,
                        "subscription_key": sub_key,
                        "message": f"Reminder ({job.get('reminder_type')}): {sub_key} has an upcoming charge on {job.get('target_date')}.",
                        "created_at": now,
                    },
                )
                transaction.set(doc.reference, {"status": "delivered"}, merge=True)
                return True

            if _deliver_txn(self._db.transaction()):
                delivered += 1
                if on_deliver is not None:
                    try:
                        on_deliver(job)
                    except Exception:
                        pass
        return delivered

    def list_notifications(self, account_id: str) -> list[dict[str, Any]]:
        docs = self._acct_ref(account_id).collection("notifications").stream()
        items = [d.to_dict() for d in docs]
        items.sort(key=lambda x: x.get("created_at", ""), reverse=True)
        return items

    def set_cycle_choice(self, account_id: str, subscription_key: str, cycle: str) -> None:
        self._acct_ref(account_id).collection("cycle_choices").document(subscription_key).set(
            {"subscription_key": subscription_key, "cycle": cycle, "updated_at": _utc_now_iso()}
        )

    def clear_cycle_choice(self, account_id: str, subscription_key: str) -> None:
        self._acct_ref(account_id).collection("cycle_choices").document(subscription_key).delete()

    def list_cycle_choices(self, account_id: str) -> dict[str, str]:
        docs = self._acct_ref(account_id).collection("cycle_choices").stream()
        return {d.id: (d.to_dict() or {}).get("cycle", "") for d in docs}

    def delete_account_data(self, account_id: str) -> None:
        acct = self._acct_ref(account_id)
        for sub in ("evidence", "events", "meta", "review_items", "notifications", "cycle_choices"):
            for doc in acct.collection(sub).stream():
                doc.reference.delete()
        acct.delete()
        for job in self._db.collection("reminder_jobs").where("account_id", "==", account_id).stream():
            job.reference.delete()
