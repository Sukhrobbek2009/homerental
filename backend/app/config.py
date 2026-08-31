from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    secret_key: str = "dev-only-secret-change-me"
    database_url: str = "sqlite:///./app.db"

    access_token_expire_minutes: int = 30
    refresh_token_expire_days: int = 30

    cors_origins: str = "http://localhost:8000,http://127.0.0.1:8000,http://localhost:4000,http://127.0.0.1:4000"

    # Leave blank to keep "Continue with Google" disabled until you add a real OAuth client ID.
    google_client_id: str = ""

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]


settings = Settings()
