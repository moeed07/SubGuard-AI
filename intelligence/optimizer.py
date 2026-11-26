"""Exact feature coverage for a small set of verified active plans."""
from collections import defaultdict
from collections.abc import Mapping
from dataclasses import dataclass
from itertools import combinations
import re

MAX_SELECTABLE_PLANS = 16


@dataclass(frozen=True)
class _Plan:
    plan_id: str
    currency: str | None
    monthly_cost_minor: int | None
    features: frozenset[str] | None
    protected: bool


def _features(values):
    if not isinstance(values, (list, tuple, set, frozenset)) or any(
        not isinstance(value, str) or not value.strip() for value in values
    ):
        raise ValueError("Features must be a collection of nonempty feature IDs.")
    return frozenset(values)


def _read_plans(plans):
    seen = set()
    for row in plans:
        if not isinstance(row, Mapping):
            raise ValueError("Each plan must be a dictionary of verified plan fields.")
        plan_id, currency = row.get("plan_id"), row.get("currency")
        cost, features, protected = row.get("monthly_cost_minor"), row.get("features"), row.get("protected", False)
        if not isinstance(plan_id, str) or not plan_id.strip() or plan_id in seen:
            raise ValueError("Each plan needs a unique nonempty plan_id.")
        if currency is not None and (not isinstance(currency, str) or not re.fullmatch(r"[A-Z]{3}", currency)):
            raise ValueError("Currency must be an uppercase three-letter code or null.")
        if cost is not None and (type(cost) is not int or cost < 0):
            raise ValueError("Monthly cost must be a nonnegative integer in minor units or null.")
        if not isinstance(protected, bool):
            raise ValueError("Protected must be a boolean.")
        seen.add(plan_id)
        yield _Plan(plan_id, currency, cost, None if features is None else _features(features), protected)


def _missing(plan):
    fields = ("currency", "monthly_cost_minor", "features")
    return [field for field in fields if getattr(plan, field) is None]


def _coverage(plans):
    return frozenset().union(*(plan.features or () for plan in plans))


def _optimize_currency(plans, capabilities, unknown_currency):
    available = _coverage(plans)
    required = available if capabilities is None else capabilities
    missing_ids = sorted(plan.plan_id for plan in plans if _missing(plan))
    locked = set(missing_ids) | {plan.plan_id for plan in plans if plan.protected}
    fixed = [plan for plan in plans if plan.plan_id in locked]
    candidates = [plan for plan in plans if plan.plan_id not in locked]
    result = {
        "status": "unavailable",
        "required_features": sorted(required),
        "uncovered_features": sorted(required - available),
        "retained_features": [],
        "retained_plan_ids": [],
        "removal_candidate_ids": [],
        "missing_plan_ids": missing_ids,
        "current_monthly_minor": None,
        "minimum_monthly_minor": None,
        "monthly_reduction_minor": None,
        "subsets_checked": 0,
    }
    if result["uncovered_features"]:
        return dict(result, reason="required_features_uncovered")
    if len(candidates) > MAX_SELECTABLE_PLANS:
        return dict(result, reason="too_many_selectable_plans")

    fixed_coverage = _coverage(fixed)
    best_score, best_features = None, frozenset()
    for count in range(len(candidates) + 1):
        for choice in combinations(candidates, count):
            coverage = fixed_coverage | _coverage(choice)
            if not required <= coverage:
                continue
            retained = tuple(sorted(locked | {plan.plan_id for plan in choice}))
            score = (sum(plan.monthly_cost_minor for plan in choice), -len(retained), retained)
            if best_score is None or score < best_score:
                best_score, best_features = score, coverage

    optimized_variable_cost, _, retained = best_score
    partial = bool(missing_ids or unknown_currency)
    result.update(
        status="partial" if partial else "complete",
        retained_features=sorted(best_features),
        retained_plan_ids=list(retained),
        removal_candidate_ids=sorted({plan.plan_id for plan in plans} - set(retained)),
        subsets_checked=2 ** len(candidates),
    )
    if not partial:
        current = sum(plan.monthly_cost_minor for plan in plans)
        minimum = sum(plan.monthly_cost_minor for plan in fixed) + optimized_variable_cost
        result.update(current_monthly_minor=current, minimum_monthly_minor=minimum,
                      monthly_reduction_minor=current - minimum)
    return result


def optimize_portfolio(plans, capabilities=None):
    """Compute conditional results per currency from a verified catalog and monthly prices.

    If capabilities is omitted, preserve every listed feature in each currency group.
    Otherwise require the specified feature IDs independently within each group.
    """
    required = None if capabilities is None else _features(capabilities)
    groups, missing = defaultdict(list), {}
    unknown_currency = False
    for plan in _read_plans(plans):
        fields = _missing(plan)
        if fields:
            missing[plan.plan_id] = fields
        if plan.currency is None:
            unknown_currency = True
        else:
            groups[plan.currency].append(plan)

    currencies = {currency: _optimize_currency(group, required, unknown_currency)
                  for currency, group in sorted(groups.items())}
    if not currencies or all(row["status"] == "unavailable" for row in currencies.values()):
        status = "unavailable"
    else:
        status = "partial" if missing or any(row["status"] != "complete" for row in currencies.values()) else "complete"
    return {"status": status, "currencies": currencies, "missing_fields_by_plan": dict(sorted(missing.items()))}
