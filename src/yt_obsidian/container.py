# src/yt_obsidian/container.py

import logging
import requests
from pathlib import Path
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from typing import Optional

from .config import settings
from .clients.youtube_client import YouTubeClient
from .clients.transcript_client import TranscriptClient
from .writers.markdown_writer import MarkdownWriter
from .processor import VideoProcessor

logger = logging.getLogger(__name__)

class CachedSession(requests.Session):
    """
    Extended requests.Session with built-in timeout, caching, and retry functionality.
    """
    def __init__(self, timeout: int = 30, retries: int = 3):
        super().__init__()
        self.base_timeout = timeout
        
        # Configure retry strategy
        retry_strategy = Retry(
            total=retries,
            backoff_factor=1,
            status_forcelist=[429, 500, 502, 503, 504],
            allowed_methods=["GET", "POST"]
        )
        
        # Mount the retry adapter to both HTTP and HTTPS requests
        adapter = HTTPAdapter(max_retries=retry_strategy)
        self.mount("http://", adapter)
        self.mount("https://", adapter)
        
        logger.debug(f"Initialized CachedSession with timeout={timeout}s, retries={retries}")
    
    def request(self, method, url, **kwargs):
        """Override request method to apply default timeout if not specified"""
        if 'timeout' not in kwargs:
            kwargs['timeout'] = self.base_timeout
        return super().request(method, url, **kwargs)


class ServiceContainer:
    """
    Service container that manages dependencies and provides factory methods
    for creating service clients.
    """
    def __init__(self, config=None):
        """
        Initialize the service container with configuration and shared resources.
        
        Args:
            config: Optional config instance. If not provided, the global settings will be used.
        """
        # Use importlib to get the settings at runtime
        # This allows tests to mock the settings module
        if config is None:
            from .config import settings
            self.config = settings
        else:
            self.config = config
        self.config.validate()
        
        # Initialize the shared HTTP client
        self.http_client = CachedSession(
            timeout=self.config.request_timeout,
            retries=self.config.retry_count
        )
        
        logger.debug("ServiceContainer initialized")
    
    def get_youtube_client(self) -> YouTubeClient:
        """
        Factory method to create a YouTube client instance.
        
        Returns:
            YouTubeClient: Configured YouTube API client with shared HTTP session
        """
        return YouTubeClient(
            api_key=self.config.youtube_api_key,
            session=self.http_client
        )
    
    def get_transcript_client(self) -> TranscriptClient:
        """
        Factory method to create a transcript client instance.
        
        Returns:
            TranscriptClient: Configured transcript client with shared HTTP session
        """
        return TranscriptClient(session=self.http_client)
    
    def get_writer(self) -> MarkdownWriter:
        """
        Factory method to create a markdown writer instance.
        
        Returns:
            MarkdownWriter: Configured markdown writer with shared HTTP session
        """
        return MarkdownWriter(session=self.http_client)
    
    def create_processor(self) -> VideoProcessor:
        """
        Factory method to create a video processor instance.
        
        The processor encapsulates the business logic for processing
        YouTube videos, playlists, and channels.
        
        Returns:
            VideoProcessor: Configured processor with all required clients
        """
        return VideoProcessor(
            youtube_client=self.get_youtube_client(),
            transcript_client=self.get_transcript_client(),
            writer=self.get_writer()
        )
    
    def __enter__(self):
        """Context manager entry point"""
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """
        Context manager exit point - clean up resources.
        
        This ensures proper cleanup of resources like HTTP connections
        when the container goes out of scope.
        """
        if hasattr(self, 'http_client') and self.http_client:
            self.http_client.close()
            logger.debug("HTTP client session closed")
        
        return False  # Don't suppress exceptions