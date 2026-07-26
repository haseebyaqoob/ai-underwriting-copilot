
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    ENV: str = "development"

    
    DATABASE_URL: str = "postgresql+psycopg2://postgres:postgres@localhost:5432/yaqeen"

    
    JWT_SECRET_KEY: str = "CHANGE_ME_IN_PRODUCTION"
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 15
    REFRESH_TOKEN_EXPIRE_DAYS: int = 30

   
    BCRYPT_ROUNDS: int = 12
    REFRESH_COOKIE_NAME: str = "yaqeen_refresh"

    # --- CORS -------------------------------------------------------------
    FRONTEND_ORIGINS: list[str] = ["http://localhost:3000", "http://localhost:5173"]

    # --- Redis / background (used from Module 3 onward) --------------------
    REDIS_URL: str = "redis://localhost:6379/0"

    # --- AI providers (used from Module 3+ onward) -------------------------
    GEMINI_API_KEY: str = ""
    AI_PROVIDER: str = "gemini"
    GEMINI_MODEL_NAME: str = "gemini-2.5-flash"  # vision-capable, good cost/latency for this use case

    # --- Object storage (used from Module 2+ onward) -----------------------
    STORAGE_BACKEND: str = "local"  # local | s3
    LOCAL_STORAGE_PATH: str = "./uploads"


settings = Settings()
