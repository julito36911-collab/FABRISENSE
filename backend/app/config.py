from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    MONGODB_URI: str = "mongodb://localhost:27017"
    JWT_SECRET: str = "cambiar-esto"
    DEFAULT_LANG: str = "es"

    class Config:
        env_file = ".env"


settings = Settings()
