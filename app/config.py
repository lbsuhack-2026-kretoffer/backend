from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "sqlite:///./school_balance.db"
    secret_key: str = "dev-secret-change-me"
    session_cookie: str = "sb_session"
    session_max_age: int = 60 * 60 * 24 * 30
    api_prefix: str = "/api/v1"
    cors_origins: list[str] = ["http://localhost:5173", "http://localhost:3000"]
    ml_service_url: str | None = None
    seed_demo: bool = True


settings = Settings()
