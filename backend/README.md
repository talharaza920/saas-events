# Backend — FastAPI

Tenant-aware wedding RSVP API.

## First-time install (Windows / PowerShell)

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

## Local vs production — one switch: `DATABASE_URL`

The active database is chosen entirely by `DATABASE_URL`:

- **Production** → Supabase pooler URL, lives in `.env` (gitignored).
- **Local dev** → `sqlite:///./dev.db`, lives in `.env.local` (gitignored).

`.env.local` **overrides** `.env` when present, so switching never means editing
the secret-bearing `.env`:

```powershell
# --- go LOCAL (SQLite) ---
copy .env.local.example .env.local      # sets DATABASE_URL=sqlite:///./dev.db
python -m scripts.dev_setup             # create schema + seed wedding + demo guests
uvicorn app.main:app --reload --port 8000

# --- go PRODUCTION (Supabase) ---
del .env.local                          # .env (Supabase URL) takes over again
```

`GET /health` returns `"db": "sqlite"` or `"db": "postgres"` so you can always
tell which you're on; the backend also prints the backend on startup. A real
`DATABASE_URL` environment variable beats both files (one-off override).

`scripts/dev_setup.py` is SQLite-only (it refuses to run against Supabase) and
prints ready-to-open invite links:

```
solo         http://localhost:3000/i/solo-demo
plus_one     http://localhost:3000/i/plusone-demo
plus_family  http://localhost:3000/i/family-demo
```

Reset the local DB anytime: delete `dev.db` and re-run `dev_setup`.

## Production DB tasks (Supabase)

With `.env` active (no `.env.local`):

```powershell
alembic upgrade head                    # apply migrations (RLS skipped on SQLite)
python -m scripts.seed_wedding          # upsert the wedding row
python -m scripts.import_guests --file <xlsx> --wedding-slug alex-and-sam
```

## Endpoints

- Health: http://localhost:8000/health
- OpenAPI docs: http://localhost:8000/docs
- OpenAPI schema (for FE type generation): http://localhost:8000/openapi.json
- Guest invite API: `GET /api/i/{slug}`, `POST /api/i/{slug}/rsvp`
- Admin API (owner-only, `Authorization: Bearer <token>`): `/api/admin/me`,
  `/api/admin/guests` (CRUD), `/api/admin/questions` (CRUD),
  `/api/admin/responses`, `/api/admin/summary`, `/api/admin/export.csv`.
  Locally, set `DEV_ADMIN_TOKEN` in `.env.local` and use it as the bearer token;
  in production only a Supabase JWT whose email is in `ADMIN_EMAILS` is accepted.

## Tests

```powershell
.\.venv\Scripts\python.exe -m pytest -q   # offline (in-memory SQLite), no Supabase
```
