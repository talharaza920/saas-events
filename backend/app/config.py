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

    # --- AI: live calls (app/ai/, AI_WIZARD_PLAN Phase 8) -----------------------
    # ONE switch for "may this process spend money on AI?", plus per-capability
    # overrides. The master WINS: with AI_LIVE_CALLS=false nothing leaves the
    # box, whatever the four flags below say. With it on, each capability can
    # still be turned off on its own (keep text drafting, stop paying for
    # images). `None` = inherit the master.
    #
    # Off is a DEGRADE, never a crash — every one of these paths already exists
    # for the no-key case: text falls back to the offline `fake` adapter, image
    # generation skips (beats stay text-only), transcription refuses media with
    # a clear message, venue resolution keeps the couple's own words.
    #
    # This is the DEPLOY-time switch, and it is deliberately not the only one:
    # the platform kill-switch (DB, ops, no redeploy) and the daily cost ceiling
    # both still apply on top of it.
    ai_live_calls: bool = True
    ai_live_text: bool | None = None
    ai_live_images: bool | None = None
    ai_live_transcribe: bool | None = None
    ai_live_places: bool | None = None

    # LOCAL-DEV ONLY, and the image twin of the offline `fake` text adapter:
    # draw placeholder art in-process so the staged story wizard (8.5b) can be
    # demoed and browser-smoked end to end without spending a cent. Refused
    # outside development for the obvious reason — a real wedding must never get
    # a placeholder where it asked for an illustration.
    ai_fake_images: bool = False

    # --- AI: providers + models -------------------------------------------------
    # The text model is pluggable by config; media (Gemini) is a hard-coded seam.
    # `fake` is the offline/test adapter.
    ai_text_provider: str = "anthropic"  # anthropic | openai | fake
    ai_text_effort: str = "high"  # low | medium | high
    anthropic_api_key: str = ""
    openai_api_key: str = ""
    # Media understanding + image generation (app/ai/media.py) — must be a
    # BILLING-ENABLED AI Studio project (free-tier input may train on guest
    # PII). Empty = media inputs refused; pasted text still works.
    gemini_api_key: str = ""
    # Venue resolution (app/ai/resolve.py). Empty = venues stay as the
    # couple's own words (degraded, never invented).
    google_places_api_key: str = ""

    # Model ids are config, not code — they churn, and swapping one must never
    # need a code change. ONE PER PROVIDER, so selecting a provider selects its
    # model too: `AI_TEXT_PROVIDER=openai` alone is a valid, correct config.
    # (It used to also need AI_TEXT_MODEL, and getting that wrong pointed a
    # Claude id at OpenAI.) AI_TEXT_MODEL stays as an explicit override — set it
    # to pin an exact snapshot id; empty = the configured provider's default.
    # Gemini ids confirmed against ai.google.dev/gemini-api/docs/models
    # 2026-07-12: transcription = the GA flash model; images = "Nano Banana 2",
    # priced per image, not per token (see ai/pricing.py IMAGE_PRICES).
    ai_text_model: str = ""  # "" = the provider default below
    ai_model_anthropic: str = "claude-opus-4-8"
    ai_model_openai: str = "gpt-5.1"
    gemini_transcribe_model: str = "gemini-3.5-flash"
    gemini_image_model: str = "gemini-3.1-flash-image"

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

    # --- AI capability gates ----------------------------------------------------
    # Ask these, never the raw key or flag: each one folds together "is it
    # configured?" and "are we allowed to call it?", which are the two ways a
    # capability can be off and which every call site would otherwise have to
    # remember to check separately.

    def _live(self, override: bool | None) -> bool:
        """Master AND per-capability. A `true` override can never resurrect a
        capability the master switched off — that direction is the safe one, and
        the whole point of having a master."""
        if not self.ai_live_calls:
            return False
        return True if override is None else override

    @property
    def ai_text_live(self) -> bool:
        """False = serve the offline `fake` adapter whatever the provider says."""
        return self._live(self.ai_live_text)

    @property
    def ai_transcribe_enabled(self) -> bool:
        return bool(self.gemini_api_key) and self._live(self.ai_live_transcribe)

    @property
    def ai_images_enabled(self) -> bool:
        return bool(self.gemini_api_key) and self._live(self.ai_live_images)

    @property
    def ai_fake_images_enabled(self) -> bool:
        """The dev placeholder painter — never in production, whatever the env
        file says (same stance as the dev admin token)."""
        return self.ai_fake_images and self.environment != "production"

    @property
    def ai_images_available(self) -> bool:
        """Can this process illustrate anything at all? Ask THIS at the call
        sites: real Gemini, or the dev painter, or neither (in which case the
        story stays text and the UI says so instead of offering a paid button
        that can only fail)."""
        return self.ai_images_enabled or self.ai_fake_images_enabled

    @property
    def ai_places_enabled(self) -> bool:
        return bool(self.google_places_api_key) and self._live(self.ai_live_places)

    @property
    def text_model(self) -> str:
        """The model id for the CONFIGURED provider — ALWAYS read this, never the
        raw `ai_text_model` field. An explicit AI_TEXT_MODEL wins, else that
        provider's own default, so a provider swap can't leave a Claude id
        pointed at OpenAI."""
        if self.ai_text_model.strip():
            return self.ai_text_model.strip()
        return {
            "anthropic": self.ai_model_anthropic,
            "openai": self.ai_model_openai,
            "fake": "fake",  # don't report a real model id we aren't calling
        }.get(self.ai_text_provider.strip().lower(), self.ai_model_anthropic)

    @property
    def ai_mode(self) -> str:
        """One-line summary for the startup log — so a process that is NOT
        going to call a real model says so, loudly, before anyone wonders why
        the drafts look canned."""
        # ASCII only: this lands in a server log line and the Windows console is
        # cp1252 (LEARNINGS 2026-07-09).
        if not self.ai_text_live:
            return "ai=OFFLINE (fake text model; live calls are switched off)"
        capabilities = ",".join(
            name
            for name, on in (
                ("transcribe", self.ai_transcribe_enabled),
                ("images", self.ai_images_enabled),
                ("places", self.ai_places_enabled),
            )
            if on
        )
        return (
            f"ai={self.ai_text_provider}/{self.text_model} "
            f"[{capabilities or 'text only'}]"
        )

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
