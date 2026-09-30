# Uzbek Rentals API — full app backend

FastAPI app that serves the whole site (clean URLs, no `.html` in the address bar)
and powers the login / sign-up flow: email+password accounts with a `renter` or
`host` role, JWT access + refresh tokens, and bcrypt password hashing. SQLite by
default; swap `DATABASE_URL` for Postgres in production.

## Setup

```bash
cd backend
python3.12 -m venv .venv   # Python 3.12 (see .python-version)
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
python -c "import secrets; print(secrets.token_urlsafe(64))"   # paste into SECRET_KEY in .env
alembic upgrade head   # create the schema (SQLite by default)
```

`SECRET_KEY` is required: the app won't start without a private value of at
least 32 characters. Set `SEED_DEMO_DATA=true` in `.env` if you want demo
listings and accounts locally.

## Run

```bash
source .venv/bin/activate   # if not already active
uvicorn app.main:app --reload --port 8000
```

Open `http://localhost:8000/` — that's the homepage now (not `index.html`). API
docs are at `http://localhost:8000/docs`. Stop the server with `Ctrl+C`.

Verify it's up with:

```bash
curl http://localhost:8000/health
# {"status":"ok"}
```

(`/api/health` is the same check, kept for backwards compatibility with existing callers.)

On first startup the app seeds demo data (starter listings, hosts, renters, and
an admin account) into the local SQLite database. `DEMO_ADMIN_PASSWORD` and
`DEMO_USER_PASSWORD` in `.env` are optional — leave them blank and a random
password is generated once and printed to the terminal, e.g.:

```
[seed] No DEMO_ADMIN_PASSWORD set — generated one for admin@uzbekrentals.app: <password>
[seed] No DEMO_USER_PASSWORD set — generated one for the starter accounts: <password>
```

Copy that password from the log to sign in as `admin@uzbekrentals.app` (admin
dashboard) or any seeded host/renter, e.g. `host-aziza@uzbekrentals.app` /
`renter-dilnoza@uzbekrentals.app` (see `app/seed.py` for the full list) — every
seeded host/renter account shares the one `DEMO_USER_PASSWORD`. Set both
variables explicitly in `.env` if you want stable credentials across restarts.

## Page routes

The app reads the `.html` files at the repo root and serves them at clean paths
(`backend/app/routers/pages.py`). All internal links across every page were
rewritten to match, so navigating the site never shows a `.html` URL:

| URL                  | File                        |
|-----------------------|------------------------------|
| `/`                    | `index.html`                 |
| `/login`, `/signup`    | `auth.html` (mode set by path) |
| `/listings`            | `listings.html`               |
| `/listings/property`   | `listing-detail.html`         |
| `/listings/car`        | `car-listing-detail.html`     |
| `/host-dashboard`      | `host-dashboard.html`         |
| `/renter-dashboard`    | `renter-dashboard.html`       |
| `/messages`            | `messages.html`               |
| `/profile`             | `profile.html`                |

`auth.html`'s form now calls the real API (`/api/auth/signup` and `/api/auth/login`)
instead of faking success — see "Wiring" below.

## Endpoints

| Method | Path                  | Auth   | Purpose                                  |
|--------|-----------------------|--------|-------------------------------------------|
| POST   | `/api/auth/signup`    | none   | Create account, returns tokens + user     |
| POST   | `/api/auth/login`     | none   | Log in, returns tokens + user             |
| POST   | `/api/auth/refresh`   | none   | Exchange refresh token for new access token |
| GET    | `/api/auth/me`        | Bearer | Current user profile                      |
| PATCH  | `/api/auth/me/role`   | Bearer | Switch between `renter` / `host`          |
| POST   | `/api/auth/google`    | none   | Exchange a Google ID token for our tokens |
| GET    | `/api/config`         | none   | Public config the frontend needs (Google client ID) |
| GET    | `/api/health`         | none   | Liveness check                            |
| GET    | `/api/listings/mine`  | Bearer | Current user's own listings                |
| POST   | `/api/listings`       | Bearer | Create a listing (home or car)             |
| PATCH  | `/api/listings/{id}`  | Bearer | Update a listing you own (partial)         |
| DELETE | `/api/listings/{id}`  | Bearer | Delete a listing you own                   |

Listing ownership is enforced server-side: `PATCH`/`DELETE` on a listing you don't
own returns `403`, regardless of what the UI shows. There's no public "browse all
listings" endpoint yet — `listings.html` / `listing-detail.html` still show static
demo data; only the host dashboard is wired to real data so far.

`signup` body: `{ full_name, email, phone?, password, role? }` (`role` defaults to
`renter`; the frontend's "Rent" / "List a property" step maps to this field —
call `PATCH /api/auth/me/role` right after signup once the user picks one, or pass
`role` directly in the signup call).

Tokens: access token expires in `ACCESS_TOKEN_EXPIRE_MINUTES` (default 30), refresh
token in `REFRESH_TOKEN_EXPIRE_DAYS` (default 30). Send the access token as
`Authorization: Bearer <token>`.

## Wiring in `auth.html`

The form calls the real API with a relative `fetch` (same-origin, since this app
serves the page too):

- Sign up → `POST /api/auth/signup`, stores `access_token`/`refresh_token` in
  `localStorage`, then shows the rent-vs-host role step.
- "Rent" → redirects straight to `/listings` (new accounts default to `renter`).
- "List a property or car" → `PATCH /api/auth/me/role` with `role: "host"`
  (Bearer token from `localStorage`), then redirects to `/host-dashboard`.
- Log in → `POST /api/auth/login`, stores tokens, redirects to `/host-dashboard`
  or `/listings` based on the returned user's role.
- Validation and auth errors from the API (both the single-string `detail` and the
  Pydantic array-of-errors shape) render inline above the submit button.

Every other page now also has a "Log in" link in its nav bar, since none of them
linked to the auth page before. Once logged in (a token exists in `localStorage`),
that link turns into "Log out" everywhere, and the profile page has its own
"Log out" entry too — both just clear the stored tokens and redirect to `/login`.

## Google sign-in

"Continue with Google" is fully wired up but ships **disabled** until you add a
Google OAuth Client ID — see the `GOOGLE_CLIENT_ID` instructions in `.env.example`.
With it blank: `GET /api/config` returns an empty `google_client_id`, the frontend
leaves the button disabled with an explanatory tooltip, and `POST /api/auth/google`
returns `501` — nothing else is affected.

Once you set `GOOGLE_CLIENT_ID` and restart the server:

1. The button becomes clickable. Google renders its real "Sign in with Google"
   button invisibly on top of ours (`auth.html`'s `googleBtnOverlay`) so the click
   is a trusted user gesture, as Google Identity Services requires — you still see
   our styling.
2. Google returns an ID token to `handleGoogleCredential`, which POSTs it to
   `/api/auth/google`.
3. The backend verifies the token's signature and audience with `google-auth`
   (`app/security.py::verify_google_credential`), then finds-or-creates a user by
   `google_sub` (falling back to matching by email, so an existing password
   account gets linked rather than duplicated) and issues our normal JWTs.

Google-only accounts have `password_hash = NULL`; trying to log in with a password
on one returns a clear "This account uses Google sign-in" error instead of a
confusing generic failure.

Test it locally with a real ID by adding `http://localhost:8000` under
"Authorized JavaScript origins" for your OAuth client in Google Cloud Console —
Google Identity Services checks the exact origin, so `127.0.0.1` won't match if
you registered `localhost` (or vice versa).

## Host dashboard CRUD

`host-dashboard.html` now redirects to `/login` immediately (before the page
renders) if there's no token in `localStorage`. Once loaded, it:

- Fetches `GET /api/listings/mine` and renders real cards — no more hardcoded
  demo listings, and an empty state if you have none yet.
- "Add New Listing" opens a modal (title, home/car type, location, price, status,
  and type-specific fields — bedrooms/home-type for homes, vehicle-type/
  transmission for cars) that `POST`s to `/api/listings`.
- The pencil icon on each card opens the same modal pre-filled, `PATCH`ing on save.
- The new trash icon `DELETE`s after a confirm dialog.
- "Total listings" and "Active listings" stat cards are computed from the real
  list, not hardcoded. Booking counts were removed from cards entirely rather
  than showing fabricated numbers — there's no bookings feature yet.

A `401` from any listings call (expired/invalid token) clears storage and bounces
back to `/login`, same as an expired session anywhere else on the site.

## Database migrations

Schema is managed entirely by Alembic now — there's no more `Base.metadata.create_all`
and no hand-rolled column patcher. After pulling changes that touch `app/models.py`:

```bash
alembic revision --autogenerate -m "describe the change"   # review the generated file
alembic upgrade head
```

`alembic/env.py` reads `DATABASE_URL` from the same `app.config.settings` the app
uses, so migrations always target whatever database your `.env` (or Railway env
vars) point at — no separate URL to keep in sync.

## Deploy

### How the app starts

`railway.json` (Railway, Nixpacks builder) starts the service with:

```bash
alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port $PORT --no-access-log
```

- **Migrations run first** on every deploy. If one fails, the app doesn't start
  and the previous deploy keeps serving.
- **`PORT`** is set by the platform; Uvicorn listens on it.
- **Health check:** `GET /health` (also `/api/health`) returns `{"status":"ok"}`.
  Railway waits for it (up to 300 s) before switching traffic to a new deploy.
- **Python 3.12**, pinned in `.python-version` (read by Nixpacks and by CI).
- Request logs (`METHOD path status time ip=…`) replace Uvicorn's access log.

Any other host works the same way: install `requirements.txt` on Python 3.12,
set the variables below, and run the command above.

### Railway setup

1. Create a Railway project, add a **Postgres** plugin, and add this repo as a
   service with **Root Directory** set to `backend/`.
2. Set the environment variables below. Railway provides `DATABASE_URL` and
   `PORT` itself.
3. Deploy, then check the logs: the `ip=` in request lines should show
   visitors' addresses, not the same Railway address for everyone (see
   `TRUSTED_PROXY_COUNT`).

### Environment variables

Every setting the app reads (`app/config.py`). Names are case-insensitive.
Locally they can go in `backend/.env` (see `.env.example`; never commit `.env`).

**Required**

| Variable | Default | Description |
|---|---|---|
| `SECRET_KEY` | — | Signs login tokens. At least 32 random characters; the app refuses to start without one or with the old `.env.example` placeholder. Generate: `python -c "import secrets; print(secrets.token_urlsafe(64))"`. Changing it logs everyone out. |
| `DATABASE_URL` | `sqlite:///./app.db` | Database connection. Use Postgres in production (Railway sets it). `postgres://` URLs are accepted. |
| `CORS_ORIGINS` | localhost ports 8000 and 4000 | Comma-separated browser origins allowed to call the API, e.g. `https://you.github.io`. Exact `scheme://host[:port]` only: no `*`, no path. Not needed for pages served by this backend itself. |

**Recommended in production**

| Variable | Default | Description |
|---|---|---|
| `TRUSTED_PROXY_COUNT` | `0` | Reverse proxies in front of the app that add to `X-Forwarded-For`. Set `1` on Railway, or every visitor shares one login rate limit. Leave `0` when nothing sits in front, since clients can forge the header. |
| `AUTH_RATE_LIMIT_PER_MINUTE` | `5` | Login and signup attempts per IP per minute (counted separately). `0` disables. Counts are per app instance. |
| `SEED_DEMO_DATA` | `false` | `true` creates demo hosts, renters, listings, reviews and an admin on every start, printing generated passwords to the log. For local development only. |

**Optional features**

| Variable | Default | Description |
|---|---|---|
| `S3_ENDPOINT` | — | S3-compatible storage endpoint for listing photos (AWS S3, Cloudflare R2, MinIO…). Photo uploads return 503 until endpoint, bucket, key and secret are all set. |
| `S3_BUCKET` | — | Bucket name. Must allow public reads of uploaded objects. |
| `S3_KEY` | — | Access key ID. |
| `S3_SECRET` | — | Secret access key. |
| `S3_REGION` | `us-east-1` | Region; most providers accept the default (R2 also accepts `auto`). |
| `S3_PUBLIC_URL` | — | Public base URL for photos when it isn't `<S3_ENDPOINT>/<S3_BUCKET>` (e.g. an R2 public URL or CDN). |
| `GOOGLE_CLIENT_ID` | — | OAuth client ID; enables "Continue with Google". Blank keeps it disabled. |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | `60` | Lifetime of access tokens. |
| `REFRESH_TOKEN_EXPIRE_DAYS` | `30` | Lifetime of refresh tokens. |
| `DEMO_ADMIN_PASSWORD` | random | Password for the seeded `admin@uzbekrentals.app`. Only used with `SEED_DEMO_DATA=true`; if blank, a random one is printed to the log. |
| `DEMO_USER_PASSWORD` | random | Shared password for the seeded demo hosts and renters. Same rules. |

**Set by the platform / CI only**

| Variable | Description |
|---|---|
| `PORT` | Port Uvicorn listens on (Railway sets it). |
| `TEST_POSTGRES_URL` | Tests only. Postgres server for `tests/test_booking_concurrency.py`; the tests create and drop their own temporary database there. Without it those 3 tests are skipped. |

### Continuous integration

`.github/workflows/tests.yml` runs `pytest` on every push and pull request,
on Python 3.12 with a Postgres 17 service, so the booking-overlap tests run too.
The tests always use their own temporary SQLite database and ignore any
`DATABASE_URL`, so they can't touch a real database.

## Notes / production TODOs

- Refresh tokens are stateless JWTs (not stored server-side), so they can't be
  revoked individually — add a token-blacklist table if you need logout-everywhere.
- Login/signup rate limits are kept in memory per instance. If you run more than
  one instance, move them to a shared store (e.g. Redis).

## Frontend API address

Every page loads `config.js` and `api.js` from the repo root. `config.js` holds
the one deploy-time setting, `apiBaseUrl`: leave it `''` when this backend
serves the pages (local dev), or set it to the API's origin (e.g.
`https://your-api.up.railway.app`) when the pages are hosted elsewhere, such as
GitHub Pages. In that case, also add the pages' origin to `CORS_ORIGINS`.

`api.js` exposes `apiFetch()`, which all pages use for backend calls. It adds the
stored bearer token and, on any 401 (other than a failed login/signup), clears
the session and redirects to `/login?redirect=<current page>`.
