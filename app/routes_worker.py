"""Private worker routes (mounted only when SERVICE_MODE=worker)."""

from __future__ import annotations

import os
from fastapi import APIRouter, Request, Response
from fastapi.responses import JSONResponse

from app.storage import LocalStore

router = APIRouter()


@router.post("/jobs/deliver")
async def deliver_jobs(request: Request) -> Response:
    # Require bearer / OIDC identity in worker mode; tests may pass X-Worker-Test if configured
    auth_header = request.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer ") or len(auth_header.split(" ", 1)[1].strip()) < 8:
        if os.getenv("ALLOW_LOCAL_WORKER_BYPASS", "").lower() != "true":
            return JSONResponse({"detail": "Unauthorized worker call"}, status_code=401)

    from app.routes_api import deliver_due_jobs_with_email

    delivered = deliver_due_jobs_with_email(request.app)
    return JSONResponse({"ok": True, "delivered": delivered})
