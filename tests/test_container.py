# tests/test_container.py

import pytest
from unittest.mock import Mock, patch, MagicMock
from pathlib import Path

from yt_obsidian.container import ServiceContainer, CachedSession
from yt_obsidian.config import settings
from yt_obsidian.clients.youtube_client import YouTubeClient
from yt_obsidian.clients.transcript_client import TranscriptClient
from yt_obsidian.writers.markdown_writer import MarkdownWriter
from yt_obsidian.processor import VideoProcessor


@pytest.fixture
def mock_config():
    """Create a mock config for testing."""
    config = Mock(spec=settings.__class__)
    config.youtube_api_key = "test-api-key"
    config.request_timeout = 30
    config.retry_count = 3
    config.obsidian_vault_path = Path("/test/path")
    config.model = "test-model"
    config.api_endpoint = "http://localhost:11434/v1"
    config.api_key = "ollama"
    config.max_keywords = 20
    return config


class TestServiceContainer:
    """Test suite for the ServiceContainer class."""

    def test_initialization(self, mock_config):
        """Test that the container initializes correctly with a provided config."""
        container = ServiceContainer(config=mock_config)
        
        # Verify config is set and validated
        assert container.config == mock_config
        mock_config.validate.assert_called_once()
        
        # Verify HTTP client is initialized with correct parameters
        assert isinstance(container.http_client, CachedSession)
        assert container.http_client.base_timeout == mock_config.request_timeout

    def test_initialization_without_config(self):
        """Test that the container loads config if not provided."""
        # Create a mock AppConfig instance
        mock_config = Mock()
        mock_config.youtube_api_key = "test-api-key"
        mock_config.model = "test-model"
        mock_config.api_endpoint = "http://test-endpoint.com"
        
        # Patch the config constructor in the correct module location
        with patch('yt_obsidian.config.AppConfig', return_value=mock_config):
            # Create a new container without providing a config
            container = ServiceContainer()
            
            # Verify config is set to our mock config
            assert container.config == mock_config
            mock_config.validate.assert_called_once()

    def test_get_youtube_client(self, mock_config):
        """Test that get_youtube_client returns a properly configured YouTubeClient."""
        container = ServiceContainer(config=mock_config)
        
        # Get a YouTube client from the container
        youtube_client = container.get_youtube_client()
        
        # Verify the client is properly configured
        assert isinstance(youtube_client, YouTubeClient)
        assert youtube_client.api_key == mock_config.youtube_api_key
        assert youtube_client.session == container.http_client

    def test_get_transcript_client(self, mock_config):
        """Test that get_transcript_client returns a properly configured TranscriptClient."""
        container = ServiceContainer(config=mock_config)
        
        # Get a transcript client from the container
        transcript_client = container.get_transcript_client()
        
        # Verify the client is properly configured
        assert isinstance(transcript_client, TranscriptClient)
        assert transcript_client.session == container.http_client

    def test_get_writer(self, mock_config):
        """Test that get_writer returns a properly configured MarkdownWriter."""
        container = ServiceContainer(config=mock_config)
        
        # Get a writer from the container
        writer = container.get_writer()
        
        # Verify the writer is properly configured
        assert isinstance(writer, MarkdownWriter)
        assert writer.session == container.http_client

    def test_create_processor(self, mock_config):
        """Test that create_processor returns a properly configured VideoProcessor."""
        container = ServiceContainer(config=mock_config)
        
        # Mock the client factory methods to verify they're called
        container.get_youtube_client = MagicMock(return_value=Mock(spec=YouTubeClient))
        container.get_transcript_client = MagicMock(return_value=Mock(spec=TranscriptClient))
        container.get_writer = MagicMock(return_value=Mock(spec=MarkdownWriter))
        
        # Create a processor from the container
        processor = container.create_processor()
        
        # Verify the processor is properly configured
        assert isinstance(processor, VideoProcessor)
        container.get_youtube_client.assert_called_once()
        container.get_transcript_client.assert_called_once()
        container.get_writer.assert_called_once()
        
        # Verify the processor has the correct clients
        assert processor.youtube_client == container.get_youtube_client.return_value
        assert processor.transcript_client == container.get_transcript_client.return_value
        assert processor.writer == container.get_writer.return_value

    def test_context_manager(self, mock_config):
        """Test that the container works as a context manager and cleans up resources."""
        # Create a mock HTTP client to verify it's closed
        mock_http_client = Mock(spec=CachedSession)
        
        # Create a container and replace its HTTP client with our mock
        with patch('yt_obsidian.container.CachedSession', return_value=mock_http_client):
            with ServiceContainer(config=mock_config) as container:
                # Verify the container is returned by __enter__
                assert isinstance(container, ServiceContainer)
                
            # Verify the HTTP client is closed when the context manager exits
            mock_http_client.close.assert_called_once()


class TestCachedSession:
    """Test suite for the CachedSession class."""
    
    def test_initialization(self):
        """Test that the session initializes with correct parameters."""
        session = CachedSession(timeout=45, retries=5)
        
        assert session.base_timeout == 45
        # Verify adapters are mounted
        assert "http://" in session.adapters
        assert "https://" in session.adapters
        
    def test_request_with_default_timeout(self):
        """Test that the session applies the default timeout if not specified."""
        session = CachedSession(timeout=60)
        
        with patch('requests.Session.request') as mock_request:
            session.request('GET', 'http://example.com')
            
            # Verify the default timeout is applied
            mock_request.assert_called_once()
            _, kwargs = mock_request.call_args
            assert kwargs['timeout'] == 60
            
    def test_request_with_custom_timeout(self):
        """Test that the session respects a custom timeout if specified."""
        session = CachedSession(timeout=60)
        
        with patch('requests.Session.request') as mock_request:
            session.request('GET', 'http://example.com', timeout=30)
            
            # Verify the custom timeout is respected
            mock_request.assert_called_once()
            _, kwargs = mock_request.call_args
            assert kwargs['timeout'] == 30

    def test_container_resource_cleanup_on_exception(self, mock_config):
        """Test that resources are properly cleaned up even when an exception occurs."""
        # Create a mock HTTP client to verify it's closed
        mock_http_client = Mock(spec=CachedSession)
        
        # Create a container and replace its HTTP client with our mock
        with patch('yt_obsidian.container.CachedSession', return_value=mock_http_client):
            try:
                with ServiceContainer(config=mock_config) as container:
                    # Raise an exception inside the context manager
                    raise ValueError("Test exception")
            except ValueError:
                pass
                
            # Verify the HTTP client is closed even when an exception occurs
            mock_http_client.close.assert_called_once()
    
    def test_container_with_multiple_clients(self, mock_config):
        """Test that multiple clients can be created from the same container."""
        container = ServiceContainer(config=mock_config)
        
        # Create multiple clients
        youtube_client1 = container.get_youtube_client()
        youtube_client2 = container.get_youtube_client()
        transcript_client = container.get_transcript_client()
        writer = container.get_writer()
        
        # Verify each client is properly configured
        assert isinstance(youtube_client1, YouTubeClient)
        assert isinstance(youtube_client2, YouTubeClient)
        assert isinstance(transcript_client, TranscriptClient)
        assert isinstance(writer, MarkdownWriter)
        
        # Verify they all share the same HTTP session
        assert youtube_client1.session == container.http_client
        assert youtube_client2.session == container.http_client
        assert transcript_client.session == container.http_client
        assert writer.session == container.http_client
        
        # Verify the YouTube clients are different instances but configured the same
        assert youtube_client1 is not youtube_client2
        assert youtube_client1.api_key == youtube_client2.api_key