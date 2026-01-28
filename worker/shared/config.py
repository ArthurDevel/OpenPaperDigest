from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import model_validator, Field
from dotenv import load_dotenv
from typing import Optional, Any, Dict
import os

# Load environment variables from .env file.
# `override=True` ensures that the .env file takes precedence over system environment variables.
load_dotenv(override=True)

class Settings(BaseSettings):
   
    CONTAINERPORT_API: int = 8000
    CONTAINERPORT_FRONTEND: int = 3000
    OPENROUTER_API_KEY: str
    CONTAINERPORT_QDRANT: int = 6333
    CONTAINERPORT_QDRANT_GRPC: int = 6334

    # Vector search related
    VOYAGE_API_KEY: str
    QDRANT_HOST: str
    QDRANT_PORT: int
    QDRANT_API_KEY: str
    
    MYSQL_USER: str
    MYSQL_PASSWORD: str
    MYSQL_HOST: str
    MYSQL_PORT: int = 3306
    MYSQL_DATABASE: str

settings = Settings()

