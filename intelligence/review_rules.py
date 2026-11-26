"""The available proposal targets for one billing snapshot."""
from datetime import date, timedelta


def reviewable_charges(portfolio):
    start = date.fromisoformat(portfolio["as_of"])
    end = start + timedelta(days=7)
    for row in portfolio["due"]:
        target = row["date"]
        if (
            row["date_basis"] != "confirmed" or not isinstance(target, str) or not row["evidence_ids"]
            or row["kind"] not in {"renewal", "trial_conversion"}
            or row["subscription_key"] not in portfolio["timelines"]
        ):
            continue
        try:
            day = date.fromisoformat(target)
        except ValueError:
            continue
        if target == day.isoformat() and start <= day <= end:
            yield row
