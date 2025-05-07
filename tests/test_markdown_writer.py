 # Add the project's src folder to sys.path so pytest can find yt_obsidian
import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../src")))
# tests/test_markdown_writer.py

import os
import pytest
from unittest.mock import Mock, patch
from yt_obsidian.writers.markdown_writer import MarkdownWriter
from yt_obsidian.clients.openai_compatible_client import OpenAICompatibleClient
from yt_obsidian.config import Settings


@pytest.fixture
def mock_env():
    env_vars = {
        'YOUTUBE_API_KEY': 'dummy-key-for-testing',
        'OBSIDIAN_VAULT_PATH': 'test/path',
        'API_ENDPOINT': 'http://localhost:11434/v1',
        'API_KEY': '',
        'MODEL': 'test-model',
        'TEST_MODEL': 'test-model',
        'MAX_RETRIES': '3',
        'INITIAL_RETRY_DELAY': '1.0',
        'MAX_RETRY_DELAY': '60.0',
        'RETRY_EXPONENTIAL_BASE': '2.0'
    }
    with patch.dict(os.environ, env_vars, clear=True):
        yield env_vars

@pytest.fixture
def video_meta():
    return {
        "snippet": {
            "title": "Test Video",
            "description": "This is a description.",
            "publishedAt": "2025-04-29T12:34:56Z",
            "channelTitle": "Test Channel",
            "channelId": "UC12345",
            "tags": ["test", "video", "metadata"],
            "categoryId": "27",
            "thumbnails": {
                "default": {"url": "https://img.youtube.com/vi/abc123/default.jpg"}
            },
            "defaultLanguage": "en",
            "defaultAudioLanguage": "en"
        },
        "contentDetails": {
            "videoId": "abc123"
        }
    }

@pytest.fixture
def transcript():
    return "This is a test transcript."

def test_write_video_note_creates_file(mock_env, tmp_path, video_meta, transcript):
    # 1. Prepare a temporary vault directory
    vault = tmp_path / "vault"
    vault.mkdir()

    # 2. Instantiate the writer (no vault_path needed at init)
    writer = MarkdownWriter()

    # Mock summary and keywords generation
    with patch('yt_obsidian.writers.markdown_writer.OpenAICompatibleClient') as mock_client:
        mock_instance = mock_client.return_value
        mock_instance.generate_summary.return_value = "Test summary content"
        mock_instance.generate_keywords.return_value = ["keyword1", "keyword2", "advanced topic"]

        # 3. Invoke the method under test, passing the output directory
        filepath = writer.write_video_note(video_meta, transcript, vault) # Pass vault as output_dir

    # 4. Assert file was created
    assert os.path.isfile(filepath), f"Expected file at {filepath}"

    # 5. Read its contents and check for key frontmatter and transcript
    with open(filepath, encoding="utf-8") as f:
        content = f.read()

    # Check for frontmatter fields
    assert 'title: \'"Test Video"\'' in content
    assert "date: '2025-04-29T12:34:56Z'" in content
    assert "youtube_id: abc123" in content
    assert "channel: Test Channel" in content
    assert "channel_id: UC12345" in content
    assert "url: https://youtu.be/abc123" in content
    assert "description: This is a description." in content
    assert "tags:" in content and "- test" in content and "- video" in content and "- metadata" in content
    assert "category_id: '27'" in content
    assert "thumbnail: https://img.youtube.com/vi/abc123/default.jpg" in content
    assert "default_language: en" in content
    assert "default_audio_language: en" in content
    
    # Check for keywords section in frontmatter
    assert "keywords:" in content
    assert "- keyword1" in content
    assert "- keyword2" in content
    assert "- advanced topic" in content

    # Check for transcript section
    # Check for summary section
    assert "## Summary" in content
    assert "Test summary content" in content
    
    # Check for transcript section
    assert "## Transcript" in content
    assert "This is a test transcript." in content
    
def test_write_video_note_with_existing_tags(mock_env, tmp_path, video_meta, transcript):
    # 1. Prepare a temporary vault directory
    vault = tmp_path / "vault"
    vault.mkdir()

    # 2. Instantiate the writer
    writer = MarkdownWriter()
    
    # Set up mock keywords that overlap with existing tags
    with patch('yt_obsidian.writers.markdown_writer.OpenAICompatibleClient') as mock_client:
        mock_instance = mock_client.return_value
        mock_instance.generate_summary.return_value = "Test summary content"
        # Return some keywords that overlap with existing tags (case differences to test case insensitivity)
        mock_instance.generate_keywords.return_value = ["TEST", "Video", "keyword1", "keyword2"]

        # 3. Invoke the method under test
        filepath = writer.write_video_note(video_meta, transcript, vault)

    # 4. Read its contents and check for frontmatter
    with open(filepath, encoding="utf-8") as f:
        content = f.read()

    # Check that existing tags are preserved
    assert "tags:" in content
    assert "- test" in content
    assert "- video" in content
    assert "- metadata" in content
    
    # Check that only new keywords are added (not duplicates of existing tags)
    assert "keywords:" in content
    assert "- keyword1" in content
    assert "- keyword2" in content
    # TEST and Video should not be in keywords as they're already in tags (case-insensitive)
    assert "- TEST" not in content
    assert "- Video" not in content
    
def test_write_video_note_keywords_error_handling(mock_env, tmp_path, video_meta, transcript):
    # 1. Prepare a temporary vault directory
    vault = tmp_path / "vault"
    vault.mkdir()

    # 2. Instantiate the writer
    writer = MarkdownWriter()
    
    # Set up mock to simulate error in keyword generation
    with patch('yt_obsidian.writers.markdown_writer.OpenAICompatibleClient') as mock_client:
        mock_instance = mock_client.return_value
        mock_instance.generate_summary.return_value = "Test summary content"
        # Simulate an error in keyword generation
        mock_instance.generate_keywords.side_effect = Exception("Keyword generation failed")

        # 3. Invoke the method under test - should not raise exception
        filepath = writer.write_video_note(video_meta, transcript, vault)

    # 4. Read its contents and check that the file was created successfully
    with open(filepath, encoding="utf-8") as f:
        content = f.read()

    # Verify the file was created with summary and transcript but no keywords
    assert "## Summary" in content
    assert "Test summary content" in content
    assert "## Transcript" in content
    assert "This is a test transcript." in content
    # Keywords should not be in the frontmatter
    assert "keywords:" not in content