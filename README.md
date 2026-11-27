# SubGuard AI

**SubGuard AI** helps students and users see what subscriptions they are paying for—before the next charge hits—using a read-only Gmail connection, deterministic billing math, and an evidence-backed AI review agent.

## Architecture
- `app/` — FastAPI web service (`SERVICE_MODE=web`) and private reminder delivery worker (`SERVICE_MODE=worker`), Gmail read-only OAuth, sanitization, and account-scoped persistence (SQLite locally, Google Cloud Firestore in production).
- `intelligence/` — Billing event extraction, deterministic portfolio calculations, and Gemini + stdio MCP review agent (developed on `feat/ahmed-agent`).
- `deploy/` — Google Cloud Run, Secret Manager, and Cloud Scheduler deployment instructions.
- `tests/app/` — Automated tests for web/worker routes, OAuth state & consent handling, Gmail sanitization, scan versioning, §3 fixture math integration, reminders, and session isolation.

## Local Setup (Windows PowerShell)

1. Create and activate a virtual environment:
   ```powershell
   python -m venv .venv
   .\.venv\Scripts\python.exe -m pip install -r requirements.txt
   ```
2. Copy `.env.example` to `.env` and fill in your values (never commit `.env`):
   ```powershell
   Copy-Item .env.example .env
   ```
3. Run the tests:
   ```powershell
   .\.venv\Scripts\python.exe -m pytest -q
   ```
4. Start the local server:
   ```powershell
   .\.venv\Scripts\python.exe -m uvicorn app.main:app --port 8000
   ```
   Open `http://localhost:8000` in your browser. Click **Explore fictional example** to test without Gmail OAuth, or **Connect Gmail** once OAuth is configured.

## Environment Variables
| Variable | Purpose |
|---|---|
| `GOOGLE_CLOUD_PROJECT` | GCP project ID (enables Firestore when set; leave blank for local SQLite) |
| `APP_BASE_URL` | Public base URL (`http://localhost:8000` locally, or Cloud Run HTTPS URL) |
| `GOOGLE_OAUTH_CLIENT_ID` | Google Web OAuth Client ID |
| `GOOGLE_OAUTH_CLIENT_SECRET` | Google Web OAuth Client Secret |
| `SESSION_SECRET` | Secret key for signing `HttpOnly` session cookies and CSRF tokens |
| `TOKEN_ENCRYPTION_KEY` | Fernet key (or passphrase) for encrypting persisted OAuth tokens |
| `SERVICE_MODE` | `web` (public UI/API) or `worker` (private `/jobs/deliver` endpoint) |
| `GEMINI_MODEL` | Gemini model name (e.g., `gemini-3.5-flash-lite`) |
| `GOOGLE_API_KEY` | Gemini API key (used by `intelligence` if using AI Studio) |
| `SMTP_EMAIL` | Optional sender Gmail address for automated email reminders |
| `SMTP_APP_PASSWORD` | Optional Gmail App Password for `SMTP_EMAIL` |

## Demo Access & Limitations
- **Reviewer Demo (No Login Required):** Click **Explore fictional example** on the homepage to run the shared §3 fixture through the real billing math and Gemini + stdio MCP review agent.
- **Live Gmail Testing:** Uses Google OAuth in **Testing** mode with read-only scope (`https://www.googleapis.com/auth/gmail.readonly`). Only email addresses listed under Google Auth Platform → Test users can connect live Gmail.
- **Scan & Delivery Limits:** Each scan/refresh fetches up to 100 unseen billing emails across the last 13 months and skips already-saved messages. Automated 5-day and 1-day email reminders use SMTP when `SMTP_EMAIL` and `SMTP_APP_PASSWORD` are configured; in-app notifications always persist in SQLite/Firestore.

## Verified Test Results
- `.\.venv\Scripts\python.exe -m pip check` → `No broken requirements found.`
- `.\.venv\Scripts\python.exe -m pytest tests/app tests/intelligence -q` → `69 passed` (`19.24s`)
- Live MCP optimizer check (`intelligence.optimizer_demo --live`) → `status: complete`, `optimize_subscription_features: ok`, keeps plans `A` and `C` (`PKR 9,000` → `PKR 4,500`).

## Deployment
See [deploy/README.md](deploy/README.md) for Cloud Run (`subguard-web` and `subguard-worker`), Secret Manager, Firestore, and Cloud Scheduler OIDC setup.
