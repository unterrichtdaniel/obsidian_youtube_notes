import logging
import os
import sys
import time
from typing import Optional, Any, Dict, TYPE_CHECKING
from pydantic import BaseModel, ConfigDict
import openai
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type, RetryError
import socket  # For socket.timeout

# Use TYPE_CHECKING to avoid circular imports
if TYPE_CHECKING:
    from ..container import CachedSession

from yt_obsidian.config import settings, AppConfig

logger = logging.getLogger(__name__)

class SummaryRequest(BaseModel):
    model_config = ConfigDict(validate_assignment=True)
    
    transcript: str
    template: Optional[str] = None

class OpenAICompatibleClient:
    def __init__(self, session: Optional["CachedSession"] = None):
        """
        Initialize the OpenAI compatible client with an optional session.
        
        Args:
            session: Optional CachedSession for HTTP requests with retry and timeout handling
        """
        # Reload settings to ensure we get the latest environment variables
        from yt_obsidian.config import AppConfig
        self.settings = AppConfig()
        
        self.base_url = self.settings.api_endpoint
        # Convert empty string to None
        self.api_key = self.settings.api_key if self.settings.api_key else None
        self.session = session
        
        # Use test model in test environment, production model otherwise
        self.model = self.settings.test_model if 'pytest' in sys.modules else self.settings.model
        
        # Configure openai client instance
        # Allow empty API key for testing
        client_args = {
            "base_url": self.base_url,
            "api_key": self.api_key or "sk-dummy-key",
            # Set a longer timeout for Ollama to have time to load models
            "timeout": 120.0,  # 2 minutes timeout
        }
        
        # Don't pass our CachedSession directly to OpenAI client
        # as it expects a different interface with a 'timeout' attribute
        # We'll keep the session for our own use if needed
        
        self.client = openai.OpenAI(**client_args)

    def _make_api_request(self, **kwargs) -> Dict[str, Any]:
        """Make API request with retry logic"""
        # Reload retry config to ensure we get the latest environment variables
        from yt_obsidian.config import RetryConfig
        retry_config = RetryConfig()
        
        # Get the retry config
        max_retries = retry_config.max_retries
        initial_delay = retry_config.initial_delay
        max_delay = retry_config.max_delay
        exp_base = retry_config.exponential_base
        
        @retry(
            stop=stop_after_attempt(max_retries + 1),  # +1 for initial attempt
            wait=wait_exponential(
                multiplier=initial_delay,
                max=max_delay,
                exp_base=exp_base
            ),
            # Include timeout and connection errors for Ollama model loading
            retry=retry_if_exception_type((
                openai.APIError,
                openai.APIConnectionError,
                openai.RateLimitError,
                socket.timeout,
                ConnectionError,
                Exception  # Catch all exceptions to be more resilient
            )),
            reraise=True
        )
        def _request():
            try:
                response = self.client.chat.completions.create(**kwargs)
                # Log successful response details
                logger.info(f"API request successful: model={kwargs.get('model')}, tokens={getattr(getattr(response, 'usage', None), 'total_tokens', 'unknown')}")
                return response
            except openai.APIError as e:
                attempt = kwargs.get('_attempt', 1)
                logger.warning(f"API Error (attempt {attempt}): {str(e)}, status_code={getattr(e, 'status_code', 'unknown')}, type={type(e).__name__}")
                raise
            except openai.APIConnectionError as e:
                attempt = kwargs.get('_attempt', 1)
                logger.warning(f"API Connection Error (attempt {attempt}): {str(e)}, type={type(e).__name__}")
                raise
            except openai.RateLimitError as e:
                attempt = kwargs.get('_attempt', 1)
                logger.warning(f"Rate Limit Error (attempt {attempt}): {str(e)}, status_code={getattr(e, 'status_code', 'unknown')}, type={type(e).__name__}")
                raise
            except Exception as e:
                attempt = kwargs.get('_attempt', 1)
                logger.warning(f"Unexpected error (attempt {attempt}): {str(e)}, type={type(e).__name__}")
                raise

        try:
            return _request()
        except RetryError as e:
            # Re-raise the original exception
            if e.__cause__:
                raise e.__cause__
            raise

    def generate_summary(self, request: SummaryRequest) -> str:
        """Generate summary using OpenAI-compatible API"""
        base_prompt = (
            "Summarize this lecture/interview transcript. Include:\n"
            "1. Resources mentioned (books/papers/people)\n"
            "2. Important concepts\n"
            "3. Key takeaways\n"
            "4. Chronological overview with timestamp ranges\n\n"
            "Structure the summary for readability using markdown."
        )
        
        if request.template:
            prompt = f"{base_prompt}\n\nUse this template:\n{request.template}"
        else:
            prompt = base_prompt

        messages = [
            {
                "role": "system",
                "content": request.transcript
            },
            {
                "role": "user",
                "content": prompt
            }
        ]

        try:
            logger.info(f"Generating summary using {self.model} at {self.base_url}")
            logger.debug(f"Prompt length: {len(request.transcript)} characters")
            
            start_time = time.time()
            response = self._make_api_request(
                model=self.model,
                messages=messages,
                temperature=0.3
            )
            elapsed_time = time.time() - start_time
            
            # Log detailed response information
            tokens_used = getattr(response, 'usage', {})
            logger.info(f"Summary generated successfully: model={self.model}, elapsed_time={elapsed_time:.2f}s")
            logger.debug(f"Token usage: {tokens_used}")
            
            summary_content = response.choices[0].message.content
            logger.debug(f"Summary length: {len(summary_content)} characters")
            
            return summary_content
            
        except Exception as e:
            error_type = type(e).__name__
            logger.error(f"Failed to generate summary after all retries: {error_type}: {str(e)}")
            # Log additional context that might help diagnose the issue
            logger.debug(f"Context: model={self.model}, base_url={self.base_url}, transcript_length={len(request.transcript)}")
            raise