"""FastAPI application entrypoint for SubGuard AI web and worker services."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Optional

from fastapi import FastAPI
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from app.config import Settings, get_settings
from app.intelligence_adapter import IntelligenceBackend
from app.routes_api import router as api_router
from app.routes_auth import router as auth_router
from app.routes_worker import router as worker_router
from app.security import SecurityManager
from app.storage import LocalStore

STATIC_DIR = Path(__file__).parent / "static"


def create_app(
    settings: Optional[Settings] = None,
    store: Optional[LocalStore] = None,
    intelligence: Optional[IntelligenceBackend] = None,
    service_mode: Optional[str] = None,
) -> FastAPI:
    cfg = settings or get_settings()
    mode = (service_mode or cfg.service_mode or "web").lower()

    app = FastAPI(title="SubGuard AI", version="0.1.0")
    app.state.settings = cfg
    app.state.security = SecurityManager(cfg.session_secret, cfg.token_encryption_key)
    if store is not None:
        app.state.store = store
    elif cfg.google_cloud_project:
        from app.firestore_store import FirestoreStore

        app.state.store = FirestoreStore(cfg.google_cloud_project)
    else:
        app.state.store = LocalStore()
    app.state.intelligence = intelligence
    app.state.service_mode = mode

    @app.get("/health")
    async def health() -> JSONResponse:
        return JSONResponse({"status": "ok", "service_mode": mode})

    if mode == "worker":
        app.include_router(worker_router)
    else:
        app.include_router(auth_router)
        app.include_router(api_router)
        if STATIC_DIR.exists():
            app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

        @app.get("/")
        async def index() -> FileResponse:
            return FileResponse(str(STATIC_DIR / "index.html"))

    return app


app = create_app()
