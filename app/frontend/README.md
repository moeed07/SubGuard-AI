# SubGuard web frontend

SubGuard's web UI uses React with JavaScript, Vite, and Tailwind CSS. Build it from the repository root:

```powershell
npm.cmd --prefix app/frontend ci
npm.cmd --prefix app/frontend run build
.\.venv\Scripts\python.exe -m uvicorn app.main:app --port 8000
```

Open `http://localhost:8000/` in a fresh browser session. FastAPI serves the Vite build at `/`; the API and OAuth stay on the same origin. Restart FastAPI after the first build if it was already running. The Dockerfile builds and includes the frontend automatically.

For fast stylesheet edits, start `npm.cmd --prefix app/frontend run dev` alongside FastAPI. The Vite server proxies `/api`, `/auth`, and `/demo` to `http://localhost:8000` by default. Use the FastAPI URL for the full sign-in so OAuth redirects return to the configured app origin.

To check consent denial without a Google sign-in, open `/auth/google/callback?error=access_denied`. Then select **Explore fictional example** and verify the totals in DESIGN.md §4. On the dashboard, select **Apply fictional cancellation**, then refresh again to verify the cancellation remains applied. Review proposals and traces require the configured Gemini agent. Reminder delivery requires the configured background loop or worker. Dismissed proposals are hidden in the active browser session because there is no dismissal API.

In the fictional session, open **Agent Review → Find savings** to compare the four plans from the optimizer brief. The server should retain A and C and reduce the modeled monthly cost from PKR 9,000 to PKR 4,500. **Run with Gemini** runs the same fictional scenario via the real MCP tool and shows its trace when available. The optimizer uses a separate catalog; it does not change Gmail billing totals or review proposals.
