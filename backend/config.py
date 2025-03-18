from pydantic_settings import BaseSettings
import os
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

class Settings(BaseSettings):
    GROQ_API_KEY: str = os.getenv("GROQ_API_KEY")  # Load API key safely
    DEV_DB_URL: str = os.getenv("DEV_DB_URL")  # Uncomment if needed

    class Config:
        env_file = ".env"

# Instantiate settings
settings = Settings()
