import pytest

from intelligence.api import optimize_portfolio
from intelligence.optimizer import MAX_SELECTABLE_PLANS
from intelligence.optimizer_demo import demo_plans


@pytest.mark.parametrize(("unique_ide", "retained", "minimum"), [
    (False, ["A", "C"], 450_000), (True, ["B", "C", "D"], 600_000),
])
def test_exact_optimizer_preserves_every_feature_in_the_guide_catalog(unique_ide, retained, minimum):
    plans = demo_plans(unique_ide=unique_ide)
    result = optimize_portfolio(reversed(plans))
    assert result == optimize_portfolio(plans)
    currency = result["currencies"]["PKR"]
    assert result["status"] == "complete"
    assert currency["subsets_checked"] == 16
    assert currency["retained_plan_ids"] == retained
    assert currency["removal_candidate_ids"] == sorted({"A", "B", "C", "D"} - set(retained))
    expected_features = ["coding", "design", "ide", "writing"] if unique_ide else ["coding", "design", "writing"]
    assert currency["retained_features"] == expected_features
    assert currency["current_monthly_minor"] == 900_000
    assert currency["minimum_monthly_minor"] == minimum
    assert currency["monthly_reduction_minor"] == 900_000 - minimum


def test_protected_plans_stay_and_ties_prefer_fewer_removals_then_plan_id():
    base = {"currency": "USD", "features": ["writing"], "monthly_cost_minor": 500}
    plans = [dict(base, plan_id="B"), dict(base, plan_id="A"),
             dict(base, plan_id="free", features=[], monthly_cost_minor=0),
             dict(base, plan_id="locked", features=["design"], protected=True)]
    result = optimize_portfolio(plans)["currencies"]["USD"]
    assert result["retained_plan_ids"] == ["A", "free", "locked"]
    assert result["minimum_monthly_minor"] == 1000
    assert result["monthly_reduction_minor"] == 500


def test_missing_coverage_and_prices_are_disclosed_and_do_not_create_full_savings():
    fixed = [
        {"plan_id": "unknown-features", "currency": "PKR", "monthly_cost_minor": 1000, "features": None},
        {"plan_id": "unknown-price", "currency": "PKR", "monthly_cost_minor": None, "features": ["coding"]},
    ]
    result = optimize_portfolio(demo_plans() + fixed)
    assert result["status"] == "partial"
    assert result["missing_fields_by_plan"] == {
        "unknown-features": ["features"], "unknown-price": ["monthly_cost_minor"],
    }
    group = result["currencies"]["PKR"]
    assert group["retained_plan_ids"] == ["B", "C", "unknown-features", "unknown-price"]
    assert group["current_monthly_minor"] is None
    assert group["minimum_monthly_minor"] is None
    assert group["monthly_reduction_minor"] is None


def test_currencies_are_optimized_separately_and_uncovered_requirements_are_explicit():
    plans = demo_plans() + [{"plan_id": "USD-note", "currency": "USD", "monthly_cost_minor": 50, "features": ["design"]}]
    outcome = optimize_portfolio(plans)
    assert outcome["currencies"]["PKR"]["retained_plan_ids"] == ["A", "C"]
    assert outcome["currencies"]["USD"]["retained_plan_ids"] == ["USD-note"]
    scoped = optimize_portfolio(plans, ["writing"])
    assert scoped["currencies"]["PKR"]["retained_plan_ids"] == ["B"]
    unavailable = scoped["currencies"]["USD"]
    assert (unavailable["status"], unavailable["uncovered_features"]) == ("unavailable", ["writing"])


def test_exact_search_is_bounded_and_invalid_prices_are_rejected():
    plans = [dict(demo_plans()[0], plan_id=f"p{i}") for i in range(MAX_SELECTABLE_PLANS + 1)]
    result = optimize_portfolio(plans)["currencies"]["PKR"]
    assert result["reason"] == "too_many_selectable_plans"
    assert result["subsets_checked"] == 0
    with pytest.raises(ValueError, match="minor units"):
        optimize_portfolio([dict(plans[0], monthly_cost_minor=1.5)])
