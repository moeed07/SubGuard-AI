"""Run the optimizer on the separate fictional catalog from the merge guide."""
import argparse
import asyncio
import json

from .api import build_portfolio, optimize_portfolio, run_review
from .fictional import AS_OF, TIMEZONE


def demo_plans(*, unique_ide=False):
    return [
        {"plan_id": "A", "currency": "PKR", "monthly_cost_minor": 300000, "features": ["coding", "writing"]},
        {"plan_id": "B", "currency": "PKR", "monthly_cost_minor": 200000, "features": ["writing"]},
        {"plan_id": "C", "currency": "PKR", "monthly_cost_minor": 150000, "features": ["design"]},
        {"plan_id": "D", "currency": "PKR", "monthly_cost_minor": 250000,
         "features": ["coding", "ide"] if unique_ide else ["coding"]},
    ]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--live", action="store_true", help="Ask Gemini to use the real stdio optimizer tool.")
    args = parser.parse_args()
    if args.live:
        snapshot = dict(build_portfolio([], AS_OF, TIMEZONE), optimizer_plans=demo_plans())
        result = asyncio.run(run_review(
            snapshot, "Which plans would preserve every listed feature at the lowest monthly cost?",
        ))
        print(json.dumps(result, indent=2))
        return int(result["status"] != "complete" or not any(
            call["tool"] == "optimize_subscription_features" and call["outcome"] == "ok"
            for call in result["trace"]
        ))

    print(json.dumps({
        "fictional_catalog": optimize_portfolio(demo_plans()),
        "with_unique_ide_feature": optimize_portfolio(demo_plans(unique_ide=True)),
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
