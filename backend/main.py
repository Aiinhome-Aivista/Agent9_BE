"""
ARIES — FastAPI Application Entry Point
"""

import logging
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from .routers.login_router import login_router

from .config import get_settings
from .database import create_tables
from .arango_client import init_arango
from .chroma_client import init_chroma
from .routers.all_routers import (
    dashboard_router,
    connector_router,
    policy_router,
    prospect_router,
    campaign_router,
    log_router,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)s — %(message)s",
    datefmt="%H:%M:%S",
)
logger   = logging.getLogger("aries.main")
settings = get_settings()
print("MISTRAL KEY:", settings.MISTRAL_API_KEY)

@asynccontextmanager
async def lifespan(app: FastAPI):
    # ── Startup ────────────────────────────────────────────
    logger.info("ARIES starting up…")
    os.makedirs(settings.UPLOAD_DIR, exist_ok=True)

    await create_tables()
    logger.info("MySQL tables ready.")

    try:
        init_arango()
        logger.info("ArangoDB ready.")
    except Exception as exc:
        logger.warning("ArangoDB unavailable (continuing): %s", exc)

    try:
        init_chroma()
        logger.info("ChromaDB ready.")
    except Exception as exc:
        logger.warning("ChromaDB unavailable (continuing): %s", exc)

    logger.info("ARIES %s online. All agents active.", settings.APP_VERSION)
    yield

    # ── Shutdown ───────────────────────────────────────────
    logger.info("ARIES shutting down.")


def create_app() -> FastAPI:
    app = FastAPI(
        title       = settings.APP_TITLE,
        version     = settings.APP_VERSION,
        description = "Agentic Revenue Intelligence Engine for Sales — Backend API",
        lifespan    = lifespan,
        docs_url    = "/api/docs",
        redoc_url   = "/api/redoc",
        openapi_url = "/api/openapi.json",
    )

    # ── CORS ──────────────────────────────────────────────
    app.add_middleware(
        CORSMiddleware,
        allow_origins     = settings.cors_origins_list,
        allow_credentials = True,
        allow_methods     = ["*"],
        allow_headers     = ["*"],
    )

    # ── Routers ───────────────────────────────────────────
    for router in [
        dashboard_router,
        connector_router,
        policy_router,
        prospect_router,
        campaign_router,
        log_router,
        login_router,
    ]:
        app.include_router(router)

    # ── Health ────────────────────────────────────────────
    @app.get("/health", tags=["Health"])
    async def health():
        return {"status": "ok", "version": settings.APP_VERSION, "service": "ARIES"}

    return app


app = create_app()


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=3004, reload=True, log_level="info")
