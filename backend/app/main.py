"""FastAPI entrypoint. Multi-tenant-aware wedding RSVP API.

M3 adds the guest-facing, tenant-scoped invite + RSVP router. Admin (auth-gated)
question CRUD and responses land in M6.
"""
import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.config import get_settings
from app.routers import admin, invite, me, platform
from app.storage import UPLOAD_DIR

settings = get_settings()

app = FastAPI(title=settings.app_name)

# Make the active DB obvious in the server log on boot (local vs production).
print(f"[startup] DB backend: {settings.db_backend} (env={settings.environment})")

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

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health", tags=["meta"])
def health() -> dict[str, str]:
    """Liveness probe. `db` tells you which backend is active (sqlite|postgres)."""
    return {
        "status": "ok",
        "service": settings.app_name,
        "env": settings.environment,
        "db": settings.db_backend,
    }


app.include_router(invite.router)
app.include_router(invite.public_router)
app.include_router(me.router)
app.include_router(admin.router)
app.include_router(platform.router)
