"""Application settings, loaded from environment / .env (never hardcode secrets).

Local vs production is a single switch — `DATABASE_URL`:
  • Production: the Supabase pooler URL (in `.env`).
  • Local dev:  `sqlite:///./dev.db` (in `.env.local`).

`.env.local` is gitignored and OVERRIDES `.env`, so the recommended workflow is:
create `backend/.env.local` (from `.env.local.example`) to run against local
SQLite, and delete it to run against production — without ever editing the
secret-bearing `.env`. A real `DATABASE_URL` environment variable still beats
both files (handy for one-off runs).
"""
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # Later files win: `.env.local` overrides `.env`. Missing files are ignored.
    model_config = SettingsConfigDict(
        env_file=(".env", ".env.local"), env_file_encoding="utf-8", extra="ignore"
    )

    # Core
    app_name: str = "saas-events — Wedding RSVP API"
    environment: str = "development"

    # Database. Default is local SQLite so a fresh clone runs with zero config;
    # production sets the Supabase `postgresql+psycopg://...` URL in `.env`.
    database_url: str = "sqlite:///./dev.db"

    # Comma-separated origins allowed to call the API (the Next.js frontend).
    cors_origins: str = "http://localhost:3000"

    # Supabase auth (admin/owner sign-in). We validate the admin's access token
    # by introspection — calling Supabase's `/auth/v1/user` — so NO JWT secret is
    # needed; both values below are public (the publishable/anon key is the
    # `apikey` header). Works whether the project signs tokens symmetrically or
    # with the newer asymmetric keys.
    supabase_url: str = ""
    supabase_publishable_key: str = ""

    # Admin allowlist — only these emails may use the owner dashboard. The email
    # returned by Supabase for the token must be in this list (comma-separated).
    # In the future two-tier model (PLAN.md) this becomes the PLATFORM-admin list
    # (per-wedding access moves to a `wedding_members` table) — keep it small.
    admin_emails: str = ""

    # --- Transactional email (app/emailer.py) ----------------------------------
    # When BOTH are set, emails go out via Resend's HTTP API; otherwise they land
    # only in the dev outbox + server log. `email_from` must be a sender Resend
    # has verified, e.g. "Invites <invites@yourdomain.com>".
    resend_api_key: str = ""
    email_from: str = ""

    # --- Rate limiting (app/ratelimit.py) --------------------------------------
    # Per-instance fixed-window limits on the UNAUTHENTICATED guest API. Default
    # (None) = enabled only in production; set RATE_LIMIT_ENABLED=true/false to
    # force either way (tests enable it explicitly). Per-IP, per minute.
    rate_limit_enabled: bool | None = None
    rate_limit_guest_reads_per_minute: int = 120
    rate_limit_guest_writes_per_minute: int = 30

    # --- Observability (app/obs.py) ---------------------------------------------
    # Error tracking is on only when a Sentry DSN is provided; LOG_LEVEL tunes
    # stdlib logging (INFO default).
    sentry_dsn: str = ""
    log_level: str = "INFO"

    # --- Internal cron endpoints (app/routers/internal.py) ----------------------
    # Shared secret for scheduler-driven routes (Vercel cron sends
    # `Authorization: Bearer $CRON_SECRET`). Empty = the routes 404.
    cron_secret: str = ""

    # --- AI creation wizard (app/ai/, AI_WIZARD_PLAN Phase 8) -------------------
    # The text model is pluggable by config; media (Gemini) is a hard-coded seam.
    # `fake` is the offline/test adapter. Platform admins can later override
    # model/effort per prompt key via the ai_prompts table.
    ai_text_provider: str = "anthropic"  # anthropic | openai | fake
    ai_text_model: str = "claude-opus-4-8"
    ai_text_effort: str = "high"  # low | medium | high
    anthropic_api_key: str = ""
    # Alternate text model behind the same port (providers/openai.py). When
    # selecting it, set ai_text_model to an OpenAI id (e.g. gpt-5.1) too.
    openai_api_key: str = ""
    # Media understanding (app/ai/media.py) — must be a BILLING-ENABLED
    # AI Studio project (free-tier input may train on guest PII). Empty =
    # media inputs refused; pasted text still works.
    gemini_api_key: str = ""
    # Gemini model ids are config, not code (they churn) — confirmed against
    # ai.google.dev/gemini-api/docs/models 2026-07-12. Transcription = the GA
    # flash model; images = "Nano Banana 2" (gemini-3.1-flash-image), priced
    # per image, not per token (see ai/pricing.py IMAGE_PRICES).
    gemini_transcribe_model: str = "gemini-3.5-flash"
    gemini_image_model: str = "gemini-3.1-flash-image"
    # Venue resolution (app/ai/resolve.py). Empty = venues stay as the
    # couple's own words (degraded, never invented).
    google_places_api_key: str = ""

    # LOCAL-DEV ONLY: a static bearer token that stands in for a Supabase login
    # so /admin works on SQLite without Supabase Auth. Empty in production (then
    # only a real Supabase session is accepted). Set it in .env.local.
    dev_admin_token: str = ""

    # --- Image uploads (admin) -------------------------------------------------
    # Story/iconography images uploaded from /admin. Two backends behind
    # app/storage.py: locally we write to backend/uploads/ and serve via the
    # FastAPI `/media` mount (URLs prefixed with `media_base_url`); in production
    # we push to a public Supabase Storage bucket and return its public URL.
    # `media_base_url` is where this API is reachable for static media (no
    # trailing slash). The Supabase service key is only needed for prod uploads.
    media_base_url: str = "http://localhost:8000"
    supabase_storage_bucket: str = "invite-media"
    supabase_service_key: str = ""

    @property
    def use_supabase_storage(self) -> bool:
        """Prod path: push uploads to Supabase Storage (needs URL + service key)."""
        return bool(self.supabase_url and self.supabase_service_key)

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def admin_email_list(self) -> list[str]:
        return [e.strip().lower() for e in self.admin_emails.split(",") if e.strip()]

    @property
    def is_production(self) -> bool:
        return self.environment.lower() in ("production", "prod")

    @property
    def is_sqlite(self) -> bool:
        return self.database_url.startswith("sqlite")

    @property
    def db_backend(self) -> str:
        """Human label for the active DB — surfaced at /health and on startup so
        it's obvious whether you're pointed at local SQLite or production."""
        return "sqlite" if self.is_sqlite else "postgres"


@lru_cache
def get_settings() -> Settings:
    return Settings()
