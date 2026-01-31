from pydantic_settings import BaseSettings
from dotenv import load_dotenv
from pathlib import Path

# Load environment variables from worker/.env
# Looks for .env in the worker directory (parent of shared/)
worker_env = Path(__file__).parent.parent / ".env"
load_dotenv(worker_env, override=True)

class Settings(BaseSettings):

    OPENROUTER_API_KEY: str
    DATABASE_URL: str

settings = Settings()

