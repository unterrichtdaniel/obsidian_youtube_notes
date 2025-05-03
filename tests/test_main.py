# Add the project's src folder to sys.path so pytest can find yt_obsidian
import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../src")))

import pytest
from unittest.mock import Mock, patch
from yt_obsidian.main import get_existing_video_ids
from yt_obsidian.config import Settings

@pytest.fixture
def mock_env():
    env_vars = {
        'YOUTUBE_API_KEY': 'dummy-key-for-testing',
        'OBSIDIAN_VAULT_PATH': 'test/path',
        'API_ENDPOINT': 'http://localhost:11434/v1',
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
def mock_vault(tmp_path):
    """Create a temporary vault directory with test markdown files."""
    # Create test markdown files
    files = {
        "2023-04-23-test-video-1.md": """---
title: "Test Video 1"
youtube_id: "abc123"
---
Content 1""",
        "2023-04-23-test-video-2.md": """---
title: "Test Video 2"
youtube_id: "def456"
---
Content 2""",
        "invalid-frontmatter.md": """No frontmatter here""",
        "not-a-markdown.txt": "Not a markdown file"
    }
    
    vault_dir = tmp_path / "vault"
    vault_dir.mkdir()
    
    for filename, content in files.items():
        filepath = vault_dir / filename
        filepath.write_text(content, encoding='utf-8')
        
    return vault_dir

def test_get_existing_video_ids(mock_env, mock_vault):
    """Test extracting video IDs from existing markdown files."""
    video_ids = get_existing_video_ids(mock_vault) # Pass the mock_vault Path object

    assert len(video_ids) == 2
    assert "abc123" in video_ids
    assert "def456" in video_ids
