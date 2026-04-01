from pathlib import Path
from pydantic_settings import BaseSettings

# .env siempre relativo a este archivo: backend/app/config.py → backend/.env
_ENV_FILE = Path(__file__).parent.parent / ".env"


class Settings(BaseSettings):
    MONGODB_URI: str = "mongodb://localhost:27017"
    JWT_SECRET: str = "cambiar-esto"
    DEFAULT_LANG: str = "es"
    MQTT_BROKER_HOST: str = "localhost"
    MQTT_BROKER_PORT: int = 1883
    REDIS_URL: str = "redis://localhost:6379"

    class Config:
        env_file = str(_ENV_FILE)
        extra = "ignore"


settings = Settings()
