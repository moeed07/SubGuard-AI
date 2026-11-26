"""Fixture tests. MCP is a real subprocess; the scripted model never calls Gemini."""
import asyncio
from types import SimpleNamespace

from google.adk.models.llm_response import LlmResponse
from google.adk.models import google_llm
from google.genai import types
from mcp import ClientSession
from mcp.client.stdio import stdio_client

from intelligence import agent
from intelligence.api import build_portfolio, extract_events, run_review
from intelligence.fictional import AS_OF, TIMEZONE, fictional_messages


def snapshot(*, canceled=False):
    return build_portfolio(extract_events(fictional_messages(canceled=canceled)), AS_OF, TIMEZONE)


def proposal(**changes):
    return {
        "subscription_key": "sketch-trial",
        "target_date": "2026-11-29",
        "kind": "trial_conversion",
        "state": "open",
        "evidence_ids": ["m5"],
        **changes,
    }


def test_real_stdio_tool_discovery_and_account_isolation():
    async def check():
        with agent.snapshot_file(snapshot(canceled=True)) as path:
            async with asyncio.timeout(20):
                async with stdio_client(agent.server_parameters(path)) as (read, write):
                    async with ClientSession(read, write) as session:
                        await session.initialize()
                        listed = await session.list_tools()
                        assert {tool.name for tool in listed.tools} == {
                            "get_portfolio", "get_subscription_events", "upsert_review_item",
                        }
                        result = await session.call_tool("get_portfolio")
                        assert "timelines" not in result.structuredContent
                        assert result.structuredContent["totals"]["PKR"] == {
                            "paid": "PKR 14,000.00",
                            "monthly_equivalent": "PKR 2,000.00",
                            "next_7d": "PKR 700.00",
                        }
                        assert result.structuredContent["due"][0]["amount"] == "PKR 700.00"
                        assert "amount_minor" not in result.structuredContent["due"][0]
                        result = await session.call_tool("get_subscription_events", {"subscription_key": "design-pro"})
                        assert result.structuredContent["evidence_ids"] == ["m3", "m4", "m8"]
                        result = await session.call_tool("get_subscription_events", {"subscription_key": "other-account"})
                        assert result.structuredContent["error"] == "Unknown subscription"

                        for args in (
                            proposal(evidence_ids=["m4"]),
                            proposal(target_date="2026-99-99"),
                            proposal(subscription_key="other-account"),
                            proposal(kind="payment"),
                            proposal(state="resolved"),
                            proposal(subscription_key="design-pro", kind="renewal",
                                     target_date="2026-12-01", evidence_ids=["m4"]),
                        ):
                            result = await session.call_tool("upsert_review_item", args)
                            assert "error" in result.structuredContent
                            assert "item" not in result.structuredContent
                        result = await session.call_tool("upsert_review_item", proposal())
                        item = result.structuredContent["item"]
                        assert item["evidence_ids"] == ["m5"]
                        assert "m5" in item["explanation"]
        assert not path.exists()

    asyncio.run(check())


async def scripted_generate(self, llm_request, stream=False):
    """Feed actual ADK with scripted function calls on its normal model seam."""
    responses = [
        part.function_response for content in llm_request.contents
        for part in content.parts or [] if part.function_response
    ]
    goal = llm_request.contents[0].parts[0].text
    if not responses:
        part = types.Part.from_function_call(name="get_portfolio", args={})
    elif len(responses) == 1 and goal == agent.DEFAULT_GOAL:
        part = types.Part.from_function_call(name="upsert_review_item", args=proposal(evidence_ids=["m4"]))
    elif len(responses) == 2 and goal == agent.DEFAULT_GOAL:
        part = types.Part.from_function_call(name="upsert_review_item", args=proposal())
    elif len(responses) == 1 and "Design Pro" in goal:
        part = types.Part.from_function_call(
            name="get_subscription_events", args={"subscription_key": "design-pro"}
        )
    else:
        part = types.Part.from_text(text="Finished the fictional review.")
    yield LlmResponse(content=types.Content(role="model", parts=[part]))


def test_scripted_adk_model_calls_real_mcp_and_reads_actual_responses(monkeypatch):
    monkeypatch.setenv("GOOGLE_API_KEY", "fixture-placeholder")
    monkeypatch.setattr(google_llm.Gemini, "generate_content_async", scripted_generate)
    canceled = snapshot(canceled=True)
    outcomes = asyncio.run(_review_each(canceled))
    assert [result["status"] for result in outcomes] == ["complete"] * 3, outcomes
    assert [[entry["tool"] for entry in result["trace"]] for result in outcomes] == [
        ["get_portfolio"],
        ["get_portfolio", "get_subscription_events"],
        ["get_portfolio", "upsert_review_item", "upsert_review_item"],
    ]
    assert outcomes[1]["trace"][-1]["evidence_ids"] == ["m3", "m4", "m8"]
    assert outcomes[0]["items"] == outcomes[1]["items"] == []
    assert [item["evidence_ids"] for item in outcomes[2]["items"]] == [["m5"]]
    assert [call["outcome"] for call in outcomes[2]["trace"]] == ["ok", "error", "ok"]


async def _review_each(portfolio):
    return [
        await run_review(portfolio, "What are my recurring costs?"),
        await run_review(portfolio, "What will Design Pro bill me next?"),
        await run_review(portfolio),
    ]


def test_timeout_returns_structured_failure_and_removes_snapshot(monkeypatch):
    paths = []

    async def stalled(path, *args):
        paths.append(path)
        await asyncio.Event().wait()

    monkeypatch.setenv("GOOGLE_API_KEY", "fixture-placeholder")
    monkeypatch.setattr(agent, "REVIEW_TIMEOUT", 0.05)
    monkeypatch.setattr(agent, "_run", stalled)
    result = asyncio.run(run_review(snapshot()))
    assert result["status"] == "failed"
    assert "timed out" in result["summary"]
    assert result["items"] == result["trace"] == []
    assert len(paths) == 1 and not paths[0].exists()


def test_error_from_tool_is_not_a_valid_proposal():
    message = SimpleNamespace(name="upsert_review_item", response={
        "structuredContent": {"error": "rejected", "item": {"kind": "renewal"}}
    })
    trace, items = [], []
    agent._capture(message, trace, items)
    assert trace == [{"tool": "upsert_review_item", "outcome": "error", "evidence_ids": []}]
    assert items == []
