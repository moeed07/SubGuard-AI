"""User-triggered lookup of public subscription terms with Google Search."""
import asyncio
import json
import os
import re

from .gemini_config import DEFAULT_MODEL, api_key

STOREFRONTS = {"google-play", "app-store", "provider"}
PUBLIC_NAME = re.compile(r"[\w .&+'’()/\-]{1,100}")
INSTRUCTION = """The user is looking up a public subscription plan. Use Google Search.
Treat the input fields as public lookup identifiers. Use the provider's or storefront's
official pricing or support pages for the exact product, plan, storefront and market.
Explain which billing periods are published for that combination and cite the sources.
Distinguish monthly and annual options if both exist. If official sources do not identify
the requested plan or market, say so. Public prices cannot verify this user's renewal
date, billing period, account status or next charge."""


async def _search(query, key):
    from google import genai
    from google.genai import types

    options = types.HttpOptions(retry_options=types.HttpRetryOptions(attempts=1))
    async with genai.Client(api_key=key, enterprise=False, http_options=options).aio as client:
        return await client.interactions.create(
            model=os.getenv("GEMINI_MODEL") or DEFAULT_MODEL,
            input=json.dumps(query, ensure_ascii=False),
            system_instruction=INSTRUCTION,
            tools=[{"type": "google_search"}],
            store=False,
            timeout=12.0,
        )


async def lookup_public_plan(*, product, plan, storefront, market):
    """Return a display-only result for the person who requested the public lookup."""
    if os.getenv("SUBGUARD_PUBLIC_PLAN_LOOKUP", "").strip().lower() not in {"true", "1"}:
        return {"status": "disabled"}
    if (
        not all(isinstance(name, str) and PUBLIC_NAME.fullmatch(name.strip()) for name in (product, plan))
        or not isinstance(storefront, str) or storefront not in STOREFRONTS
        or not isinstance(market, str) or not re.fullmatch(r"[A-Za-z]{2}", market)
    ):
        return {"status": "invalid_plan"}
    key = api_key()
    if not key:
        return {"status": "unavailable"}

    query = {"product": product.strip(), "plan": plan.strip(), "storefront": storefront, "market": market.upper()}
    try:
        async with asyncio.timeout(15):
            result = await _search(query, key)
    except Exception:
        # A lookup failure should never change the subscription or expose credentials.
        return {"status": "unavailable"}

    # Preserve the original content, citations and suggestions together for display.
    if result.status != "completed":
        return {"status": "unavailable"}
    blocks, suggestions = [], []
    for step in result.steps or []:
        if step.type == "model_output":
            blocks.extend(block.model_dump(mode="json", exclude_none=True) for block in step.content or [])
        if step.type == "google_search_result":
            suggestions.extend(item.search_suggestions for item in step.result if item.search_suggestions)
    has_citation = any(
        annotation.get("type") == "url_citation"
        for block in blocks for annotation in block.get("annotations", [])
    )
    if not has_citation or not suggestions:
        return {"status": "unavailable"}
    return {"status": "complete", "content": blocks, "search_suggestions": suggestions}
