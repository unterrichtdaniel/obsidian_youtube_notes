# src/yt_obsidian/config.py

import os
from pydantic import BaseModel, Field, ConfigDict
from typing import Optional

class RetryConfig(BaseModel):
    model_config = ConfigDict(validate_assignment=True)
    
    max_retries: int = Field(default_factory=lambda: int(os.environ.get("MAX_RETRIES", "3")))
    initial_delay: float = Field(default_factory=lambda: float(os.environ.get("INITIAL_RETRY_DELAY", "1.0")))
    max_delay: float = Field(default_factory=lambda: float(os.environ.get("MAX_RETRY_DELAY", "60.0")))
    exponential_base: float = Field(default_factory=lambda: float(os.environ.get("RETRY_EXPONENTIAL_BASE", "2.0")))

class Settings(BaseModel):
    # Required settings - will raise error if not provided
    youtube_api_key: str = Field(default_factory=lambda: os.environ.get("YOUTUBE_API_KEY", "dummy-key-for-testing"))
    obsidian_vault_path: str = Field(default_factory=lambda: os.environ.get("OBSIDIAN_VAULT_PATH", "./vault"))
    
    # Optional settings with defaults
    default_author: str = Field(default_factory=lambda: os.environ.get("DEFAULT_AUTHOR", "Unknown Channel"))
    
    # AI Model settings
    api_endpoint: str = Field(default_factory=lambda: os.environ.get("API_ENDPOINT", "http://localhost:11434/v1"))
    api_key: Optional[str] = Field(default_factory=lambda: os.environ.get("API_KEY"))
    model: str = Field(default_factory=lambda: os.environ.get("MODEL", "gemma:3b"))
    test_model: str = Field(default_factory=lambda: os.environ.get("TEST_MODEL", "gemma:3b"))
    
    # Retry configuration
    retry_config: RetryConfig = Field(default_factory=RetryConfig)

    model_config = ConfigDict(validate_assignment=True)

settings = Settings()