# SubGuard — DESIGN.md

> **Status:** Direction adopted by Ahmad on 2026-11-27, with the reference
> designs in §9 (MotionSites + 21st.dev) chosen by him the same day.
> Source of the direction: `research_notes/subguard-frontend-direction-20261126-2143/report.md`
> (calm fintech ledger, modelled on Mercury / Rocket Money / Copilot Money, with a
> Perplexity-style agent review rail). Contract source of truth:
> `docs/03_Merge_and_Demo.md` in the `subguard-ai` repo — if this file and the
> contract ever disagree, the contract wins.
> **Owner:** Moeed (`feat/moeed-app`) — app/, deploy/, tests/app/, root config.
> **Never edit:** intelligence/, tests/intelligence/, requirements-agent.txt (Ahmad's).

## 1. The one decision

**A calm fintech ledger dashboard — NOT a flashy landing page, NOT a dark
hacker-style agent console.** The dashboard IS the product. There is no marketing
hero. A judge must understand it in 5 seconds and trust it in 4 minutes.

- Body: Mercury / Rocket Money / Copilot Money — light, calm, table-driven.
- One borrowed organ: an agent review rail on the right, console-styled *inside*
  (mono type, hairline step timeline) — the single memorable element.
- One editorial touch: a single serif-italic verdict sentence at the top
  ("Eleven subscriptions. One trial converts this week.") — the line judges repeat.

Rejected as the main surface (kept only as ingredients above): full dark
Linear-style console (highest wow for tech judges, lowest trust for real users
handing over Gmail access) and full editorial/broadsheet design (most memorable,
weakest for daily use).

## 2. Design tokens (exact — do not improvise)

| Token | Value | Use |
|---|---|---|
| Page background | `#FBFCFD` | Page |
| Card surface | `#FFFFFF` | Cards |
| Hairline / border | `#EDEDF3` (1px) | Card borders, dividers — separation by surface tone, **not** shadows |
| Ink (primary text) | `#171721` | Headings, figures |
| Secondary text | `#6B7280`-ish grey | Labels, definitions |
| Accent (ONE only) | `#5266EB` (Mercury periwinkle/indigo) | Primary buttons/links ONLY: "Connect Gmail", "Remind me" |
| Confirmed green | `#1A7F4B` | Confirmed pill + ✓ + word |
| Estimated amber | `#9A6B00` on pale amber | Estimated pill (dashed border) + "~" + word |
| Unknown grey | grey | Unknown pill + "?" + word |
| Due-soon red | red, text only | "Due in ≤ 3 days" text — the ONLY use of red |
| Card radius | 12px | Cards |
| Small chrome radius | 4px | Pills / small controls |
| Primary-button radius | 9999px (pill) | Buttons |
| Card padding | 32px | Cards |
| Grid | 12-col, 24px gutters | Page |

**Typography**

- UI + figures: **Inter** (free; Arcadia's listed substitute). Display 480–560 weight,
  body 400. Sentence-case headings. No bold display type.
- Mono: **IBM Plex Mono / ui-monospace** — ONLY for the tool-call trace, the
  `gmail.readonly` scope string, and technical labels. Never for body copy.
- Serif italic: **one line only** — the verdict sentence at the top of the
  dashboard (Tiempos substitute: Source Serif 4 / Newsreader, italic).
- Amounts: right-aligned, `font-variant-numeric: tabular-nums`.

**Banned (anti-slop — these are the tells):** purple/blue gradients, sparkle
emoji / ✨, glassmorphism, centred hero with pill badge + three identical cards,
chat box for the agent, avatar/persona name for the agent, typing/"thinking…"
theatre, numeric % confidence in the user UI, any chart wall. One accent colour,
used everywhere the same way.

## 3. Layout

### 3.1 Top bar
Wordmark left · tabs centre (Dashboard · Subscriptions · Agent Review ·
Notifications) · account / Disconnect right. No sidebar — SubGuard has ~4 views;
a sidebar is cargo-culted Linear.

### 3.2 Connect screen (GET /)
- Headline: what it does in one line.
- **Lead with the limit, not the benefit**, directly under the button:
  - Searches only billing emails (receipts, renewals, trials, cancellations)
  - Read-only — cannot send, delete, or change any email
  - Disconnect anytime in Google settings
- Print the literal scope in mono: `gmail.readonly`
- Two-column "Will read / Will never" list (Will never: send, delete, read
  non-billing personal mail for any other purpose, sell data).
- "Explore fictional example" sits **beside** Connect Gmail as a secondary button,
  labelled "fictional" in the button itself. The fictional dashboard carries a
  persistent **"Fictional example data"** banner.
- On denied consent, return to a usable Connect screen. Never a blank white
  loading state — branded loading state, judges assume blank = broken.

### 3.3 Dashboard (GET /api/dashboard renders this)
Order, top to bottom:

1. **Verdict line** — the single serif-italic sentence (e.g. "Eleven
   subscriptions. One trial converts this week.").
2. **KPI band, per currency** — three figures in a row, figure in 40–48px,
   label above in 11px uppercase grey, one-line plain-English definition in
   13px grey below each figure:
   - Paid during the scan window
   - Forward monthly equivalent ("every active subscription normalised to per-month")
   - Confirmed charges due in the next 7 days
   - Currencies are **separate bands, never mixed, never summed across
     currencies**, never a converted total unless labelled as converted.
3. **7-day Confirmed timeline strip** — horizontal day rail (Today, +1 … +7)
   with confirmed charges as solid dots + amount labels, directly under the KPI
   row, fed **only** by the Confirmed figure. Estimated items must NOT appear
   on it — that restraint is itself a trust signal. No calendar grid.
4. **Two columns:** subscription list (left, ~60%) + Agent Review rail (right,
   ~40%, sticky).

### 3.4 Subscription list
Row: initial-tile (merchant) + name + amount (right, tabular) + cadence
(monthly/annual) + next date + Confirmed/Estimated/Unknown pill + `✉ Evidence`
link. Default sort: most-needs-action / next due first. Tap/expand row → detail
with price history + one prominent action.

- **Confirmed:** solid pill + ✓ + the word "Confirmed".
- **Estimated:** dashed-border pill + "~" prefix + muted text + the word
  "Estimated" — never the same weight/colour as Confirmed — plus the reason
  ("Estimated — inferred from monthly cadence; no renewal date in email").
- **Unknown:** show "Date unknown — no date in email" as text, never a blank
  and never a guessed date. A visible Unknown is a trust asset.
- **Evidence link on every row:** labelled with sender + date
  (`✉ From Netflix · 12 Mar`), opening the source email (Perplexity
  publisher-first chips). Every agent claim carries one too.
- Annual renewals: label with their **full due amount and date**.
- Trial conversions are **separate** from already-paid plans.
- Show last successful scan time + a Refresh button. Show partial scans
  distinctly. Empty mailbox, failed scan and successful zero-result scan get
  distinguishable states.

### 3.5 Agent Review rail (the wow moment)
- Label the panel **"Agent review"**, not "AI chat". **No chat box.**
- Each item is a *proposal* with fixed-order actions: **Remind me / Dismiss /
  See evidence** (Copilot fixed-action-position rule). "Remind me" is the only
  primary button style in list/rail.
- Progressive disclosure, three layers — never show raw trace first:
  1. Summary in plain English ("Trial converts in 3 days")
  2. Expandable step timeline in plain language
     ("Searched Gmail for 'trial' → Found email 12 Mar → Extracted date 15 Mar")
  3. Full tool-call trace in mono, collapsed by default (≤ 6 steps per item:
     tool name in mono, human-readable result, timestamp/duration, ✓/✗ as text)
- The trace is the demo's wow moment: judge clicks a review item and watches
  the trace resolve to the actual email proving "trial converts in 3 days".
  The hosted live screen must show a **real MCP call** — never silently fall
  back to a mock adapter (mocks live only in tests).
- Print, in the rail: "SubGuard never cancels or pays anything — it only
  reminds." And a "what the agent did NOT do" line, e.g. "Agent read 14 emails.
  It did not open non-billing emails."
- When a tool fails: retain the last good result and show a retry state.

### 3.6 Reminders & notifications
- "Remind me" authorizes **one** in-app job for a confirmed date. Revalidate
  account, target and current renewal state first. Persist `due_at` in UTC,
  display Asia/Karachi. Stable job/notification ID. Deduplicate per
  account + target + reminder type. Scheduling a cancelled renewal is rejected.
- A separate, labelled **one-minute test** option exists for the demo.
- Notifications view: exactly one timestamped in-app notification per delivered
  reminder (delivered even if the browser was closed).

### 3.7 Data-density rule
A dashboard with 12 believable subscriptions (varied currencies, one Unknown
date, one Estimated) reads as engineered; a gorgeous dashboard with 3 rows reads
as a mockup. Density is the cheapest credibility available. Do not add a 4th KPI
or a chart wall — the 3 figures × currency are already under the 5–7 metric cap.

## 4. The fixture numbers the UI must render (contract §3 — do not change)

Fixture clock: D = 2026-11-26, Asia/Karachi; D+3 = Nov 29; D+5 = Dec 1.
For the **live** demo, fictional emails use actual dates relative to demo day;
the figures below are the contract's fixed-clock expectations.

| Display | First scan | After m8 (cancellation) |
|---|---|---|
| Payments actually collected | PKR 14,000 | PKR 14,000 |
| Forward monthly equivalent of paid renewing plans | PKR 3,000 | PKR 2,000 |
| Confirmed charges due today through D+7 inclusive | PKR 12,700 | PKR 700 |
| Open Sketch Trial review items (incl. after two refreshes) | 1 | 1 |

Fixture story: Writing Plus PKR 2,000/mo (paid, receipt W-101, duplicate m2 =
second evidence, same payment); Design Pro PKR 12,000 annual (paid, receipt
D-201) with renewal PKR 12,000 scheduled D+5; Sketch Trial converts D+3, first
charge PKR 700. m8 (arriving later): Design Pro auto-renewal OFF — remove the
projected renewal, keep paid access and history. The PKR 12,700 → PKR 700
change is the demo's before/after beat (recording 2:30–3:30).

## 5. Routes & boundaries (contract §2 — Moeed owns these)

GET `/`, GET `/health`, GET `/auth/google/start`, GET `/auth/google/callback`,
GET `/api/dashboard`, POST `/api/refresh`, POST `/api/reminders`,
POST `/api/disconnect`, DELETE `/api/data`, POST `/demo/start`.
Private worker: POST `/jobs/deliver` (never mounted on the web service).
Session ownership + CSRF protection on browser mutations. A user action applies
to the active account only. The UI reports "saved" only after the database
confirms success.

Moeed calls Ahmad's package only through `intelligence/api.py`:
`extract_events`, `build_portfolio`, `run_review` (optional
`optimize_portfolio`). Never re-implement billing math in the frontend — all
money figures come from `build_portfolio`, in integer minor units (100 minor
units = PKR 1); divide only at the display boundary.

## 6. Demo-day checklist (Fri 27 Nov 2026, 2–5pm — contract §5)

Recording (3–5 min, OBS or built-in recorder, upload accessible):
0:00–0:40 problem + read-only connection · 0:40–1:30 receipts + PKR 3,000
monthly equivalent · 1:30–2:30 trial review, real MCP trace, one-minute
reminder · 2:30–3:30 cancellation (m8), refresh, PKR 700 due, unchanged
history · 3:30–4:00 reminder delivery + fictional example for judges.

Gates to try together: fresh-browser consent with the listed demo user (decline
once to verify retry) · add m8, refresh twice, retry an interrupted scan ·
compare a cost question with the cancellation/renewal conflict · inject an MCP
failure locally (failure visible, earlier good records survive) · Remind me once
for the trial, one-minute test, close the page, reopen after the worker runs
(exactly one notification) · two sessions, fictional reviewer route, disconnect
+ delete live demo user's data (sessions isolated, no secrets/personal mail in
logs or repo) · open GitHub, deployment and video signed out.

Submission = exactly three links through the organizer's portal: repository,
deployed app, video. README includes installation, env-var names, demo access,
actual test results and limitations. Record commit hash + Cloud Run revision.

**If time slips:** at 01:15 into the build, hosted OAuth + an actual MCP tool
call beat UI polish. At 05:00, freeze extra features. Preserve a live Gmail
review, verified billing math, evidence-dependent decisions and the in-app
action. Label anything incomplete.

## 7. Environment (non-secret names only — secrets go in Secret Manager)

`GOOGLE_CLOUD_PROJECT`, `APP_BASE_URL`, `GOOGLE_OAUTH_CLIENT_ID`,
`GOOGLE_OAUTH_CLIENT_SECRET`, `SESSION_SECRET`, `TOKEN_ENCRYPTION_KEY`,
`SERVICE_MODE`, `GEMINI_MODEL`, `GOOGLE_API_KEY` (if using Ahmad's AI Studio
route). Record them in `.env.example` with blank values only. Never request or
paste secret values in chat. Cloud Run → Logs is for status codes, counts and
run IDs only — no tokens, no raw mail.

## 8. Screenshot → critique → fix loop (from the anti-slop method)

Codex codes blind. After each milestone: screenshot the dashboard at desktop
and phone width, compare against §2–§3 of this file (tokens, pills, rail,
verdict line), list every deviation, fix, re-screenshot. Stop the loop when the
screenshot matches this file — not when it "looks nice". If a ban-list escape
becomes its own cliché (e.g. cream + serif + terracotta everywhere), the fix is
still this file's tokens, not a new style.

## 9. Reference designs — what to copy, what to ignore (added 2026-11-27)

Ahmad chose these from MotionSites and 21st.dev. They are **structure
references only**: layout, spacing, row density, interaction pattern. Their
own colours, fonts and themes NEVER override §2 tokens. Recreate the design
in React with JavaScript (Vite) and Tailwind CSS, using components in
`app/frontend/src/components/`. Do not import reference code.

| Screen / element | Reference | Take | Ignore |
|---|---|---|---|
| Connect screen | Treasury template (21st.dev, free) — https://21st.dev/@kedhareswer/templates/treasury-management-fintech-landing-page | Hero holding a live product panel instead of a screenshot; trust/limits section under the main action | Its cream/teal palette and treasury copy — §3.2 rules stand |
| KPI band | Charts & KPI Cards — https://21st.dev/@uvain/components/revenue-charts-kpi | Card structure, label/figure/definition stack, tabular figures | Its charts — no chart wall (§2 ban) |
| Subscription list | Editable Data Table — https://21st.dev/@starc007/components/table-editable · Invoice History Table — https://21st.dev/@ziegfiroyt/components/settings64 | Row density, status-badge styling, calm table feel | Their columns — ours are §3.4; no inline editing |
| Agent tool trace | Astryx Chat Tool Calls — https://21st.dev/@Astryxdesign/components/astryx-chat-tool-calls/chat-tool-calls-expandable | Expandable call rows: tool name, arguments, duration, status; collapsed by default | Its dev-tool example content — ours are Gmail/MCP calls per §3.5 |
| Agent rail structure | Iris Assistant (MotionSites) — https://motionsites.ai/?prompt=iris-assistant | Panel structure: summary first, activity list below | Its dark theme and chat box — §3.5 bans both |
| Landing tone (backup) | FinFlow (MotionSites) — https://motionsites.ai/?prompt=finflow · Wealthcore — https://motionsites.ai/?prompt=wealthcore | Calm headline + trust-strip placement if the Connect screen needs more air | Their dark/landing-page styling |

21st.dev usage: the "Copy prompt" on a component page is a design
specification, not code to paste into the repo. Free plan = 2 copies/day —
spend them on the KPI cards and the tool-call trace first.
