from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    database_url: str = "postgresql+psycopg://postgres:postgres@localhost:5432/school_balance"
    secret_key: str = "change-me-in-prod"
    session_cookie: str = "sbp_session"
    cookie_secure: bool = False
    frontend_origins: str = "http://localhost:5173,http://localhost:8080"
    superadmin_email: str = "admin@school-balance.by"
    superadmin_password: str = "admin12345"
    superadmin_name: str = "Платформенный администратор"
    ml_service_url: str = "http://localhost:8001"

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    @property
    def origins(self) -> list[str]:
        return [o.strip() for o in self.frontend_origins.split(",") if o.strip()]


settings = Settings()
