# Supabase auth & keys — recurring mistakes (portable reference)

> Project-agnostic. Written to fold into the `rt-code-preferences` skill so the
> same Supabase auth mistakes stop recurring across projects.

## TL;DR — the one rule

**When a separate backend (FastAPI/Express/etc.) must authenticate a Supabase
user, do NOT verify the access token with the legacy symmetric `JWT Secret`
(HS256).** Default to **token introspection** (`GET /auth/v1/user`) or, for
high-traffic APIs, **asymmetric JWT verification via the JWKS endpoint**. The
symmetric secret is legacy and silently breaks on projects that sign tokens with
the newer asymmetric keys.

---

## The mistake (made repeatedly)

```python
# ❌ DON'T — the default that keeps biting us
import jwt
claims = jwt.decode(
    token,
    settings.SUPABASE_JWT_SECRET,      # the project's symmetric "JWT Secret"
    algorithms=["HS256"],
    audience="authenticated",
)
```

Why it's wrong:

1. **It breaks on asymmetric-signing projects.** Supabase has moved to asymmetric
   signing keys (ES256 / RS256, exposed via JWKS). New projects can issue tokens
   that **cannot** be verified with any symmetric secret — `jwt.decode(...HS256)`
   throws and *all* admin auth fails. The legacy "JWT Secret" still exists for old
   projects but is being phased out; don't build new code on it.
2. **It's a high-value secret to manage/leak/rotate** for no benefit when public
   options exist.
3. **It invites key confusion** (see the table below) — people paste the anon /
   publishable key, or the DB password, into `SUPABASE_JWT_SECRET` and burn an
   hour. Different things entirely.

---

## The four things people call "the key" (don't mix them up)

| Name | Looks like | Where it goes | Purpose |
|---|---|---|---|
| **Publishable key** (was `anon`) | `sb_publishable_…` (new) / long JWT (legacy) | **Browser-safe.** `apikey` header; `createClient` | Public client key; gated by RLS |
| **Secret key** (was `service_role`) | `sb_secret_…` (new) / long JWT (legacy) | **Server only, NEVER browser** | Privileged key; **bypasses RLS** |
| **JWT Secret** | random string (Settings → API → JWT) | legacy token signing/verification | Symmetric signing secret — **avoid for new verification code** |
| **Database password** | your DB password | Postgres connection string | Direct DB connect (not auth) |

A user's **access token** (the session JWT from `getSession()`) is a *fifth*
thing — it's what you actually verify, and it is NOT any of the above.

---

## Correct backend patterns

### Option B — Token introspection (default; simplest, algorithm-agnostic)

Ask Supabase to validate the token. No secret, works regardless of signing alg.

```python
import httpx

def verify_supabase_token(token: str) -> dict:
    r = httpx.get(
        f"{SUPABASE_URL}/auth/v1/user",
        headers={
            "Authorization": f"Bearer {token}",   # the user's access token
            "apikey": SUPABASE_PUBLISHABLE_KEY,    # PUBLIC key, not a secret
        },
        timeout=5.0,
    )
    if r.status_code != 200:
        raise Unauthorized("Invalid or expired session")
    return r.json()        # { id, email, ... } — then check your allowlist
```

- Pros: zero crypto, no secret, immune to HS256↔ES256 changes.
- Cons: one network call per request → for low-traffic/admin APIs this is fine;
  cache or use Option C if it's hot path.

### Option C — Asymmetric verify via JWKS (high-traffic; offline)

```python
import jwt
from jwt import PyJWKClient

_jwks = PyJWKClient(f"{SUPABASE_URL}/auth/v1/.well-known/jwks.json")  # cache this

def verify_supabase_token(token: str) -> dict:
    key = _jwks.get_signing_key_from_jwt(token).key
    return jwt.decode(
        token, key,
        algorithms=["ES256", "RS256"],   # NOT HS256
        audience="authenticated",
    )
```

- Pros: offline, fast, no per-request call.
- Cons: more code; cache JWKS with a TTL and handle key rotation / `kid`.

### Decision rule

- Low-traffic / admin-only / want simplest → **introspection (B)**.
- High-traffic / latency-sensitive → **JWKS asymmetric verify (C)**.
- **Never** the symmetric `JWT Secret` for new code.

---

## Frontend keys & client choice

- Browser env: `NEXT_PUBLIC_SUPABASE_URL` + **publishable key**
  (`sb_publishable_…`). Safe to expose. **Never** ship the secret/service_role key
  to the browser.
- **`@supabase/supabase-js`** — base client. Enough for a client component / SPA
  that reads `supabase.auth.getSession().access_token` and calls your own API with
  it as a bearer. **You do NOT need `@supabase/ssr` for this.**
- **`@supabase/ssr`** — cookie-based session storage so Next.js **server
  components / middleware / route handlers** can read the session (SSR-auth pages,
  server-side RLS queries). Add it only when the server needs the session.

### OAuth redirect gotcha

`supabase-js` v2 defaults to the **PKCE** flow → the provider redirect returns
`?code=…`. The browser client's `detectSessionInUrl` (default on) exchanges it
automatically; with `@supabase/ssr` you do the exchange in a server
`/auth/callback` route. Symptom of a mismatch: "logged in with Google but the app
still thinks I'm signed out." Check flow type vs. where you handle the code.

---

## Related Supabase gotchas (same family)

- **Driver scheme:** SQLAlchemy needs `postgresql+psycopg://` (psycopg **v3**).
  Plain `postgresql://` loads psycopg2 → `ModuleNotFoundError: psycopg2`.
- **Pooler choice:** *session* pooler = port **5432**; *transaction* pooler =
  port **6543** (use this for serverless/Vercel). For the transaction pooler,
  disable prepared statements (psycopg: `prepare_threshold=None`) and use
  `NullPool` — pgbouncer in transaction mode can't keep prepared statements.
- **Pooler URL placeholders:** fill the `<region>` in the copied connection
  string (wrong region → `Tenant or user not found`); strip any trailing space in
  the pasted password.
- **RLS as a backstop:** `ENABLE ROW LEVEL SECURITY` on every table; the owner/
  `postgres` connection bypasses RLS, `anon`/`authenticated` are denied. Do **not**
  use `FORCE` (it applies RLS to the owner too and locks the backend out).

---

## Pre-flight checklist (paste into a PR / review)

- [ ] Backend verifies the user token via **introspection or JWKS**, not the
      symmetric JWT Secret.
- [ ] No `SUPABASE_JWT_SECRET` / `service_role` / secret key anywhere in frontend
      or `NEXT_PUBLIC_*`.
- [ ] `apikey` header uses the **publishable** key; bearer is the **user's**
      access token (two different values).
- [ ] Frontend uses `@supabase/ssr` **only** if a server needs the session.
- [ ] Postgres URL is `postgresql+psycopg://`, transaction pooler for serverless.
