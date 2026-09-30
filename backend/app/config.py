import re

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    # No fixed fallback on purpose: a hardcoded default would be a known
    # secret baked into source control, letting anyone who has read this repo
    # forge tokens against any deployment that forgets to set SECRET_KEY.
    # Required: startup fails below if it's missing, short or a known public
    # value.
    secret_key: str = ""
    database_url: str = "sqlite:///./app.db"

    @field_validator("database_url")
    @classmethod
    def _normalize_database_url(cls, value: str) -> str:
        # Some Postgres providers hand out the old "postgres://" scheme, which
        # SQLAlchemy 2.x / psycopg2 no longer accept.
        if value.startswith("postgres://"):
            return "postgresql://" + value[len("postgres://") :]
        return value

    access_token_expire_minutes: int = 60
    refresh_token_expire_days: int = 30

    # Comma-separated browser origins allowed to call the API, e.g.
    # "https://example.github.io". "*" is refused: list every origin.
    cors_origins: str = "http://localhost:8000,http://127.0.0.1:8000,http://localhost:4000,http://127.0.0.1:4000"

    @field_validator("cors_origins")
    @classmethod
    def _check_cors_origins(cls, value: str) -> str:
        origins = []
        for origin in (o.strip() for o in value.split(",")):
            if not origin:
                continue
            if "*" in origin:
                raise ValueError("CORS_ORIGINS must list exact origins; '*' wildcards are not allowed")
            # Browsers send the origin without a trailing slash, so
            # "https://site.com/" would silently never match.
            origin = origin.rstrip("/")
            if not re.fullmatch(r"https?://[^/\s]+", origin):
                raise ValueError(f"CORS_ORIGINS entry {origin!r} must look like https://host[:port], with no path")
            origins.append(origin)
        return ",".join(origins)

    # Login and signup attempts allowed per client IP per minute (each
    # counted separately). 0 turns the limit off.
    auth_rate_limit_per_minute: int = 5

    # How many reverse proxies in front of the app append to X-Forwarded-For
    # (1 on Railway). With 0, the direct connection's address is the client
    # IP and X-Forwarded-For is ignored, since clients can set it to anything.
    trusted_proxy_count: int = 0

    # Leave blank to keep "Continue with Google" disabled until you add a real OAuth client ID.
    google_client_id: str = ""

    # Leave blank to have the demo admin account seeded with a fresh random
    # password printed to the server log on first startup, instead of a fixed
    # credential baked into source control.
    demo_admin_password: str = ""

    # Same idea, shared by every seeded starter host/renter account (see
    # seed.py) so they're all reachable with one login during local dev/demo
    # without a fixed credential baked into source control.
    demo_user_password: str = ""

    # Seeds/reseeds the demo hosts, renters, listings, reviews, and admin
    # account on every startup, printing any generated passwords to the log.
    # Off unless SEED_DEMO_DATA=true, so a deployment that forgets the setting
    # doesn't get an admin account whose password is in its logs.
    seed_demo_data: bool = False

    # S3-compatible bucket for listing photos (AWS S3, Cloudflare R2, MinIO,
    # ...). Photo uploads return 503 until endpoint, bucket, key and secret
    # are all set. The bucket must allow public reads of uploaded objects.
    s3_endpoint: str = ""
    s3_bucket: str = ""
    s3_key: str = ""
    s3_secret: str = ""
    # Optional. Most providers accept the default; R2 also accepts "auto".
    s3_region: str = "us-east-1"
    # Optional. Base URL photos are publicly served from, if it differs from
    # "<S3_ENDPOINT>/<S3_BUCKET>" (e.g. an R2 public bucket URL or a CDN).
    s3_public_url: str = ""

    @property
    def s3_configured(self) -> bool:
        return all([self.s3_endpoint, self.s3_bucket, self.s3_key, self.s3_secret])

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]


# Values that have been public in this repo (the .env.example placeholder and
# an old hardcoded default). A server using one would accept tokens anyone can
# forge, so they're refused like a missing key.
_PUBLIC_SECRET_KEYS = {"change-this-to-a-long-random-secret", "dev-only-secret-change-me"}
_MIN_SECRET_KEY_LENGTH = 32

settings = Settings()

if not settings.secret_key or settings.secret_key in _PUBLIC_SECRET_KEYS or len(settings.secret_key) < _MIN_SECRET_KEY_LENGTH:
    raise RuntimeError(
        f"SECRET_KEY must be set to a private random value of at least {_MIN_SECRET_KEY_LENGTH} characters "
        "(not the .env.example placeholder). Generate one with:\n"
        '  python -c "import secrets; print(secrets.token_urlsafe(64))"'
    )
