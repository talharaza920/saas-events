"""FastAPI entrypoint. Multi-tenant-aware wedding RSVP API.

M3 adds the guest-facing, tenant-scoped invite + RSVP router. Admin (auth-gated)
question CRUD and responses land in M6.
"""
import logging
import os

from fastapi import Depends, FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import get_db
from app.obs import init_sentry, setup_logging
from app.routers import admin, internal, invite, me, platform
from app.storage import UPLOAD_DIR

settings = get_settings()
setup_logging(settings)
init_sentry(settings)
logger = logging.getLogger("app.main")

app = FastAPI(title=settings.app_name)

# Make the active DB obvious in the server log on boot (local vs production).
logger.info("startup: DB backend=%s env=%s", settings.db_backend, settings.environment)

# Serve locally-uploaded images (dev storage backend) — DEV ONLY. On serverless
# (Vercel) the filesystem is read-only, so creating/mounting this dir crashes the
# app at import. Skip it in production AND on Vercel (which always sets `VERCEL`),
# and never let a read-only filesystem take down boot — production serves uploads
# from Supabase Storage instead. The belt-and-braces guards are deliberate: a
# misconfigured ENVIRONMENT var must not be able to crash the whole service.
if not settings.is_production and not os.environ.get("VERCEL"):
    try:
        UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
        app.mount("/media", StaticFiles(directory=str(UPLOAD_DIR)), name="media")
    except OSError:
        pass  # read-only filesystem (serverless) — local media mount not available

# Backstop for check-then-insert races (REVIEW_BACKLOG P2-11): hot paths catch
# IntegrityError at their commit with a specific message, but SQLAlchemy can also
# raise it at an autoflush mid-handler — surface those as a retryable 409, not a
# 500. The session is discarded by get_db's close() afterwards.
@app.exception_handler(IntegrityError)
def _integrity_conflict(request: Request, exc: IntegrityError) -> JSONResponse:
    logger.warning("integrity conflict on %s %s", request.method, request.url.path)
    return JSONResponse(
        status_code=409, content={"detail": "That change conflicted — please try again"}
    )


app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health", tags=["meta"])
def health(db: Session = Depends(get_db)) -> dict:
    """Liveness + DB probe. `db` names the active backend (sqlite|postgres);
    `db_ok` is a real SELECT 1 against it. Always HTTP 200 (serverless: a 5xx
    here can recycle the instance) — monitors alert on `status: degraded`."""
    db_ok = True
    try:
        db.execute(text("SELECT 1"))
    except Exception:
        logging.getLogger("app.health").exception("health: DB ping failed")
        db_ok = False
    return {
        "status": "ok" if db_ok else "degraded",
        "service": settings.app_name,
        "env": settings.environment,
        "db": settings.db_backend,
        "db_ok": db_ok,
    }


app.include_router(invite.router)
app.include_router(invite.public_router)
app.include_router(me.router)
app.include_router(admin.router)
app.include_router(platform.router)
app.include_router(internal.router)
