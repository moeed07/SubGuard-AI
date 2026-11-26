"""Use the actual MCP stdio boundary with only a fictional plan catalog."""
import asyncio

from mcp import ClientSession
from mcp.client.stdio import stdio_client

from intelligence.agent import server_parameters, snapshot_file
from intelligence.api import build_portfolio
from intelligence.fictional import AS_OF, TIMEZONE
from intelligence.optimizer_demo import demo_plans


def test_optimizer_reads_the_catalog_from_the_stdio_snapshot():
    async def check():
        snapshot = dict(build_portfolio([], AS_OF, TIMEZONE), optimizer_plans=demo_plans())
        with snapshot_file(snapshot) as path:
            async with asyncio.timeout(20):
                async with stdio_client(server_parameters(path)) as (reader, writer):
                    async with ClientSession(reader, writer) as session:
                        await session.initialize()
                        tools = await session.list_tools()
                        assert "optimize_subscription_features" in {tool.name for tool in tools.tools}

                        result = await session.call_tool("optimize_subscription_features")
                        assert not result.isError
                        pkr = result.structuredContent["currencies"]["PKR"]
                        assert pkr["retained_plan_ids"] == ["A", "C"]
                        assert pkr["monthly_reduction"] == "PKR 4,500.00"

                        result = await session.call_tool("optimize_subscription_features", {"capabilities": ["writing"]})
                        scoped = result.structuredContent["currencies"]["PKR"]
                        assert scoped["retained_plan_ids"] == ["B"]
                        assert scoped["minimum_monthly"] == "PKR 2,000.00"

    asyncio.run(check())
