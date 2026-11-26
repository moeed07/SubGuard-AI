# SubGuard AI | Shared contract, merge and demo

**Moeed and Ahmed • Read together before coding • Seven-hour build**

Put these three files in the same repository under `docs/`. Each coding assistant gets its owner's file and this file. Start each new assistant session by giving it the branch name, current milestone and last passing test. Keep this file as the single source for names, amounts and handoffs. The commands below use Windows PowerShell. Replace uppercase placeholders with your values.

## 1. Create one starting point | first 15 minutes

1. Moeed creates a GitHub repository named `subguard-ai` with a README and Python .gitignore. Under Settings → Collaborators, invite Ahmed. Ahmed accepts with his own GitHub account. Copy the HTTPS clone URL from the green Code button. [GitHub](https://github.com/new)
2. Moeed clones it, places the three briefs in `docs/`, and commits them on main. Add ignore entries for `.env`, `.venv/`, OAuth credential downloads, token caches and local database files. Commit a blank-value `.env.example`. Both choose Python 3.11. Moeed owns root configuration and release integration.
3. Both clone or update **after** this first push. Each runs the corresponding branch command below, in their own checkout. Share the first commit hash in your team chat. On one laptop use separate clones in different folders.
4. Work against the contract in §2 immediately. Moeed can render a synthetic result while Ahmed can compute the result from synthetic envelopes. Mark development fixtures clearly. The hosted live route must use real Gmail and a real MCP invocation.

```powershell
git clone YOUR_REPO_HTTPS_URL
cd subguard-ai
git switch main
git pull --ff-only origin main
git sw/itch -c feat/moeed-app
```

Ahmed uses `git switch -c feat/ahmed-agent` for the last line. For each checkpoint inspect `git status --short` and `git diff`, stage owned paths, commit with a description and push. On the first push use `git push -u origin HEAD`.

| Path or responsibility                                                                              | Only editor                                                                                                                         |
| --------------------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------- |
| app/, tests/app/, deploy/, README.md, Dockerfile, requirements.txt, .env.example, .gitignore, docs/ | Moeed                                                                                                                               |
| intelligence/, tests/intelligence/, requirements-agent.txt                                          | Ahmed                                                                                                                               |
| Contract change                                                                                     | Ahmed proposes the exact input/output difference and one test. Both acknowledge it. Moeed edits this file and both pull the change. |

Moeed's root requirements include `-r requirements-agent.txt` once Ahmed's file is available. Before the integration branch exists each developer can install their own dependencies separately. Neither agent needs to generate the other agent's service, UI, schema copy or deployment files.

## 2. The boundary to build against

One web service and a private scheduled worker use the same codebase. One Python package, `intelligence`, holds the billing calculations, ADK agent and local stdio MCP server. The browser talks only to the web service. The Python interface below is the team contract; SDK internals stay inside their owner’s directory.

| Function in intelligence/api.py                  | Input supplied by Moeed                                                                                   | Output/side effect supplied by Ahmed                                                                                            |
| ------------------------------------------------ | --------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------- |
| extract_events(messages)                         | List of sanitized Message envelopes for the scan                                                          | List of Event records, each citing its source. Return an empty list for non-billing mail. Preserve uncertainties.               |
| build_portfolio(events, as_of, timezone)         | All persisted events for one account, ISO date, IANA zone                                                 | JSON-compatible Portfolio with totals, subscriptions, timelines and due entries; deterministic, no network.                     |
| async run_review(portfolio, goal)                | Single-account snapshot with opaque IDs; default goal: “Find what needs attention before my next charge.” | ReviewResult with evidence-backed item proposals, summary, tool trace and completion status. Uses Gemini and a real MCP server. |
| Optional optimize_portfolio(plans, capabilities) | Synthetic or verified active plans in one currency and capabilities to preserve                           | Exact minimum-cost subset and conditional difference. Missing coverage stays explicit.                                          |

**Message envelope** has source_id, received_at (UTC timestamp), sender_domain, subject and body_text. Remove personal identifiers, signatures, quoted replies, external tracking URLs and unrelated content before model use. Original Gmail IDs and source links stay in Moeed's account-scoped mapping. Synthetic examples can use readable opaque IDs like m1.

**Event** has event_id, source_id, received_at, subscription_key, kind, currency, amount_minor, cycle, transaction_ref, event_date, effective_date, next_charge_date and date_basis. Business dates use YYYY-MM-DD. Preserve received_at as a UTC timestamp for ordering. Absent fields use JSON null. subscription_key identifies a merchant plus plan/account variant when supported. Event kinds are payment, renewal, trial_conversion, cancellation_confirmed, cancellation_requested, failed, promo or unknown. cycle is monthly, annual or null. date_basis is confirmed, estimated or unknown for next_charge_date. Separate evidence of a charge from evidence about future billing.

**Worked event** for the first receipt:

```json
{"event_id":"m1:0","source_id":"m1","received_at":"2026-11-26T08:00:00Z","subscription_key":"writing-plus","kind":"payment","currency":"PKR","amount_minor":200000,"cycle":"monthly","transaction_ref":"W-101","event_date":"2026-11-26","effective_date":null,"next_charge_date":null,"date_basis":"unknown"}
```

**Portfolio** contains as_of, timezone, totals, subscriptions, due and timelines. totals is keyed by currency; its fields are paid_minor, monthly_equivalent_minor and next_7d_minor. subscriptions entries have subscription_key, status, paid_through, auto_renew and evidence_ids; use null when unknown. due entries have subscription_key, date, amount_minor, currency, kind, date_basis and evidence_ids. timelines maps subscription_key to its validated events. Use integer minor units; the fixture uses 100 minor units per rupee. Divide only at the display boundary. Keep other currencies separate and use their currency exponent. Round a monthly equivalent once per currency total, half-up, after exact rational/decimal calculation.

**ReviewResult** contains status (complete, partial or failed), summary, items and trace. An item has subscription_key, kind, target_date, state (open or resolved), evidence_ids and explanation. Trace records contain tool, outcome and opaque source IDs; exclude raw mail and private reasoning. Stable review-item key = account + subscription_key + kind + target_date. On date change, resolve the old key and open the new one. Moeed maps these proposals to durable writes only after validation. The UI reports “saved” only after the database confirms success.

**How stdio crosses the process boundary.** Ahmed's runner launches one MCP child per review via the same Python interpreter. Supply that child's validated snapshot through a private per-run temporary JSON file, passed at launch by the backend; close and remove the file on success, error or timeout. The MCP tools read only that snapshot. Tool inputs have opaque plan IDs; no user-selected path or account ID. The child returns review-item proposals in its tool results. The runner collects the results of actual calls. Moeed persists validated proposals in the parent. This design gives both students independent tests and keeps Gmail tokens out of Gemini and MCP.

**HTTP routes owned by Moeed:** GET /, GET /health, GET /auth/google/start, GET /auth/google/callback, GET /api/dashboard, POST /api/refresh, POST /api/reminders, POST /api/disconnect, DELETE /api/data and POST /demo/start. The separate private worker serves POST /jobs/deliver. Use authenticated session ownership and CSRF protection on browser mutations. A user action applies to the active account only.

## 3. One fixture and one clock

For repeatable tests set D = 2026-11-26, Asia/Karachi; D+3 = Nov 29 and D+5 = Dec 1. For a live demo send fictional emails with actual dates relative to demo day. The team seeds the dedicated mailbox using ordinary Gmail before presenting. Keep the cancellation for the second scan. Do not seed a computed total.

| Source             | Fictional email content                                                                      | Expected effect                                         |
| ------------------ | -------------------------------------------------------------------------------------------- | ------------------------------------------------------- |
| m1                 | Writing Plus monthly subscription. Paid PKR 2,000 today. Receipt W-101. Auto-renews monthly. | One payment and active monthly plan.                    |
| m2                 | Duplicate confirmation of the same Writing Plus payment, W-101, PKR 2,000.                   | Second piece of evidence for the same payment.          |
| m3                 | Design Pro annual subscription. Paid PKR 12,000. Receipt D-201. Auto-renews annually.        | One annual payment.                                     |
| m4                 | Design Pro annual renewal of PKR 12,000 is scheduled on D+5.                                 | Future charge only.                                     |
| m5                 | Sketch Trial converts to a paid plan on D+3. First charge PKR 700.                           | Open trial review, future charge.                       |
| m6, m7             | Promotional offer for a new plan; separate failed debit.                                     | Neither counts as a successful charge.                  |
| m8, arriving later | Design Pro auto-renewal is OFF. Your access ends D+5. You will not be billed on D+5.         | Remove projected renewal. Keep paid access and history. |

| Expected display                                              | First scan |   After m8 |
| ------------------------------------------------------------- | ---------: | ---------: |
| Payments actually collected                                   | PKR 14,000 | PKR 14,000 |
| Forward monthly equivalent of paid renewing plans             |  PKR 3,000 |  PKR 2,000 |
| Confirmed charges due today through D+7 inclusive             | PKR 12,700 |    PKR 700 |
| Open Sketch Trial review items, including after two refreshes |          1 |          1 |

## 4. Merge twice

**First integration by 01:15.** Push each branch and open draft pull requests on GitHub. Moeed creates the integration branch off the current main. Bring in Ahmed's interface/MCP smoke test and Moeed's callback/host skeleton. Run the integration checks before adding features. Push integration. Keep both feature branches alive. Use regular merge commits so Git recognizes both branches' ancestry on the next integration.

```powershell
git fetch origin
git switch -c integration origin/main
git merge --no-ff origin/feat/ahmed-agent
git merge --no-ff origin/feat/moeed-app
git push -u origin integration
```

**Second integration by 05:00.** Ask both people for their branch's tested commit hash and known gaps. From a clean checkout run:

```powershell
git fetch origin
git switch integration
git pull --ff-only origin integration
git merge --no-ff origin/feat/ahmed-agent
git merge --no-ff origin/feat/moeed-app
py -3.11 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m pip check
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m uvicorn app.main:app --port 8000
```

Start the local app with Moeed’s environment variables configured. The server runs in that terminal. Use another terminal/browser for localhost:8000. Stop with Ctrl+C. If an earlier draft merge was made, omit branch creation. On a merge conflict run `git status`; ask the path owner to reconcile the file with §2. For dependencies retain the root include and Ahmed's package pins. Run tests, stage the resolved paths and use `git merge --continue`. To abandon an in-progress merge from a clean starting state use `git merge --abort`. Avoid force-pushing a shared branch. Push integration, open a PR **base main ← compare integration**, review the combined diff, merge after the gates pass, then deploy the tested main commit. Close superseded draft PRs. [GitHub pull requests](https://docs.github.com/en/pull-requests/collaborating-with-pull-requests/proposing-changes-to-your-work-with-pull-requests/creating-a-pull-request)

## 5. Joint release, recording and submission | 05:00–07:00

| Gate to try together                                                                                                                      | Evidence for the README or video                                                                                                                       |
| ----------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------ |
| Open hosted app in a fresh browser; consent with the listed demo user.                                                                    | No data entry. Live results cite the correct fictional email. Decline once to verify retry.                                                            |
| Add m8, refresh twice, then retry an interrupted scan.                                                                                    | Table §3 matches; payment history survives and partial scans do not invent cancellations.                                                              |
| Compare a simple cost question with the cancellation/renewal conflict. Temporarily inject an MCP failure in a local test.                 | Different actual tool traces; failure is visible and earlier good records survive.                                                                     |
| Click Remind me once for the trial. Use the labeled one-minute test option. Close the page, reopen after the worker runs, retry delivery. | Exactly one timestamped in-app notification. Scheduling a canceled renewal is rejected.                                                                |
| Use two sessions, try the fictional reviewer route, disconnect and delete the live demo user's data.                                      | Sessions are isolated; example is labeled; cross-account lookup fails; secret values and personal mail are absent from logs and repo.                  |
| Open GitHub, deployment and video signed out.                                                                                             | README includes installation, environment variable names, demo access, actual test results and limitations. Record commit hash and Cloud Run revision. |

**Recording script.** 0:00–0:40 show the problem and read-only connection. 0:40–1:30 show receipts and the PKR 3,000 monthly equivalent. 1:30–2:30 show the trial review, real MCP trace and one-minute reminder. 2:30–3:30 introduce the cancellation, refresh, show PKR 700 due and unchanged historical payments. 3:30–4:00 show reminder delivery and how a judge opens the fictional example. Use OBS or a built-in screen recorder and upload an accessible 3–5 minute video. Submit exactly three links through the organizer's portal: repository, deployed app, video. [OBS](https://obsproject.com/) · [YouTube Studio](https://studio.youtube.com/)

**If time slips:** At 01:15 give hosted OAuth and an actual MCP tool call priority over UI polish. At 05:00 freeze extra features. Preserve a live Gmail review, verified billing math, evidence-dependent decisions and the in-app action. Label anything incomplete. A team-member demo inbox can prove OAuth live even when judges prefer to test the isolated fictional example.

**Handoff message to send each other:** “Branch \_\_, commit \_\_, checkpoint \_\_. Run \_\_. Expected \_\_, observed \_\_. Changed contract fields \_\_. Remaining blocker \_\_.” Decisions made in a coding chat belong in the PR when the other student depends on them.
