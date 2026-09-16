import secrets
import warnings

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    # No fixed fallback on purpose: a hardcoded default would be a known
    # secret baked into source control, letting anyone who has read this repo
    # forge tokens against any deployment that forgets to set SECRET_KEY.
    # Leave unset and one is generated per-process instead (existing tokens
    # won't survive a restart, but nothing forgeable ships in source).
    secret_key: str = ""
    database_url: str = "sqlite:///./app.db"

    access_token_expire_minutes: int = 30
    refresh_token_expire_days: int = 30

    cors_origins: str = "http://localhost:8000,http://127.0.0.1:8000,http://localhost:4000,http://127.0.0.1:4000"

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

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]


settings = Settings()

if not settings.secret_key:
    settings.secret_key = secrets.token_urlsafe(64)
    warnings.warn(
        "SECRET_KEY is not set; generated a random one for this process. "
        "Tokens will stop validating on restart. Set SECRET_KEY in your .env "
        "for a stable, production-ready deployment.",
        stacklevel=1,
    )
