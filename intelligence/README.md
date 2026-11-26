# Ahmed's agent

From the repository root, create a Python 3.11 virtual environment and install the agent's requirements.

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-agent.txt
.\.venv\Scripts\python.exe -m pip check
.\.venv\Scripts\python.exe -m pytest tests/intelligence -q
```

The fixture suite never calls Google. It covers arithmetic and extraction with the shared fictional mail, runs a real MCP child through stdio, and runs that child through ADK using a scripted model.

For the live smoke test, privately set `GOOGLE_API_KEY` for the approved Gemini project. Set `GEMINI_MODEL` to the team's chosen tool-capable model, or use the default `gemini-flash-latest`. Each command sends only fictional evidence. It prints the model, elapsed time, result and tool trace, and exits unsuccessfully if the expected behavior was not observed.

```powershell
.\.venv\Scripts\python.exe -m intelligence.smoke --goal conflict
.\.venv\Scripts\python.exe -m intelligence.smoke --goal cost
.\.venv\Scripts\python.exe -m intelligence.smoke --goal automatic
```

Moeed can import `extract_events(messages)`, `build_portfolio(events, as_of, timezone)`, and `await run_review(portfolio, goal=None)` from `intelligence.api`. Include `-r requirements-agent.txt` in the app's requirements. The fixture clock is 2026-11-26 in Asia/Karachi.

The application saves validated open proposals by the shared stable item key. Reconcile old renewal items against confirmed cancellation in the app, since the review receives no existing item history. An optional optimizer is outside this implementation. The deterministic extractor targets explicit English billing notices, ISO dates, and currency codes. Keep unsupported or incomplete evidence out of confirmed figures. Before using new real sender templates, check their extracted evidence against the original mail.
