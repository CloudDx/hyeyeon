from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    app_port: int = 8080
    database_url: str
    event_id: str = "E1"
    hold_ttl_sec: int = 60
    idempotency_ttl_sec: int = 120
    log_level: str = "info"

    class Config:
        env_file = ".env"

settings = Settings()
