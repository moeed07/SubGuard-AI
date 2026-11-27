"""Opt-in live Gemini and real stdio MCP smoke test with fictional emails."""
import argparse
import asyncio
import json
import os
from time import perf_counter

from .agent import DEFAULT_MODEL
from .api import build_portfolio, extract_events, run_review
from .fictional import AS_OF, TIMEZONE, fictional_messages

GOALS = {
    "conflict": "Which notice determines what Design Pro will bill me next?",
    "cost": "What are my recurring costs?",
    "automatic": None,
}


async def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--goal", choices=GOALS, default="conflict")
    choice = parser.parse_args().goal
    portfolio = build_portfolio(
        extract_events(fictional_messages(canceled=choice == "conflict")), AS_OF, TIMEZONE
    )
    start = perf_counter()
    result = await run_review(portfolio, GOALS[choice])
    print(json.dumps({
        "test": "live_gemini_real_stdio_mcp",
        "model": os.getenv("GEMINI_MODEL") or DEFAULT_MODEL,
        "goal": choice,
        "elapsed_seconds": round(perf_counter() - start, 2),
        **result,
    }, indent=2))
    successful = [call for call in result["trace"] if call["outcome"] == "ok"]
    tools = {call["tool"] for call in successful}
    if result["status"] != "complete":
        return 1
    if choice == "cost":
        return int(
            tools != {"get_portfolio"} or bool(result["items"])
            or "PKR 3,000.00" not in result["summary"]
        )
    if choice == "conflict":
        return int(not any(
            call["tool"] == "get_subscription_events" and "m8" in call["evidence_ids"]
            for call in successful
        ) or "m8" not in result["summary"] or bool(result["items"]))
    return int(len(result["items"]) != 1 or result["items"][0]["evidence_ids"] != ["m5"])


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
