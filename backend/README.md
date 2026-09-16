# Uzbek Rentals API — full app backend

FastAPI app that serves the whole site (clean URLs, no `.html` in the address bar)
and powers the login / sign-up flow: email+password accounts with a `renter` or
`host` role, JWT access + refresh tokens, and bcrypt password hashing. SQLite by
default; swap `DATABASE_URL` for Postgres in production.

## Setup

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # then edit SECRET_KEY at minimum
```

`SECRET_KEY` can be left blank for local dev — a random one is generated per
process if unset — but set a real value in `.env` for anything you want tokens
to survive a restart on.

## Run

```bash
source .venv/bin/activate   # if not already active
uvicorn app.main:app --reload --port 8000
```

Open `http://localhost:8000/` — that's the homepage now (not `index.html`). API
docs are at `http://localhost:8000/docs`. Stop the server with `Ctrl+C`.

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

## Notes / production TODOs

- Set a strong random `SECRET_KEY` and never commit `.env`.
- `CORS_ORIGINS` must list the exact origin(s) the frontend is served from.
- Refresh tokens are stateless JWTs (not stored server-side), so they can't be
  revoked individually — add a token-blacklist table if you need logout-everywhere.
- No rate limiting is included; put one in front (e.g. via a reverse proxy) before
  going to production to slow down credential-stuffing attempts.
- Table creation uses `Base.metadata.create_all` for simplicity. Add Alembic
  migrations before you need to evolve the schema without dropping data.
- If you have a pre-existing local `app.db` from before Google sign-in was added,
  delete it (or add the `google_sub` column yourself) — `create_all` only creates
  missing tables, it won't add columns to one that already exists.
