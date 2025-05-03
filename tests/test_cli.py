# tests/test_cli.py
import pytest
import sys
import os
from pathlib import Path
from unittest.mock import patch, Mock

# Add src to path for imports
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../src")))

from yt_obsidian.main import detect_content_type, process_video, process_playlist, process_channel
from yt_obsidian.config import settings # Import settings if needed for defaults
from click.testing import CliRunner
from yt_obsidian.main import cli # Import the click cli object

# --- Fixtures ---

@pytest.fixture
def mock_clients():
    """Provides mocked YouTube, Transcript, and Writer clients."""
    # Import the actual classes to use with spec
    from yt_obsidian.clients.youtube_client import YouTubeClient
    from yt_obsidian.clients.transcript_client import TranscriptClient
    from yt_obsidian.writers.markdown_writer import MarkdownWriter
    # Patch the classes where they are imported in main.py
    # Using autospec=True is generally preferred over spec=ClassName
    with patch('yt_obsidian.main.YouTubeClient', autospec=True) as mock_yt_class, \
         patch('yt_obsidian.main.TranscriptClient', autospec=True) as mock_tr_class, \
         patch('yt_obsidian.main.MarkdownWriter', autospec=True) as mock_writer_class:

        # Get the mock instances that will be used when the classes are instantiated
        mock_yt = mock_yt_class.return_value
        mock_tr = mock_tr_class.return_value
        mock_writer = mock_writer_class.return_value

        # --- Configure mock methods on the INSTANCES ---
        # Basic mock setup (can be customized per test)
        mock_yt.get_video_details.return_value = [{"snippet": {"title": "Mock Video"}, "id": "test_vid_id"}]
        mock_yt.get_videos_from_playlist.return_value = [{"contentDetails": {"videoId": "pl_vid_1"}, "snippet": {"title": "Playlist Video 1"}}]
        mock_yt.get_channel_playlists.return_value = [{"id": "pl_id_1", "snippet": {"title": "Channel Playlist 1"}}]
        # Add default mock for the new API verification method - IMPORTANT
        # autospec should ensure the method exists if it's in the class
        mock_yt.verify_input_type.return_value = (None, None)
        mock_tr.get_transcript.return_value = "Mock transcript content."
        mock_writer.write_video_note.return_value = "mock_path/video_note.md"

        yield mock_yt, mock_tr, mock_writer # Yield the instances

@pytest.fixture
def runner():
    """Provides a Click CliRunner instance."""
    return CliRunner()

@pytest.fixture
def temp_output_dir(tmp_path):
    """Provides a temporary directory for output files."""
    output_dir = tmp_path / "test_output"
    output_dir.mkdir()
    return output_dir


# --- Tests for detect_content_type ---

# Fixture specifically for detect_content_type tests
@pytest.fixture
def mock_yt_client_for_detect():
    """Provides a mocked YouTubeClient instance for detect_content_type tests."""
    # Import the actual class to use with spec
    from yt_obsidian.clients.youtube_client import YouTubeClient
    # Use autospec=True for more rigorous mocking
    mock_client = Mock(autospec=YouTubeClient)
    # Ensure the method exists on the spec'd mock
    mock_client.verify_input_type.return_value = (None, None) # Default API fallback result
    return mock_client


@pytest.mark.parametrize("input_str, expected_type, expected_id", [
    # Video URLs
    ("https://www.youtube.com/watch?v=dQw4w9WgXcQ", "video", "dQw4w9WgXcQ"),
    ("https://youtu.be/dQw4w9WgXcQ", "video", "dQw4w9WgXcQ"),
    ("https://www.youtube.com/shorts/abcdefghijk", "video", "abcdefghijk"),
    # Video IDs
    ("dQw4w9WgXcQ", "video", "dQw4w9WgXcQ"),
    ("abcdefghijk", "video", "abcdefghijk"), # Short ID example
    # Playlist URLs
    ("https://www.youtube.com/playlist?list=PLXXXXXXXXXXXXXXXX", "playlist", "PLXXXXXXXXXXXXXXXX"),
    ("https://www.youtube.com/watch?v=somevideo&list=PLYYYYYYYYYYYYYYYY", "playlist", "PLYYYYYYYYYYYYYYYY"),
    # Playlist IDs
    ("PLXXXXXXXXXXXXXXXX", "playlist", "PLXXXXXXXXXXXXXXXX"),
    ("UUXXXXXXXXXXXXXXXX", "playlist", "UUXXXXXXXXXXXXXXXX"), # Uploads playlist
    ("FLXXXXXXXXXXXXXXXX", "playlist", "FLXXXXXXXXXXXXXXXX"), # Favorites playlist
    # Mixed cases
    ("youtu.be/dQw4w9WgXcQ?si=some_tracking", "video", "dQw4w9WgXcQ"),
    ("youtube.com/watch?v=dQw4w9WgXcQ&feature=share", "video", "dQw4w9WgXcQ"),
    # Channel URLs
    ("https://www.youtube.com/channel/UCXXXXXXXXXXXXXXXX", "channel", "UCXXXXXXXXXXXXXXXX"),
    ("https://www.youtube.com/c/ChannelName", "channel", "UCYYYYYYYYYYYYYYYY"),
    ("https://www.youtube.com/@ChannelHandle", "channel", "UCZZZZZZZZZZZZZZZZ"),
    # Channel IDs
    ("UCXXXXXXXXXXXXXXXX", "channel", "UCXXXXXXXXXXXXXXXX"),
])
def test_detect_content_type_valid(mock_yt_client_for_detect, input_str, expected_type, expected_id):
    """Test detection of valid YouTube URLs and IDs using YouTube API."""
    # Configure the API to return the expected type and ID
    mock_yt_client_for_detect.verify_input_type.return_value = (expected_type, expected_id)

    # Call the function with the mocked client
    content_type, content_id = detect_content_type(input_str, mock_yt_client_for_detect)

    # Assertions
    assert content_type == expected_type
    assert content_id == expected_id

    # Verify API was called for all inputs
    mock_yt_client_for_detect.verify_input_type.assert_called_once_with(input_str)


@pytest.mark.parametrize("input_str", [
    "invalid string",
    "https://example.com",
    "youtube.com/watch?v=", # Missing ID
    "PL", # Too short
    "UC", # Too short
    "just/some/path",
])
def test_detect_content_type_invalid(mock_yt_client_for_detect, input_str):
    """Test detection with invalid inputs using YouTube API."""
    # API should return None, None for invalid inputs
    mock_yt_client_for_detect.verify_input_type.return_value = (None, None)

    content_type, content_id = detect_content_type(input_str, mock_yt_client_for_detect)

    assert content_type is None
    assert content_id is None
    # Verify that the API was called
    mock_yt_client_for_detect.verify_input_type.assert_called_once_with(input_str)

def test_cli_process_video(runner, mock_clients, temp_output_dir):
    """Test processing a video via CLI."""
    mock_yt, mock_tr, mock_writer = mock_clients
    video_id = "dQw4w9WgXcQ"
    
    # Configure API verification to return video type
    mock_yt.verify_input_type.return_value = ("video", video_id)
    
    result = runner.invoke(cli, [
        'process', video_id,
        '--output-dir', str(temp_output_dir)
    ])

    assert result.exit_code == 0
    # Verify API verification was called
    mock_yt.verify_input_type.assert_called_once_with(video_id)
    # Verify subsequent calls use the canonical ID
    mock_yt.get_video_details.assert_called_once_with([video_id])
    mock_tr.get_transcript.assert_called_once_with(video_id)
    # Check that write_video_note was called with the correct arguments
    # The first argument is the video metadata dictionary
    # The second is the transcript string
    # The third is the output directory Path object
    mock_writer.write_video_note.assert_called_once()
    call_args, call_kwargs = mock_writer.write_video_note.call_args
    assert call_args[0]['id'] == 'test_vid_id' # Check based on mock_clients fixture
    assert call_args[1] == "Mock transcript content."
    assert call_args[2] == temp_output_dir


def test_cli_process_playlist(runner, mock_clients, temp_output_dir):
    """Test processing a playlist via CLI."""
    mock_yt, mock_tr, mock_writer = mock_clients
    playlist_id = "PLXXXXXXXXXXXXXXXX"
    # Configure API verification to return playlist type
    mock_yt.verify_input_type.return_value = ("playlist", playlist_id)
    
    # Mock playlist to return one video ID
    playlist_video_id = "pl_vid_1"
    mock_yt.get_videos_from_playlist.return_value = [{"contentDetails": {"videoId": playlist_video_id}, "snippet": {"title": "Playlist Video 1"}}]
    # Mock video details for the video found in the playlist
    mock_yt.get_video_details.return_value = [{"snippet": {"title": "Playlist Video 1 Details"}, "id": playlist_video_id}]

    result = runner.invoke(cli, [
        'process', playlist_id,
        '--output-dir', str(temp_output_dir)
    ])

    assert result.exit_code == 0
    # Verify API verification was called
    mock_yt.verify_input_type.assert_called_once_with(playlist_id)
    # Verify subsequent calls use the correct ID
    mock_yt.get_videos_from_playlist.assert_called_once_with(playlist_id)
    # process_playlist calls process_video internally, which calls get_video_details
    mock_yt.get_video_details.assert_called_once_with([playlist_video_id])
    mock_tr.get_transcript.assert_called_once_with(playlist_video_id)
    mock_writer.write_video_note.assert_called_once()
    call_args, call_kwargs = mock_writer.write_video_note.call_args
    assert call_args[0]['id'] == playlist_video_id
    assert call_args[1] == "Mock transcript content."
    assert call_args[2] == temp_output_dir


def test_cli_process_channel(runner, mock_clients, temp_output_dir):
    """Test processing a channel via CLI."""
    mock_yt, mock_tr, mock_writer = mock_clients
    channel_id_input = "UCXXXXXXXXXXXXXXXX" # This is the input to the CLI
    channel_id_canonical = "UCXXXXXXXXXXXXXXXX" # This is what detect_content_type should return

    # Configure API verification for this specific test case
    mock_yt.verify_input_type.return_value = ('channel', channel_id_canonical)

    playlist_id = "pl_id_1"
    playlist_video_id = "pl_vid_1"

    # Mock channel playlists
    mock_yt.get_channel_playlists.return_value = [{"id": playlist_id, "snippet": {"title": "Channel Playlist 1"}}]
    # Mock playlist videos
    mock_yt.get_videos_from_playlist.return_value = [{"contentDetails": {"videoId": playlist_video_id}, "snippet": {"title": "Playlist Video 1"}}]
    # Mock video details
    mock_yt.get_video_details.return_value = [{"snippet": {"title": "Playlist Video 1 Details"}, "id": playlist_video_id}]

    result = runner.invoke(cli, [
        'process', channel_id_input, # Use the input string for the CLI call
        '--output-dir', str(temp_output_dir)
    ])

    assert result.exit_code == 0
    # Verify API verification was called
    mock_yt.verify_input_type.assert_called_once_with(channel_id_input)
    # Verify subsequent calls use the canonical ID
    mock_yt.get_channel_playlists.assert_called_once_with(channel_id_canonical)
    mock_yt.get_videos_from_playlist.assert_called_once_with(playlist_id)
    mock_yt.get_video_details.assert_called_once_with([playlist_video_id])
    mock_tr.get_transcript.assert_called_once_with(playlist_video_id)
    mock_writer.write_video_note.assert_called_once()
    call_args, call_kwargs = mock_writer.write_video_note.call_args
    assert call_args[0]['id'] == playlist_video_id
    assert call_args[1] == "Mock transcript content."
    assert call_args[2] == temp_output_dir

def test_cli_process_overwrite(runner, mock_clients, temp_output_dir):
    """Test the --overwrite flag skips existing check."""
    mock_yt, mock_tr, mock_writer = mock_clients
    # Use a valid-looking 11-char ID
    video_id = "abc123def45"
    
    # Configure API verification to return video type
    mock_yt.verify_input_type.return_value = ("video", video_id)

    # Simulate an existing file by mocking get_existing_video_ids
    with patch('yt_obsidian.main.get_existing_video_ids') as mock_get_existing:
        mock_get_existing.return_value = {video_id} # Pretend this video exists

        # Run without overwrite (should skip)
        result_no_overwrite = runner.invoke(cli, [
            'process', video_id,
            '--output-dir', str(temp_output_dir)
        ])
        assert result_no_overwrite.exit_code == 0
        mock_yt.get_video_details.assert_not_called() # Should not fetch details if skipped
        mock_tr.get_transcript.assert_not_called()
        mock_writer.write_video_note.assert_not_called()

        # Reset mocks before the next run
        mock_yt.reset_mock()
        mock_tr.reset_mock()
        mock_writer.reset_mock()
        
        # Reconfigure API verification after reset
        mock_yt.verify_input_type.return_value = ("video", video_id)

        # Run with overwrite (should process)
        result_overwrite = runner.invoke(cli, [
            'process', video_id,
            '--output-dir', str(temp_output_dir),
            '--overwrite'
        ])
        assert result_overwrite.exit_code == 0
        mock_yt.get_video_details.assert_called_once_with([video_id])
        mock_tr.get_transcript.assert_called_once_with(video_id)
        mock_writer.write_video_note.assert_called_once()


def test_cli_process_max_depth(runner, mock_clients, temp_output_dir):
    """Test the --max-depth flag for channels."""
    mock_yt, mock_tr, mock_writer = mock_clients
    channel_id_input = "UCXXXXXXXXXXXXXXXX"
    channel_id_canonical = "UCXXXXXXXXXXXXXXXX"

    # Configure API verification
    mock_yt.verify_input_type.return_value = ('channel', channel_id_canonical)

    pl_id_1 = "pl_id_1"
    pl_id_2 = "pl_id_2"
    pl_vid_1 = "pl_vid_1" # Video in pl_id_1

    # Mock channel to return two playlists
    mock_yt.get_channel_playlists.return_value = [
        {"id": pl_id_1, "snippet": {"title": "Playlist 1"}},
        {"id": pl_id_2, "snippet": {"title": "Playlist 2"}}
    ]
    # Mock playlist 1 to return one video
    mock_yt.get_videos_from_playlist.side_effect = lambda pid: \
        [{"contentDetails": {"videoId": pl_vid_1}, "snippet": {"title": "Video 1"}}] if pid == pl_id_1 else []

    # Mock video details for the video in playlist 1
    mock_yt.get_video_details.return_value = [{"snippet": {"title": "Video 1 Details"}, "id": pl_vid_1}]


    # Run with max-depth=1
    result = runner.invoke(cli, [
        'process', channel_id_input,
        '--output-dir', str(temp_output_dir),
        '--max-depth', '1'
    ])

    assert result.exit_code == 0
    # Verify API verification was called
    mock_yt.verify_input_type.assert_called_once_with(channel_id_input)
    # Verify subsequent calls use the canonical ID
    mock_yt.get_channel_playlists.assert_called_once_with(channel_id_canonical)
    # Should only process the first playlist (pl_id_1)
    mock_yt.get_videos_from_playlist.assert_called_once_with(pl_id_1)
    mock_yt.get_video_details.assert_called_once_with([pl_vid_1])
    mock_tr.get_transcript.assert_called_once_with(pl_vid_1)
    mock_writer.write_video_note.assert_called_once()


def test_cli_process_dry_run(runner, mock_clients, temp_output_dir):
    """Test the --dry-run flag prevents processing."""
    mock_yt, mock_tr, mock_writer = mock_clients
    video_id = "dQw4w9WgXcQ"
    
    # Configure API verification to return video type
    mock_yt.verify_input_type.return_value = ("video", video_id)

    result = runner.invoke(cli, [
        'process', video_id,
        '--output-dir', str(temp_output_dir),
        '--dry-run'
    ])

    assert result.exit_code == 0
    # Ensure no processing functions were called
    mock_yt.get_video_details.assert_not_called()
    mock_tr.get_transcript.assert_not_called()
    mock_writer.write_video_note.assert_not_called()
    # Check for dry run output
    assert "--- Dry Run Plan ---" in result.output
    assert f"Detected Type: video" in result.output
    assert f"Detected ID: {video_id}" in result.output


def test_cli_process_verbose(runner, mock_clients, temp_output_dir):
    """Test the --verbose flag enables DEBUG logging."""
    mock_yt, mock_tr, mock_writer = mock_clients
    video_id = "dQw4w9WgXcQ"
    
    # Configure API verification to return video type
    mock_yt.verify_input_type.return_value = ("video", video_id)
    
    # We need to patch the logger used in main.py
    with patch('yt_obsidian.main.logger') as mock_logger:
        result = runner.invoke(cli, [
            'process', video_id,
            '--output-dir', str(temp_output_dir),
            '--verbose'
            # '-v' # Alternative short flag
        ])

        assert result.exit_code == 0
        # Check if the logger level was set to DEBUG
        # Note: Accessing the effective level might require patching logging.getLogger()
        # or checking if specific debug messages were logged.
        # A simpler check is if the debug message for enabling verbose logging was called.
        mock_logger.debug.assert_any_call("Verbose logging enabled.")
        # Check if other debug messages were logged during processing
        mock_logger.debug.assert_any_call(f"Fetching details for video: {video_id}")


def test_cli_process_invalid_input(runner, mock_clients, temp_output_dir, caplog):
    """Test CLI behavior with invalid input."""
    import logging
    caplog.set_level(logging.ERROR) # Capture ERROR level logs
    mock_yt, mock_tr, mock_writer = mock_clients # Unpack mock_clients here

    invalid_input = 'invalid-youtube-string'
    # Ensure API verification returns None for invalid input
    mock_yt.verify_input_type.return_value = (None, None)

    result = runner.invoke(cli, [
        'process', invalid_input,
        '--output-dir', str(temp_output_dir)
    ])
    assert result.exit_code != 0 # Should exit with an error code
    # Check the log output instead of stdout/stderr
    assert f"Could not determine content type or extract valid ID from input via API: {invalid_input}" in caplog.text
    
    # Verify API verification was called
    mock_yt.verify_input_type.assert_called_with(invalid_input)


def test_cli_process_output_dir_creation(runner, mock_clients, tmp_path):
    """Test that the output directory is created if it doesn't exist."""
    mock_yt, mock_tr, mock_writer = mock_clients
    video_id = "dQw4w9WgXcQ"
    non_existent_dir = tmp_path / "new_output_dir"
    
    # Configure API verification to return video type
    mock_yt.verify_input_type.return_value = ("video", video_id)

    assert not non_existent_dir.exists() # Ensure it doesn't exist initially

    result = runner.invoke(cli, [
        'process', video_id,
        '--output-dir', str(non_existent_dir)
    ])

    assert result.exit_code == 0
    assert non_existent_dir.exists() # Check if the directory was created
    assert non_existent_dir.is_dir()
    mock_writer.write_video_note.assert_called_once()
    call_args, call_kwargs = mock_writer.write_video_note.call_args
    assert call_args[2] == non_existent_dir # Check correct path passed to writer


def test_cli_process_default_output_dir(runner, mock_clients):
    """Test that the default output directory (settings.obsidian_vault_path) is used and properly converted to Path."""
    mock_yt, mock_tr, mock_writer = mock_clients
    video_id = "dQw4w9WgXcQ"
    
    # Configure API verification to return video type
    mock_yt.verify_input_type.return_value = ("video", video_id)

    # Patch settings to use a string path
    with patch('yt_obsidian.main.settings') as mock_settings:
        # Set obsidian_vault_path to a string
        mock_settings.obsidian_vault_path = "./test_vault"
        
        # Patch Path.exists and Path.mkdir to avoid filesystem operations
        with patch('pathlib.Path.exists', return_value=False), \
             patch('pathlib.Path.mkdir'):
            
            result = runner.invoke(cli, [
                'process', video_id
                # No --output-dir provided, should use settings.obsidian_vault_path
            ])
            
            assert result.exit_code == 0
            
            # Check that write_video_note was called with a Path object
            mock_writer.write_video_note.assert_called_once()
            call_args, call_kwargs = mock_writer.write_video_note.call_args
            
            # Verify the third argument (output_dir) is a Path object
            assert isinstance(call_args[2], Path)
            # Verify it has the correct path (Path normalizes the string)
            assert str(call_args[2]) == "test_vault"