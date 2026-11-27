# Ahmed's agent

From the repository root, create a Python 3.11 virtual environment and install the agent's requirements.

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-agent.txt
.\.venv\Scripts\python.exe -m pip check
.\.venv\Scripts\python.exe -m pytest tests/intelligence -q
```

The fixture suite never calls Google. It covers arithmetic and extraction with the shared fictional mail, runs a real MCP child through stdio, and runs that child through ADK using a scripted model.

For the live smoke test, privately set `GOOGLE_API_KEY` for the approved Gemini project. The default `gemini-3.5-flash-lite` passed the live conflict test. Set `GEMINI_MODEL` to override it with another supported model. Each command sends only fictional evidence. It prints the model, elapsed time, result and tool trace, and exits unsuccessfully if the expected behavior was not observed.

```powershell
.\.venv\Scripts\python.exe -m intelligence.smoke --goal conflict
.\.venv\Scripts\python.exe -m intelligence.smoke --goal cost
.\.venv\Scripts\python.exe -m intelligence.smoke --goal automatic
```

Moeed can import `extract_events(messages)`, `build_portfolio(events, as_of, timezone)`, and `await run_review(portfolio, goal=None)` from `intelligence.api`. Include `-r requirements-agent.txt` in the app's requirements. The fixture clock is 2026-11-26 in Asia/Karachi.

The application saves validated open proposals by the shared stable item key. Reconcile old renewal items against confirmed cancellation in the app, since the review receives no existing item history. An optional optimizer is outside this implementation.

The extractor skips marketing-only messages and accepts ISO dates, English month names, and unambiguous slash dates. An undated payment uses its received date. For a recurring receipt without a dated renewal notice, the portfolio estimates one cycle ahead using calendar months or years. Estimated dates stay out of the confirmed forecast and cannot be used for review proposals.

To enable Gemini-assisted extraction for the app, set `SUBGUARD_GEMINI_EXTRACTION=true` along with `GOOGLE_API_KEY` and `GEMINI_MODEL`. For a Python caller, use `extract_events(messages, gemini_fallback=True)` to opt in for one scan. The fallback sends a bounded batch of short billing excerpts from already detected, single-event notices with a missing cycle or amount. It fills only fields backed by evidence and leaves the deterministic result available when Gemini is unavailable. A one-off charge without a recurring-period clue still has an unknown cycle.

Extraction keeps its synchronous interface. When the fallback is enabled, async app handlers should run it in a worker thread, for example with `await asyncio.to_thread(extract_events, messages)`. The Gemini request uses a 10-second HTTP timeout and no retries.

### Subscription confirmation and billing prompts

- Clear shopping orders and editorial mail emit no events. A receipt without subscription evidence can emit an event with `subscription_basis: "uncertain"`. Persist that optional field alongside the event in both stores (Firestore already copies the event dictionary; SQLite needs to round-trip this field). Events without the field retain their legacy meaning. An uncertain duplicate can still corroborate an identified payment if plan, reference, currency and amount match.
- `portfolio.needs_confirmation` contains `{source_id, subscription_key, events}` for unclear receipts. Use `source_id` to save the answer for an individual receipt. These entries do not contribute to subscription totals, forecasts, or reminders. For a user-confirmed receipt, persist the classification, associate the receipt with the confirmed plan key, and rebuild with `subscription_basis: "user_confirmed"`. For a confirmed one-time purchase, keep it out of the billing input on later scans.
- `portfolio.billing_prompts` is keyed by confirmed subscription key. `field: "cycle"` requests the billing period and `can_estimate_from_payment` indicates whether a cycle selection could produce a dated estimate. Save a cycle answer even when no dated estimate is possible. `field: "next_charge_date"` means the cycle is already known and the date needs evidence. Confirmed dates can coexist with a cycle prompt when cadence is missing. Cancelled, suspended and pending-cancellation plans receive no billing prompt. Treat `status: "suspended"` as having no forecast until new billing evidence reactivates it. Render `status: "payment_failed"` independently from the cycle prompt.
- After updating the app, re-extract each account's old evidence and replace derived events by `source_id`, including zero-event replacements, before rebuilding the portfolio. The incremental refresh currently upserts events and cannot remove old false positives on its own. Preserve saved choices and migrate a renamed key only when the original evidence identifies the same plan. Reconcile queued reminders with the rebuilt forecast. Existing events lack the new classification field, so this applies to both SQLite and Firestore.

### Public plan lookup

The optional **Look up billing period** action uses `await lookup_public_plan(product=..., plan=..., storefront=..., market=...)` from `intelligence.api`. Pass only the public product and plan names, the storefront (`google-play`, `app-store`, or `provider`), and a two-letter market. Set `SUBGUARD_PUBLIC_PLAN_LOOKUP=true` only after the team approves a billing-enabled Gemini project. This feature shares `GEMINI_MODEL` and the private API key with the rest of the agent.

Call this from an explicit user action. Display its original `content` with annotations alongside the associated `search_suggestions` in the requesting user's view, following [Google's Search grounding terms](https://aistudio.google.com/docs/terms#grounding-with-google-search). Keep the lookup response out of storage and the billing calculation. If the user selects monthly or annual, call `estimate_renewal_from_selection(portfolio, subscription_key, cycle)` to calculate an estimated date from the receipt already on file. The helper returns `None` when there is a known due date, a cancellation, or insufficient receipt evidence. It does not change stored totals or create a reminder.
