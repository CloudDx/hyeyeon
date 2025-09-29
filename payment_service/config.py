from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    app_port: int = 8081
    database_url: str
    log_level: str = "info"
    rabbitmq_host: str = "rabbitmq"

    class Config:
        env_file = ".env"

settings = Settings()
