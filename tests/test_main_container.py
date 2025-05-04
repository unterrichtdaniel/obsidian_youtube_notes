# tests/test_main_container.py

import pytest
from unittest.mock import Mock, patch, MagicMock
from click.testing import CliRunner
from pathlib import Path

from yt_obsidian.main import cli, process
from yt_obsidian.container import ServiceContainer
from yt_obsidian.processor import VideoProcessor


@pytest.fixture
def mock_container():
    """Create a mock ServiceContainer for testing."""
    container = Mock(spec=ServiceContainer)
    processor = Mock(spec=VideoProcessor)
    container.create_processor.return_value = processor
    
    # Setup processor mock methods
    processor.detect_content_type.return_value = ("video", "test-video-id")
    processor.process_video = MagicMock()
    processor.process_playlist = MagicMock()
    processor.process_channel = MagicMock()
    
    # Add context manager methods to the mock
    container.__enter__ = MagicMock(return_value=container)
    container.__exit__ = MagicMock(return_value=False)
    
    return container, processor


class TestMainWithContainer:
    """Test suite for the main CLI with ServiceContainer integration."""
    
    def test_process_command_with_container(self, mock_container):
        """Test that the process command uses the ServiceContainer correctly."""
        container, processor = mock_container
        
        # Mock the ServiceContainer context manager
        with patch('yt_obsidian.main.ServiceContainer', return_value=container) as mock_container_class:
            # Container is already configured as a context manager in the fixture
            
            runner = CliRunner()
            result = runner.invoke(cli, ['process', 'https://www.youtube.com/watch?v=test-video-id'])
            
            # Verify the command executed successfully
            assert result.exit_code == 0
            
            # Verify the container was used as a context manager
            container.__enter__.assert_called_once()
            container.__exit__.assert_called_once()
            
            # Verify the processor was created using the container
            container.create_processor.assert_called_once()
            
            # Verify content detection was called
            processor.detect_content_type.assert_called_once_with('https://www.youtube.com/watch?v=test-video-id')
            
            # Verify the correct processing method was called
            processor.process_video.assert_called_once()
    
    def test_process_command_with_playlist(self, mock_container):
        """Test processing a playlist."""
        container, processor = mock_container
        processor.detect_content_type.return_value = ("playlist", "test-playlist-id")
        
        with patch('yt_obsidian.main.ServiceContainer', return_value=container):
            # Container is already configured as a context manager in the fixture
            
            runner = CliRunner()
            result = runner.invoke(cli, ['process', 'https://www.youtube.com/playlist?list=test-playlist-id'])
            
            assert result.exit_code == 0
            processor.process_playlist.assert_called_once()
    
    def test_process_command_with_channel(self, mock_container):
        """Test processing a channel."""
        container, processor = mock_container
        processor.detect_content_type.return_value = ("channel", "test-channel-id")
        
        with patch('yt_obsidian.main.ServiceContainer', return_value=container):
            # Container is already configured as a context manager in the fixture
            
            runner = CliRunner()
            result = runner.invoke(cli, ['process', 'https://www.youtube.com/channel/test-channel-id', '--max-depth', '5'])
            
            assert result.exit_code == 0
            processor.process_channel.assert_called_once()
            # Verify max-depth parameter was passed correctly
            assert processor.process_channel.call_args[0][2] == False  # overwrite
            assert processor.process_channel.call_args[0][3] == 5  # max_depth
    
    def test_process_command_with_dry_run(self, mock_container):
        """Test dry run mode."""
        container, processor = mock_container
        
        with patch('yt_obsidian.main.ServiceContainer', return_value=container):
            # Container is already configured as a context manager in the fixture
            
            runner = CliRunner()
            result = runner.invoke(cli, ['process', 'https://www.youtube.com/watch?v=test-video-id', '--dry-run'])
            
            assert result.exit_code == 0
            # Verify detection was called but not processing
            processor.detect_content_type.assert_called_once()
            processor.process_video.assert_not_called()
    
    def test_process_command_with_error_handling(self, mock_container):
        """Test error handling in the process command."""
        container, processor = mock_container
        processor.detect_content_type.side_effect = Exception("Test error")
        
        with patch('yt_obsidian.main.ServiceContainer', return_value=container):
            # Container is already configured as a context manager in the fixture
            
            runner = CliRunner()
            result = runner.invoke(cli, ['process', 'https://www.youtube.com/watch?v=test-video-id'])
            
            # Verify the command failed with non-zero exit code
            assert result.exit_code != 0
            
            # Verify the container was still properly cleaned up
            container.__exit__.assert_called_once()
    
    def test_process_command_with_invalid_content_type(self, mock_container):
        """Test handling of invalid content type."""
        container, processor = mock_container
        processor.detect_content_type.return_value = (None, None)
        
        with patch('yt_obsidian.main.ServiceContainer', return_value=container):
            # Container is already configured as a context manager in the fixture
            
            runner = CliRunner()
            result = runner.invoke(cli, ['process', 'invalid-input'])
            
            # Verify the command failed with non-zero exit code
            assert result.exit_code != 0