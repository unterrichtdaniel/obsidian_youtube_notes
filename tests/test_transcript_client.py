import pytest
from yt_obsidian.clients.transcript_client import TranscriptClient

@pytest.fixture
def client():
    return TranscriptClient()

def test_transcript_success(monkeypatch, client):
    # Mock successful return from YouTubeTranscriptApi.get_transcript
    mock_segments = [{"text": "Hello", "start": 0}, {"text": "world", "start": 2}]

    def mock_get_transcript(video_id):
        assert video_id == "mock_video_id"
        return mock_segments

    monkeypatch.setattr("yt_obsidian.clients.transcript_client.YouTubeTranscriptApi.get_transcript", mock_get_transcript)

    transcript = client.get_transcript("mock_video_id")
    assert transcript == "[00:00] Hello\n[00:02] world"

def test_transcript_disabled(monkeypatch, client):
    from youtube_transcript_api import TranscriptsDisabled

    def mock_get_transcript(video_id):
        raise TranscriptsDisabled("No transcript")

    monkeypatch.setattr("yt_obsidian.clients.transcript_client.YouTubeTranscriptApi.get_transcript", mock_get_transcript)

    transcript = client.get_transcript("no_transcript_id")
    assert transcript == ""
