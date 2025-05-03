import pytest
from unittest.mock import MagicMock, patch
from yt_obsidian.clients.youtube_client import YouTubeClient


@pytest.fixture
def youtube_client():
    return YouTubeClient(api_key="fake")


def test_get_videos_from_playlist(youtube_client):
    mock_response = {
        "items": [
            {"snippet": {"title": "Video 1"}, "contentDetails": {"videoId": "vid1"}},
            {"snippet": {"title": "Video 2"}, "contentDetails": {"videoId": "vid2"}},
        ],
        "nextPageToken": None,
    }

    # Patch the playlistItems().list().execute() chain
    with patch.object(youtube_client.youtube, "playlistItems") as mock_playlist_items:
        mock_playlist_items.return_value.list.return_value.execute.return_value = mock_response

        videos = youtube_client.get_videos_from_playlist("mock_playlist_id")

        assert len(videos) == 2
        assert videos[0]["snippet"]["title"] == "Video 1"
        assert videos[1]["snippet"]["title"] == "Video 2"


def test_get_channel_playlists(youtube_client):
    mock_response = {
        "items": [
            {"snippet": {"title": "Playlist 1"}},
            {"snippet": {"title": "Playlist 2"}},
        ],
        "nextPageToken": None,
    }

    # Patch the playlists().list().execute() chain
    with patch.object(youtube_client.youtube, "playlists") as mock_playlists:
        mock_playlists.return_value.list.return_value.execute.return_value = mock_response

        playlists = youtube_client.get_channel_playlists("mock_channel_id")

        assert len(playlists) == 2
        assert playlists[0]["snippet"]["title"] == "Playlist 1"
        assert playlists[1]["snippet"]["title"] == "Playlist 2"
def test_get_video_details_single_batch(youtube_client):
    """Test fetching details for a small number of videos (single API call)."""
    video_ids = ["vid1", "vid2"]
    mock_response = {
        "items": [
            {"id": "vid1", "snippet": {"title": "Video 1 Details"}, "statistics": {"viewCount": "100"}},
            {"id": "vid2", "snippet": {"title": "Video 2 Details"}, "statistics": {"viewCount": "200"}},
        ]
    }
    # Patch the videos().list().execute() chain
    with patch.object(youtube_client.youtube, "videos") as mock_videos:
        mock_videos.return_value.list.return_value.execute.return_value = mock_response

        details = youtube_client.get_video_details(video_ids)

        assert len(details) == 2
        assert details[0]["id"] == "vid1"
        assert details[1]["id"] == "vid2"
        assert "statistics" in details[0] # Check if statistics are included
        mock_videos.return_value.list.assert_called_once_with(
            part="snippet,contentDetails,statistics",
            id="vid1,vid2"
        )

def test_get_video_details_multiple_batches(youtube_client):
    """Test fetching details for many videos, requiring multiple API calls."""
    video_ids = [f"vid{i}" for i in range(55)] # More than 50 IDs
    mock_response_batch1 = {
        "items": [{"id": f"vid{i}", "snippet": {"title": f"Video {i}"}, "statistics": {}} for i in range(50)]
    }
    mock_response_batch2 = {
        "items": [{"id": f"vid{i}", "snippet": {"title": f"Video {i}"}, "statistics": {}} for i in range(50, 55)]
    }

    # Patch the videos().list().execute() chain to return different responses based on call
    with patch.object(youtube_client.youtube, "videos") as mock_videos:
        # Configure the mock execute to return different values on subsequent calls
        mock_execute = MagicMock()
        mock_execute.side_effect = [mock_response_batch1, mock_response_batch2]
        mock_videos.return_value.list.return_value.execute = mock_execute

        details = youtube_client.get_video_details(video_ids)

        assert len(details) == 55
        assert details[0]["id"] == "vid0"
        assert details[54]["id"] == "vid54"
        # Check that list was called twice
        assert mock_videos.return_value.list.call_count == 2
        # Check the arguments of the calls using .kwargs
        first_call_kwargs = mock_videos.return_value.list.call_args_list[0].kwargs
        second_call_kwargs = mock_videos.return_value.list.call_args_list[1].kwargs
        assert first_call_kwargs.get('id') == ",".join(video_ids[:50])
        assert second_call_kwargs.get('id') == ",".join(video_ids[50:])


def test_get_video_details_api_error(youtube_client, caplog):
    """Test handling of API errors during video detail fetching."""
    video_ids = ["vid1", "vid2"]
    error_message = "API quota exceeded"

    # Patch the videos().list().execute() chain to raise an exception
    with patch.object(youtube_client.youtube, "videos") as mock_videos:
        mock_videos.return_value.list.return_value.execute.side_effect = Exception(error_message)

        # Capture logging output
        import logging
        caplog.set_level(logging.ERROR)

        details = youtube_client.get_video_details(video_ids)

        # Should return an empty list or partial results depending on implementation
        # Current implementation logs error and returns empty list for the failed batch
        assert len(details) == 0
        # Check that the error was logged
        assert f"Failed to fetch details for video IDs {video_ids}" in caplog.text
        assert error_message in caplog.text


def test_get_videos_from_playlist_pagination(youtube_client):
    """Test fetching playlist videos with pagination."""
    mock_response_page1 = {
        "items": [{"snippet": {"title": "Video 1"}, "contentDetails": {"videoId": "vid1"}}],
        "nextPageToken": "page2_token",
    }
    mock_response_page2 = {
        "items": [{"snippet": {"title": "Video 2"}, "contentDetails": {"videoId": "vid2"}}],
        "nextPageToken": None, # Last page
    }

    # Patch the playlistItems().list().execute() chain
    with patch.object(youtube_client.youtube, "playlistItems") as mock_playlist_items:
        # Configure the mock execute to return different values
        mock_execute = MagicMock()
        mock_execute.side_effect = [mock_response_page1, mock_response_page2]
        mock_playlist_items.return_value.list.return_value.execute = mock_execute

        videos = youtube_client.get_videos_from_playlist("mock_playlist_id")

        assert len(videos) == 2
        assert videos[0]["contentDetails"]["videoId"] == "vid1"
        assert videos[1]["contentDetails"]["videoId"] == "vid2"
        # Check that list was called twice
        assert mock_playlist_items.return_value.list.call_count == 2
        # Check pageToken arguments
        first_call_kwargs = mock_playlist_items.return_value.list.call_args_list[0].kwargs
        second_call_kwargs = mock_playlist_items.return_value.list.call_args_list[1].kwargs
        assert first_call_kwargs.get("pageToken") is None
        assert second_call_kwargs.get("pageToken") == "page2_token"


def test_get_channel_playlists_pagination(youtube_client):
    """Test fetching channel playlists with pagination."""
    mock_response_page1 = {
        "items": [{"snippet": {"title": "Playlist 1"}}],
        "nextPageToken": "page2_token",
    }
    mock_response_page2 = {
        "items": [{"snippet": {"title": "Playlist 2"}}],
        "nextPageToken": None, # Last page
    }

    # Patch the playlists().list().execute() chain
    with patch.object(youtube_client.youtube, "playlists") as mock_playlists:
        # Configure the mock execute
        mock_execute = MagicMock()
        mock_execute.side_effect = [mock_response_page1, mock_response_page2]
        mock_playlists.return_value.list.return_value.execute = mock_execute

        playlists = youtube_client.get_channel_playlists("mock_channel_id")

        assert len(playlists) == 2
        assert playlists[0]["snippet"]["title"] == "Playlist 1"
        assert playlists[1]["snippet"]["title"] == "Playlist 2"
        # Check that list was called twice
        assert mock_playlists.return_value.list.call_count == 2
        # Check pageToken arguments
        first_call_kwargs = mock_playlists.return_value.list.call_args_list[0].kwargs
        second_call_kwargs = mock_playlists.return_value.list.call_args_list[1].kwargs
        assert first_call_kwargs.get("pageToken") is None
        assert second_call_kwargs.get("pageToken") == "page2_token"

# New tests for verify_input_type method
def test_verify_input_type_video(youtube_client):
    """Test verifying a video URL/ID using the YouTube API."""
    mock_response = {
        "items": [
            {
                "id": {
                    "kind": "youtube#video",
                    "videoId": "dQw4w9WgXcQ"
                }
            }
        ]
    }
    
    with patch.object(youtube_client.youtube, "search") as mock_search:
        mock_search.return_value.list.return_value.execute.return_value = mock_response
        
        # Test with video ID
        content_type, content_id = youtube_client.verify_input_type("dQw4w9WgXcQ")
        
        assert content_type == "video"
        assert content_id == "dQw4w9WgXcQ"
        mock_search.return_value.list.assert_called_with(
            q="dQw4w9WgXcQ",
            part="id",
            maxResults=1,
            type="video,playlist,channel"
        )

def test_verify_input_type_playlist(youtube_client):
    """Test verifying a playlist URL/ID using the YouTube API."""
    mock_response = {
        "items": [
            {
                "id": {
                    "kind": "youtube#playlist",
                    "playlistId": "PLlaN88a7y2_plecYoJxvRFTLHVbIVAOoS"
                }
            }
        ]
    }
    
    with patch.object(youtube_client.youtube, "search") as mock_search:
        mock_search.return_value.list.return_value.execute.return_value = mock_response
        
        # Test with playlist URL
        content_type, content_id = youtube_client.verify_input_type("https://www.youtube.com/playlist?list=PLlaN88a7y2_plecYoJxvRFTLHVbIVAOoS")
        
        assert content_type == "playlist"
        assert content_id == "PLlaN88a7y2_plecYoJxvRFTLHVbIVAOoS"

def test_verify_input_type_channel(youtube_client):
    """Test verifying a channel URL/ID using the YouTube API."""
    mock_response = {
        "items": [
            {
                "id": {
                    "kind": "youtube#channel",
                    "channelId": "UC_x5XG1OV2P6uZZ5FSM9Ttw"
                }
            }
        ]
    }
    
    with patch.object(youtube_client.youtube, "search") as mock_search:
        mock_search.return_value.list.return_value.execute.return_value = mock_response
        
        # Test with channel URL
        content_type, content_id = youtube_client.verify_input_type("https://www.youtube.com/channel/UC_x5XG1OV2P6uZZ5FSM9Ttw")
        
        assert content_type == "channel"
        assert content_id == "UC_x5XG1OV2P6uZZ5FSM9Ttw"

def test_verify_input_type_no_results(youtube_client, caplog):
    """Test verifying an invalid input that returns no search results."""
    mock_response = {
        "items": []
    }
    
    with patch.object(youtube_client.youtube, "search") as mock_search:
        mock_search.return_value.list.return_value.execute.return_value = mock_response
        
        # Capture logging output
        import logging
        caplog.set_level(logging.DEBUG)
        
        content_type, content_id = youtube_client.verify_input_type("invalid_input_that_returns_no_results")
        
        assert content_type is None
        assert content_id is None
        assert "API search returned no results" in caplog.text

def test_verify_input_type_api_error(youtube_client, caplog):
    """Test handling API errors during verification."""
    error_message = "API quota exceeded"
    
    with patch.object(youtube_client.youtube, "search") as mock_search:
        mock_search.return_value.list.return_value.execute.side_effect = Exception(error_message)
        
        # Capture logging output
        import logging
        caplog.set_level(logging.ERROR)
        
        content_type, content_id = youtube_client.verify_input_type("some_input")
        
        assert content_type is None
        assert content_id is None
        assert "API error during verification" in caplog.text
        assert error_message in caplog.text

def test_verify_input_type_unknown_kind(youtube_client, caplog):
    """Test handling unknown kind in API response."""
    mock_response = {
        "items": [
            {
                "id": {
                    "kind": "youtube#unknown",
                    "unknownId": "12345"
                }
            }
        ]
    }
    
    with patch.object(youtube_client.youtube, "search") as mock_search:
        mock_search.return_value.list.return_value.execute.return_value = mock_response
        
        # Capture logging output
        import logging
        caplog.set_level(logging.WARNING)
        
        content_type, content_id = youtube_client.verify_input_type("some_input")
        
        assert content_type is None
        assert content_id is None
        assert "API search returned unknown kind" in caplog.text