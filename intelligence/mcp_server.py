"""Private stdio tools. The only input file is selected by the backend."""
import argparse
from datetime import date, timedelta
import json
from pathlib import Path

from babel.numbers import get_currency_precision
from mcp.server.fastmcp import FastMCP
from mcp.types import CallToolResult, TextContent


def _response(payload):
    return CallToolResult(
        content=[TextContent(type="text", text=json.dumps(payload, ensure_ascii=False))],
        structuredContent=payload,
        isError="error" in payload,
    )


def _display_amount(currency, minor):
    if not currency or minor is None:
        return None
    precision = get_currency_precision(currency)
    whole, fraction = divmod(abs(minor), 10**precision)
    fraction_text = f".{fraction:0{precision}d}" if precision else ""
    sign = "-" if minor < 0 else ""
    return f"{currency} {sign}{whole:,}{fraction_text}"


def _display_charge(row):
    display = dict(row)
    minor = display.pop("amount_minor")
    display["amount"] = _display_amount(row["currency"], minor)
    return display


def create_server(portfolio):
    server = FastMCP("SubGuard billing evidence")

    @server.tool()
    def get_portfolio() -> CallToolResult:
        """Read totals, subscription status, and upcoming charges. Amounts are ready to quote."""
        evidence = {
            source
            for row in portfolio["subscriptions"] + portfolio["due"]
            for source in row["evidence_ids"]
        }
        return _response({
            **{key: portfolio[key] for key in ("as_of", "timezone", "subscriptions")},
            "totals": {
                currency: {
                    field.removesuffix("_minor"): _display_amount(currency, amount)
                    for field, amount in totals.items()
                }
                for currency, totals in portfolio["totals"].items()
            },
            "due": [_display_charge(row) for row in portfolio["due"]],
            "evidence_ids": sorted(evidence),
        })

    @server.tool()
    def get_subscription_events(subscription_key: str) -> CallToolResult:
        """Inspect a known plan's timeline when charge or cancellation evidence conflicts."""
        events = portfolio["timelines"].get(subscription_key)
        if events is None:
            return _response({"error": "Unknown subscription", "evidence_ids": []})
        return _response({
            "events": [_display_charge(event) for event in events],
            "evidence_ids": sorted({event["source_id"] for event in events}),
        })

    @server.tool()
    def upsert_review_item(
        subscription_key: str, kind: str, target_date: str, state: str, evidence_ids: list[str]
    ) -> CallToolResult:
        """Propose a review for a confirmed charge due within seven days.
        Copy subscription_key, kind, date (as target_date), and evidence_ids from one due row.
        Pass state="open". A proposal does not save or schedule anything.
        """
        rejected = _response({"error": "Proposal does not match a confirmed upcoming charge", "evidence_ids": []})
        try:
            target = date.fromisoformat(target_date)
        except ValueError:
            return rejected
        start = date.fromisoformat(portfolio["as_of"])
        if (
            target.isoformat() != target_date
            or not start <= target <= start + timedelta(days=7)
            or subscription_key not in portfolio["timelines"]
            or kind not in {"trial_conversion", "renewal"}
            or state != "open"
            or not evidence_ids
        ):
            return rejected
        sources = set(evidence_ids)
        matching = any(
            row["subscription_key"] == subscription_key
            and row["kind"] == kind
            and row["date"] == target_date
            and row["date_basis"] == "confirmed"
            and sources <= set(row["evidence_ids"])
            for row in portfolio["due"]
        )
        if not matching:
            return rejected
        sources = sorted(sources)
        label = "Trial converts to a paid plan" if kind == "trial_conversion" else "Renewal charge is scheduled"
        return _response({
            "item": {
                "subscription_key": subscription_key,
                "kind": kind,
                "target_date": target_date,
                "state": state,
                "evidence_ids": sources,
                "explanation": f"{label} on {target_date} (evidence: {', '.join(sources)}).",
            },
            "evidence_ids": sources,
        })

    return server


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("snapshot", type=Path)
    args = parser.parse_args()
    portfolio = json.loads(args.snapshot.read_text(encoding="utf-8"))
    create_server(portfolio).run(transport="stdio")


if __name__ == "__main__":
    main()
