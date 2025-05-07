# src/yt_obsidian/config.py

import os
from pathlib import Path
from pydantic import Field
from pydantic_settings import BaseSettings
from typing import Optional

class RetryConfig(BaseSettings):
    max_retries: int = Field(3, env="MAX_RETRIES")
    initial_delay: float = Field(1.0, env="INITIAL_RETRY_DELAY")
    max_delay: float = Field(60.0, env="MAX_RETRY_DELAY")
    exponential_base: float = Field(2.0, env="RETRY_EXPONENTIAL_BASE")
    
    model_config = {
        "env_prefix": "",
        "env_file": ".env",
        "env_file_encoding": "utf-8"
    }

class AppConfig(BaseSettings):
    """
    Application configuration using Pydantic BaseSettings for automatic
    environment variable loading and validation.
    """
    # Required settings (with defaults for testing)
    youtube_api_key: str = Field(os.environ.get("YOUTUBE_API_KEY", "test-api-key"), env="YOUTUBE_API_KEY")
    obsidian_vault_path: Path = Field(default_factory=lambda: Path(os.environ.get("OBSIDIAN_VAULT_PATH", "/tmp/test_vault")), env="OBSIDIAN_VAULT_PATH")
    
    # HTTP and retry settings
    request_timeout: int = 30
    retry_count: int = 3
    
    # Optional settings with defaults
    default_author: str = Field("Unknown Channel", env="DEFAULT_AUTHOR")
    
    # AI Model settings
    api_endpoint: str = Field(os.environ.get("API_ENDPOINT", "http://localhost:11434/v1"), env="API_ENDPOINT")
    api_key: Optional[str] = Field(os.environ.get("API_KEY", None), env="API_KEY")
    model: str = Field(os.environ.get("MODEL", "gemma:3b"), env="MODEL")
    test_model: str = Field(os.environ.get("TEST_MODEL", "test-model"), env="TEST_MODEL")  # Use a specific model name for tests
    max_keywords: int = Field(20, env="MAX_KEYWORDS")  # Maximum number of keywords to generate
    
    # Retry configuration
    retry_config: RetryConfig = Field(default_factory=RetryConfig)

    model_config = {
        "env_prefix": "",  # No prefix, use environment variables as defined in .envrc
        "env_file": ".env",
        "env_file_encoding": "utf-8"
    }

    @classmethod
    def load(cls):
        """Load configuration from environment variables and .env file"""
        # Log environment variables for debugging
        logger = logging.getLogger(__name__)
        logger.info(f"Loading configuration with environment variables:")
        logger.info(f"YOUTUBE_API_KEY: {os.environ.get('YOUTUBE_API_KEY', '[not set]')}")
        logger.info(f"OBSIDIAN_VAULT_PATH: {os.environ.get('OBSIDIAN_VAULT_PATH', '[not set]')}")
        logger.info(f"API_ENDPOINT: {os.environ.get('API_ENDPOINT', '[not set]')}")
        logger.info(f"MODEL: {os.environ.get('MODEL', '[not set]')}")
        return cls()

    def validate(self) -> None:
        """Perform additional validation beyond type checking"""
        if not self.obsidian_vault_path.exists():
            self.obsidian_vault_path.mkdir(parents=True, exist_ok=True)

# For backwards compatibility
settings = AppConfig()

# For backwards compatibility with tests
Settings = AppConfig