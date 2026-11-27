# SubGuard — AGENTS.md (for Codex / Antigravity, Moeed's side)

> Copy this file and `subguard-DESIGN.md` into the `subguard-ai` repo root
> (and the three briefs under `docs/`). Codex reads AGENTS.md; it does NOT read
> DESIGN.md on its own — so every prompt below points Codex at DESIGN.md
> explicitly. If this file and `docs/03_Merge_and_Demo.md` disagree, the
> contract in `03_Merge_and_Demo.md` wins.

## Who you are in this repo

You are Moeed's coding assistant on branch `feat/moeed-app`. You own ONLY:
`app/`, `deploy/`, `tests/app/`, and root configuration (`README.md`,
`Dockerfile`, `requirements.txt`, `.env.example`, `.gitignore`, `docs/`).
Ahmad owns `intelligence/`, `tests/intelligence/`, `requirements-agent.txt`
on branch `feat/ahmed-agent`.

**Hard rules — never break these, even if asked in a follow-up prompt:**
- Never edit, generate, or "helpfully" rewrite Ahmad's files (`intelligence/`,
  `tests/intelligence/`, `requirements-agent.txt`). Never generate the other
  student's service, UI, schema copy, or deployment files.
- Never request secret values in chat. Secrets live in Secret Manager / a local
  ignored `.env`; `.env.example` holds blank values and variable names only.
- Never print a secret, a token, or raw mail. Logs carry status codes, counts
  and run IDs only.
- The hosted live route uses real Gmail and a real MCP invocation. A mock
  adapter may power tests only — the live screen must never silently fall back
  to it.
- Work one milestone at a time (M1 → M4 in `docs/01_Moeed_App_Gmail_Deployment.md`).
  Stop at each milestone checkpoint, summarize changes, give the exact local
  command, the manual Google Console clicks that require Moeed's account,
  expected output and observed test results, and the next acceptance check.
  Leave publishing and merging to the team.
- Contract changes: Ahmad proposes the exact input/output difference and one
  test; both acknowledge; Moeed edits `docs/03_Merge_and_Demo.md`.

## Design authority

Read `subguard-DESIGN.md` before writing any UI code, and re-read it after
every milestone. It is the single source for: the calm-fintech-ledger direction,
exact tokens (page `#FBFCFD`, hairline `#EDEDF3`, ink `#171721`, accent
`#5266EB` for primary actions only, Inter + IBM Plex Mono + one serif-italic
verdict line), layout order (verdict → per-currency KPI band → 7-day Confirmed
strip → subscription list + agent rail), Confirmed/Estimated/Unknown pill rules,
evidence-chip rules, and the banned list (no gradients, no ✨, no chat box, no
agent persona, no numeric % confidence, no chart wall).

If a generated screen deviates from DESIGN.md, the screen is wrong — fix the
screen, do not "improve" DESIGN.md. After each UI milestone, run the
screenshot → critique → fix loop in DESIGN.md §8 (desktop + phone width).

**Reference designs (DESIGN.md §9):** Ahmad picked reference components from
21st.dev and MotionSites. They are design specifications for structure,
spacing and interaction only. When a component prompt is pasted to you,
recreate the design in this repo's React and Tailwind stack without copying
the reference's code. Where a reference's colours, fonts or theme differ
from DESIGN.md §2, DESIGN.md wins
silently — do not ask, do not copy the reference styling.

## Stack & interface

- Python 3.11 and FastAPI. The frontend uses React with JavaScript (Vite) and
  Tailwind CSS, with components in `app/frontend/src/components/`. No TypeScript.
  `GET /health` must start before OAuth or Gemini is configured.
- Dockerfile listens on the Cloud Run `PORT`. Deploy early, skeleton first:
  `gcloud run deploy subguard-web --source . --region REGION --allow-unauthenticated`
  (Cloud Shell, after `gcloud config set project PROJECT_ID`).
- Gmail scope, exactly: `https://www.googleapis.com/auth/gmail.readonly`.
  OAuth redirect URIs: `http://localhost:8000/auth/google/callback` and
  `https://YOUR_DEPLOYED_HOST/auth/google/callback` (localhost ≠ 127.0.0.1).
- Routes you own: GET `/`, `/health`, `/auth/google/start`,
  `/auth/google/callback`, `/api/dashboard`; POST `/api/refresh`,
  `/api/reminders`, `/api/disconnect`, `/demo/start`; DELETE `/api/data`.
  Private worker: POST `/jobs/deliver` (worker-only, never on the web service).
- Call Ahmad's package ONLY through `intelligence/api.py` (`extract_events`,
  `build_portfolio`, `run_review`, optional `optimize_portfolio`). Never
  re-implement billing math in the app — figures come from `build_portfolio`
  in integer minor units; divide only at the display boundary.
- Money fixture to satisfy (contract §3, D = 2026-11-26 Asia/Karachi):
  first scan PKR 14,000 collected / PKR 3,000 monthly equivalent /
  PKR 12,700 confirmed due in 7 days / 1 open Sketch Trial item; after the
  m8 cancellation: PKR 14,000 / PKR 2,000 / PKR 700 / 1 item.

## Paste into your coding assistant (Moeed)

> Read docs/01_Moeed_App_Gmail_Deployment.md and docs/03_Merge_and_Demo.md.
> I am Moeed on feat/moeed-app. Inspect the repository, report the current
> branch, then implement only my next unfinished milestone. My folders are
> app/, deploy/, tests/app/ and the root files listed in the shared guide.
> Before writing any UI, read subguard-DESIGN.md and follow it exactly —
> calm fintech ledger, tokens in §2, layout in §3, pill and evidence rules in
> §3.4–§3.5. Do not invent a different style. Use Ahmed's exact Python
> interface; keep any test double in my tests. For each milestone give me the
> exact local command, the manual Google Console clicks that require my
> account, expected output and observed test results. Never request secret
> values in chat. Stop at the milestone checkpoint, summarize changes and give
> me the next acceptance check. Leave publishing and merging to the team.

## Paste into your coding assistant (first UI pass, after M1–M2)

> Read subguard-DESIGN.md §2–§3 and implement the dashboard shell only:
> top bar, verdict line, per-currency KPI band with the three figures and
> their one-line definitions, 7-day Confirmed timeline strip, subscription
> list (left ~60%) with Confirmed/Estimated/Unknown pills and ✉ Evidence
> links, and the Agent Review rail (right ~40%) with Remind me / Dismiss /
> See evidence in that fixed order and the tool trace collapsed by default.
> Render it first with the contract fixture (DESIGN.md §4) so the figures can
> be checked exactly: 14,000 / 3,000 / 12,700, then 14,000 / 2,000 / 700
> after m8. No chat box, no gradients, no sparkles, no chart. Screenshot it
> at desktop and phone width and list every deviation from DESIGN.md before
> calling the milestone done.

## Milestone order (from the brief — do not reorder)

- **M1 (00:00–01:15)** Foundation + OAuth: skeleton, `/health`, early Cloud Run
  deploy, Gmail API + Firestore + Secret Manager + Scheduler enabled, OAuth
  client with the exact scope and both redirect URIs, server-side auth-code
  flow, first scan on callback. Gate: hosted site connects the team mailbox,
  finds one known receipt, refresh survives.
- **M2 (01:15–02:15)** Gmail → billing events: 13-month search, decode +
  redact, `extract_events`, upsert by account + event ID, scan versions.
  Gate: duplicate email = two evidence links, one payment; empty / failed /
  zero-result scans distinguishable.
- **M3 (02:15–04:15)** Dashboard + agent integration: three figures per
  currency, list + pills + evidence, `run_review` on connect/refresh, Remind
  me + one-minute test, private worker + Cloud Scheduler OIDC job.
  Gate: fixture totals match, trace shows a real MCP call, reminder delivered
  once while the tab was closed.
- **M4 (04:15–07:00)** Reviewer access, integration, handover: fictional
  example route, Disconnect + Delete review data, `.env.example`, two merges,
  signed-out release test, README + video + three-link submission.
  Gate: §5 of the contract, all rows green.

## Demo-day note (Fri 27 Nov 2026, 2–5pm)

If time slips: at 01:15 into the build, hosted OAuth + an actual MCP tool call
beat UI polish. At 05:00, freeze extra features. Preserve a live Gmail review,
verified billing math, evidence-dependent decisions and the in-app action.
Label anything incomplete. Submission = exactly three links: repository,
deployed app, 3–5 minute video.
