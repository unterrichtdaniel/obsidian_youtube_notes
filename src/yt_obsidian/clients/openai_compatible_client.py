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
from yt_obsidian.model_configs import get_model_config

logger = logging.getLogger(__name__)

class SummaryRequest(BaseModel):
    model_config = ConfigDict(validate_assignment=True)
    
    transcript: str
    template: Optional[str] = None

class KeywordsRequest(BaseModel):
    model_config = ConfigDict(validate_assignment=True)
    
    transcript: str
    max_keywords: Optional[int] = 20

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
        
        # Get model configuration based on model name
        self.model_config = get_model_config(self.model)
        self.max_transcript_chars = self.model_config["max_transcript_chars"]
        
        # Log model and environment information for debugging
        logger.info(f"Initializing OpenAI compatible client with model: {self.model}")
        logger.info(f"Model configuration: timeout={self.model_config['timeout']}s, max_chars={self.max_transcript_chars}")
        logger.info(f"API endpoint: {self.base_url}")
        logger.info(f"Environment variables: MODEL={os.environ.get('MODEL', 'not set')}, API_ENDPOINT={os.environ.get('API_ENDPOINT', 'not set')}")
        
        # Log more detailed model information for debugging
        logger.info(f"Requested model from settings: {self.settings.model}")
        logger.info(f"Test mode detection: {'pytest' in sys.modules}")
        logger.info(f"Selected model: {self.model}")
        logger.info(f"Model config used: {self.model_config}")
        
        # Log system resource information (if psutil is available)
        try:
            import psutil
            memory = psutil.virtual_memory()
            logger.info(f"System memory: total={memory.total/1024**3:.1f}GB, available={memory.available/1024**3:.1f}GB, percent_used={memory.percent}%")
            if hasattr(psutil, 'cpu_percent'):
                logger.info(f"CPU usage: {psutil.cpu_percent(interval=0.1)}%, cores: {psutil.cpu_count()}")
        except ImportError:
            logger.warning("psutil module not available. System resource info will not be logged.")
        except Exception as e:
            logger.warning(f"Could not get system resource info: {e}")
        
        # Configure openai client instance
        # Allow empty API key for testing
        client_args = {
            "base_url": self.base_url,
            "api_key": self.api_key or "sk-dummy-key",
            "timeout": self.model_config["timeout"],
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
            # Only retry on specific exception types, not all exceptions
            retry=retry_if_exception_type((
                openai.APIError,
                openai.APIConnectionError,
                openai.RateLimitError,
                socket.timeout,
                ConnectionError
                # Removed Exception catch-all to avoid retrying on non-retryable errors
            )),
            reraise=True
        )
        def _request():
            try:
                # Log request details before sending
                logger.info(f"Sending API request to {self.base_url} with model={kwargs.get('model')}")
                logger.info(f"Request timeout: {self.model_config['timeout']}s")
                
                # Track attempt number for logging but don't add to kwargs
                attempt = kwargs.pop('_attempt', 1) if '_attempt' in kwargs else 1
                attempt_for_logging = attempt
                
                # Create a clean copy of kwargs without _attempt
                api_kwargs = {k: v for k, v in kwargs.items() if k != '_attempt'}
                
                response = self.client.chat.completions.create(**api_kwargs)
                # Log successful response details
                logger.info(f"API request successful: model={kwargs.get('model')}, tokens={getattr(getattr(response, 'usage', None), 'total_tokens', 'unknown')}")
                return response
            except openai.APIError as e:
                logger.warning(f"API Error (attempt {attempt_for_logging}): {str(e)}, status_code={getattr(e, 'status_code', 'unknown')}, type={type(e).__name__}")
                raise
            except openai.APIConnectionError as e:
                logger.warning(f"API Connection Error (attempt {attempt_for_logging}): {str(e)}, type={type(e).__name__}")
                raise
            except openai.RateLimitError as e:
                logger.warning(f"Rate Limit Error (attempt {attempt_for_logging}): {str(e)}, status_code={getattr(e, 'status_code', 'unknown')}, type={type(e).__name__}")
                raise
            except Exception as e:
                logger.warning(f"Unexpected error (attempt {attempt_for_logging}): {str(e)}, type={type(e).__name__}")
                raise

        try:
            # Start with attempt 1
            kwargs['_attempt'] = 1
            return _request()
        except RetryError as e:
            # Re-raise the original exception
            if e.__cause__:
                raise e.__cause__
            raise

    def _chunk_transcript(self, transcript, max_chars, overlap=500):
        """
        Split a transcript into overlapping chunks of max_chars length.
        
        Args:
            transcript: The full transcript text
            max_chars: Maximum characters per chunk
            overlap: Number of characters to overlap between chunks
            
        Returns:
            List of transcript chunks
        """
        if len(transcript) <= max_chars:
            return [transcript]
            
        chunks = []
        start = 0
        
        while start < len(transcript):
            # Calculate end position
            end = start + max_chars
            
            # If this isn't the last chunk, try to break at a sentence
            if end < len(transcript):
                # Look for sentence breaks (., !, ?) within the last 20% of the chunk
                search_start = max(start + int(max_chars * 0.8), 0)
                search_text = transcript[search_start:end]
                
                # Find the last sentence break
                last_period = max(search_text.rfind('. '), search_text.rfind('! '), search_text.rfind('? '))
                
                if last_period != -1:
                    # Add 2 to include the period and space
                    end = search_start + last_period + 2
            
            # Add the chunk
            chunks.append(transcript[start:end])
            
            # Move start position for next chunk, accounting for overlap
            start = end - overlap
            
            # Ensure we don't go backwards (can happen with small chunks)
            start = max(start, end - overlap)
        
        logger.info(f"Split transcript into {len(chunks)} chunks with {overlap} char overlap")
        for i, chunk in enumerate(chunks):
            logger.debug(f"Chunk {i+1}/{len(chunks)}: {len(chunk)} chars")
            
        return chunks

    def generate_summary(self, request: SummaryRequest) -> str:
        """Generate summary using OpenAI-compatible API with chunking for long transcripts"""
        transcript_length = len(request.transcript)
        max_chars = self.max_transcript_chars
        
        # Log detailed transcript information
        logger.info(f"Original transcript length: {transcript_length} chars, max allowed: {max_chars} chars")
        
        # Determine if we need chunking
        if transcript_length > max_chars:
            logger.info(f"Transcript exceeds max length. Using chunking approach instead of truncation.")
            logger.info(f"Truncation would lose {(transcript_length - max_chars) / transcript_length * 100:.1f}% of content")
            return self._generate_chunked_summary(request)
        else:
            logger.info(f"Transcript within limits. Processing as single chunk.")
            return self._generate_single_summary(request)
    
    def _generate_single_summary(self, request: SummaryRequest) -> str:
        """Generate summary for a transcript that fits within max_chars limit"""
        transcript = request.transcript
        transcript_length = len(transcript)
        
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
                "content": "You are a skilled summarizer that creates concise, informative summaries of lecture transcripts. Focus on extracting key information and organizing it clearly."
            },
            {
                "role": "user",
                "content": prompt + "\n\nHere is the transcript to summarize:\n\n" + transcript
            }
        ]

        try:
            logger.info(f"Generating summary using {self.model} at {self.base_url}")
            logger.info(f"Transcript length: {transcript_length} characters")
            
            # Calculate approximate token count (rough estimate)
            approx_tokens = len(transcript.split())
            logger.info(f"Approximate token count: ~{approx_tokens} tokens")
            
            # Log Ollama server status check
            try:
                import requests
                health_url = f"{self.base_url.split('/v1')[0]}/api/health"
                logger.info(f"Checking Ollama server health at: {health_url}")
                health_response = requests.get(health_url, timeout=5)
                logger.info(f"Ollama server health check: {health_response.status_code} {health_response.text if hasattr(health_response, 'text') else ''}")
            except Exception as e:
                logger.warning(f"Failed to check Ollama server health: {str(e)}")
            
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
            logger.info(f"Detailed error context: model={self.model}, base_url={self.base_url}")
            logger.info(f"Transcript stats: length={transcript_length} chars, approx_tokens=~{len(transcript.split())}")
            
            if hasattr(e, 'response'):
                logger.info(f"API response status: {getattr(getattr(e, 'response', None), 'status_code', 'unknown')}")
                logger.debug(f"API response content: {getattr(getattr(e, 'response', None), 'text', 'not available')}")
                
            # Create a fallback summary for non-blocking operation
            fallback_summary = (
                "## Error Generating Summary\n\n"
                f"An error occurred while generating the summary: {error_type}: {str(e)}\n\n"
                "Please check the logs for more details or try again later with a different model configuration."
            )
            return fallback_summary
            
    def _generate_chunked_summary(self, request: SummaryRequest) -> str:
        """Generate summary for a transcript by processing it in chunks and combining results"""
        transcript = request.transcript
        max_chars = self.max_transcript_chars
        
        # Split transcript into chunks
        chunks = self._chunk_transcript(transcript, max_chars)
        logger.info(f"Processing transcript in {len(chunks)} chunks")
        
        # Process each chunk
        chunk_summaries = []
        for i, chunk in enumerate(chunks):
            logger.info(f"Processing chunk {i+1}/{len(chunks)} ({len(chunk)} chars)")
            
            # Create a prompt for this chunk
            chunk_prompt = (
                f"Summarize this SECTION {i+1}/{len(chunks)} of a longer transcript. Focus on:\n"
                "1. Key points and concepts discussed\n"
                "2. People, books, or resources mentioned\n"
                "3. Important quotes or statements\n\n"
                "Keep your summary focused on just this section's content."
            )
            
            messages = [
                {
                    "role": "system",
                    "content": "You are summarizing one section of a longer transcript. Focus on extracting key information from just this section."
                },
                {
                    "role": "user",
                    "content": chunk_prompt + "\n\nHere is section " + str(i+1) + "/" + str(len(chunks)) + " of the transcript:\n\n" + chunk
                }
            ]
            
            try:
                start_time = time.time()
                response = self._make_api_request(
                    model=self.model,
                    messages=messages,
                    temperature=0.3
                )
                elapsed_time = time.time() - start_time
                
                logger.info(f"Chunk {i+1} summary generated: elapsed_time={elapsed_time:.2f}s")
                chunk_summaries.append(response.choices[0].message.content)
                
            except Exception as e:
                logger.error(f"Error processing chunk {i+1}: {str(e)}")
                chunk_summaries.append(f"*Error processing this section: {str(e)}*")
        
        # Combine chunk summaries into a final summary
        combined_summary = "\n\n".join([
            f"## Section {i+1}/{len(chunks)} Summary\n{summary}"
            for i, summary in enumerate(chunk_summaries)
        ])
        
        # If there are multiple chunks, generate a meta-summary
        if len(chunks) > 1:
            try:
                logger.info("Generating meta-summary from chunk summaries")
                
                meta_prompt = (
                    "You have been given summaries of different sections of a longer transcript. "
                    "Create a cohesive overall summary that integrates these section summaries. Include:\n"
                    "1. Resources mentioned (books/papers/people) across all sections\n"
                    "2. Important concepts that appear throughout\n"
                    "3. Key takeaways from the entire transcript\n"
                    "4. A brief overview of the content\n\n"
                    "Structure the summary for readability using markdown."
                )
                
                messages = [
                    {
                        "role": "system",
                        "content": "You are creating a cohesive summary from multiple section summaries of a transcript."
                    },
                    {
                        "role": "user",
                        "content": meta_prompt + "\n\nHere are the section summaries:\n\n" + combined_summary
                    }
                ]
                
                start_time = time.time()
                response = self._make_api_request(
                    model=self.model,
                    messages=messages,
                    temperature=0.3
                )
                elapsed_time = time.time() - start_time
                
                logger.info(f"Meta-summary generated: elapsed_time={elapsed_time:.2f}s")
                
                final_summary = (
                    "# Overall Summary\n\n" +
                    response.choices[0].message.content +
                    "\n\n# Detailed Section Summaries\n\n" +
                    combined_summary
                )
                
                return final_summary
                
            except Exception as e:
                logger.error(f"Error generating meta-summary: {str(e)}")
                # Fall back to just the combined summaries
                return "# Transcript Section Summaries\n\n" + combined_summary
        else:
            # If there's only one chunk, just return its summary
            return chunk_summaries[0]
            
            # If there's only one chunk, just return its summary
            return chunk_summaries[0]
            
    def generate_keywords(self, request: KeywordsRequest) -> list:
        """Generate keywords using OpenAI-compatible API with chunking for long transcripts"""
        transcript_length = len(request.transcript)
        max_chars = self.max_transcript_chars
        
        # Log detailed transcript information
        logger.info(f"Original transcript length: {transcript_length} chars, max allowed: {max_chars} chars")
        
        # Determine if we need chunking
        if transcript_length > max_chars:
            logger.info(f"Transcript exceeds max length. Using chunking approach for keywords.")
            logger.info(f"Truncation would lose {(transcript_length - max_chars) / transcript_length * 100:.1f}% of content")
            return self._generate_chunked_keywords(request)
        else:
            logger.info(f"Transcript within limits. Processing keywords as single chunk.")
            return self._generate_single_keywords(request)
    
    def _generate_single_keywords(self, request: KeywordsRequest) -> list:
        """Generate keywords for a transcript that fits within max_chars limit"""
        transcript = request.transcript
        transcript_length = len(transcript)
        
        prompt = (
            "Extract the most important keywords and key phrases from this transcript. "
            "Focus on main topics, concepts, people, technologies, and terminology mentioned. "
            f"Return a list of {request.max_keywords} keywords or phrases, ordered by relevance. "
            "Format as a simple comma-separated list without numbering or bullet points."
        )
        
        # No truncation in single keywords mode
        
        messages = [
            {
                "role": "system",
                "content": "You are a skilled keyword extractor that identifies the most important topics, concepts, and terminology from transcripts."
            },
            {
                "role": "user",
                "content": prompt + "\n\nHere is the transcript to extract keywords from:\n\n" + transcript
            }
        ]
        
        try:
            logger.info(f"Generating keywords using {self.model} at {self.base_url}")
            logger.info(f"Transcript length: {transcript_length} characters")
            
            # Calculate approximate token count (rough estimate)
            approx_tokens = len(transcript.split())
            logger.info(f"Approximate token count: ~{approx_tokens} tokens")
            
            # Check if Ollama has the model loaded
            try:
                import requests
                models_url = f"{self.base_url.split('/v1')[0]}/api/tags"
                logger.info(f"Checking available models at: {models_url}")
                models_response = requests.get(models_url, timeout=5)
                if models_response.status_code == 200:
                    available_models = models_response.json()
                    logger.info(f"Available Ollama models: {available_models}")
                    if 'models' in available_models:
                        model_names = [m.get('name', '') for m in available_models.get('models', [])]
                        logger.info(f"Model names: {model_names}")
                        if self.model not in model_names:
                            logger.warning(f"Model {self.model} not found in available models: {model_names}")
                else:
                    logger.warning(f"Failed to get available models: {models_response.status_code}")
            except Exception as e:
                logger.warning(f"Failed to check available models: {str(e)}")
            
            start_time = time.time()
            response = self._make_api_request(
                model=self.model,
                messages=messages,
                temperature=0.3
            )
            elapsed_time = time.time() - start_time
            
            # Log detailed response information
            tokens_used = getattr(response, 'usage', {})
            logger.info(f"Keywords generated successfully: model={self.model}, elapsed_time={elapsed_time:.2f}s")
            logger.debug(f"Token usage: {tokens_used}")
            
            keywords_text = response.choices[0].message.content
            logger.debug(f"Keywords raw response: {keywords_text}")
            
            # Process the response into a list of keywords
            keywords = [kw.strip() for kw in keywords_text.split(',') if kw.strip()]
            logger.info(f"Generated {len(keywords)} keywords")
            
            return keywords
            
        except Exception as e:
            error_type = type(e).__name__
            logger.error(f"Failed to generate keywords after all retries: {error_type}: {str(e)}")
            # Log additional context that might help diagnose the issue
            logger.info(f"Detailed error context: model={self.model}, base_url={self.base_url}")
            logger.info(f"Transcript stats: length={transcript_length} chars, approx_tokens=~{len(transcript.split())}")
            
            if hasattr(e, 'response'):
                logger.info(f"API response status: {getattr(getattr(e, 'response', None), 'status_code', 'unknown')}")
                logger.debug(f"API response content: {getattr(getattr(e, 'response', None), 'text', 'not available')}")
            
            # Return empty list instead of raising to make this feature non-blocking
            logger.warning("Returning empty keywords list due to generation failure")
            return []
            
    def _generate_chunked_keywords(self, request: KeywordsRequest) -> list:
        """Generate keywords for a transcript by processing it in chunks and combining results"""
        transcript = request.transcript
        max_chars = self.max_transcript_chars
        
        # Split transcript into chunks
        chunks = self._chunk_transcript(transcript, max_chars)
        logger.info(f"Processing transcript in {len(chunks)} chunks for keyword extraction")
        
        # Process each chunk
        all_keywords = []
        for i, chunk in enumerate(chunks):
            logger.info(f"Extracting keywords from chunk {i+1}/{len(chunks)} ({len(chunk)} chars)")
            
            # Create a prompt for this chunk
            chunk_prompt = (
                f"Extract the most important keywords and key phrases from this SECTION {i+1}/{len(chunks)} of a longer transcript. "
                "Focus on main topics, concepts, people, technologies, and terminology mentioned. "
                f"Return a list of {min(request.max_keywords, 10)} keywords or phrases from this section, ordered by relevance. "
                "Format as a simple comma-separated list without numbering or bullet points."
            )
            
            messages = [
                {
                    "role": "system",
                    "content": "You are extracting keywords from one section of a longer transcript. Focus on the most important terms in just this section."
                },
                {
                    "role": "user",
                    "content": chunk_prompt + "\n\nHere is section " + str(i+1) + "/" + str(len(chunks)) + " of the transcript:\n\n" + chunk
                }
            ]
            
            try:
                start_time = time.time()
                response = self._make_api_request(
                    model=self.model,
                    messages=messages,
                    temperature=0.3
                )
                elapsed_time = time.time() - start_time
                
                logger.info(f"Chunk {i+1} keywords generated: elapsed_time={elapsed_time:.2f}s")
                
                # Process the response
                keywords_text = response.choices[0].message.content
                chunk_keywords = [kw.strip() for kw in keywords_text.split(',') if kw.strip()]
                all_keywords.extend(chunk_keywords)
                logger.debug(f"Extracted {len(chunk_keywords)} keywords from chunk {i+1}")
                
            except Exception as e:
                logger.error(f"Error processing chunk {i+1} for keywords: {str(e)}")
                # Continue with other chunks
        
        # Deduplicate and limit keywords
        unique_keywords = []
        seen = set()
        for kw in all_keywords:
            kw_lower = kw.lower()
            if kw_lower not in seen:
                seen.add(kw_lower)
                unique_keywords.append(kw)
        
        # Limit to requested number
        final_keywords = unique_keywords[:request.max_keywords]
        logger.info(f"Generated {len(final_keywords)} unique keywords from {len(chunks)} chunks")
        
        return final_keywords