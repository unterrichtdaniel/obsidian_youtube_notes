# YouTube to Obsidian Notes

A Python tool that automatically creates structured Obsidian notes from YouTube videos, including transcripts and AI-generated summaries.

## Features

- Fetch YouTube video metadata and transcripts
- Generate AI-powered summaries and key points
- Extract relevant keywords from transcripts for better searchability
- Create formatted Markdown notes compatible with Obsidian
- Configurable output structure and formatting
- YouTube API-based URL validation for reliable content detection

## Installation

1. Ensure you have Python 3.8+ and [Poetry](https://python-poetry.org/) installed
2. Clone this repository
3. Install dependencies:
```bash
poetry install
```

## Configuration

1. Copy the example environment configuration files:
```bash
cp .envrc.example .envrc
cp .env.example .env
```

2. Configure the environment variables in `.envrc` and `.env`. The files include examples for different AI services and required API keys:

### Required Configuration in `.env`

```bash
# Required for YouTube API access
YOUTUBE_API_KEY=your-youtube-api-key

# Path to your Obsidian vault
OBSIDIAN_VAULT_PATH=/path/to/your/obsidian/vault
```

### AI Service Configuration in `.envrc`

#### Using Local Ollama (Default)
```bash
export API_ENDPOINT="http://localhost:11434/v1"
export API_KEY=""  # No key needed for local Ollama
export MODEL="gemma:3b"  # Or any other model you have pulled
```

#### Using Google Gemini
```bash
export API_ENDPOINT="https://generativelanguage.googleapis.com/v1"
export API_KEY="your-gemini-api-key"
export MODEL="gemini-pro"
```

#### Using OpenAI
```bash
export API_ENDPOINT="https://api.openai.com/v1"
export API_KEY="your-openai-api-key"
export MODEL="gpt-3.5-turbo"
```

3. Allow direnv to load the environment:
```bash
direnv allow
```

## Usage

Before using the tool, activate the Poetry environment:

```bash
poetry shell
```

Use the `process` command to generate Obsidian notes from a YouTube URL or ID:

```bash
python -m yt_obsidian.main process <URL_or_ID> [OPTIONS]
```

**Options:**
- `--output-dir DIRECTORY`  
  Specify the directory where notes will be saved. Defaults to the `OBSIDIAN_VAULT_PATH` environment variable.
- `--overwrite`  
  Overwrite existing notes. By default, existing notes are skipped.
- `--max-depth INTEGER`  
  For channel processing, limit the number of playlists to process (0 = all playlists).
- `--dry-run`  
  Show the planned actions without fetching transcripts, calling the AI, or writing any files.
- `--verbose`, `-v`  
  Enable detailed (DEBUG) logging for troubleshooting.
- `--help`  
  Show the help message and exit.


### Examples

**Processing a Single Video:**
```bash
# Using URL
python -m yt_obsidian.main process "https://www.youtube.com/watch?v=dQw4w9WgXcQ"

# Using Video ID
python -m yt_obsidian.main process dQw4w9WgXcQ
```

**Processing a Playlist:**
```bash
# Using URL
python -m yt_obsidian.main process "https://www.youtube.com/playlist?list=PLrxxIuPUBEH3pMfkRMe3DxF-6OsMeJM4_"

# Using Playlist ID
python -m yt_obsidian.main process PLrxxIuPUBEH3pMfkRMe3DxF-6OsMeJM4_
```

**Processing a Channel:**
```bash
# Using URL
python -m yt_obsidian.main process "https://www.youtube.com/channel/UCXgNOWiX_xRl8EiN3HJMVAQ"

# Using Channel ID
python -m yt_obsidian.main process UCXgNOWiX_xRl8EiN3HJMVAQ"

# Using Channel Handle
python -m yt_obsidian.main process "https://www.youtube.com/@channelhandle"
```

### Command-Line Options

-   `<URL_or_ID>`: (Required) The URL or ID of the YouTube video, playlist, or channel to process.
-   `--output-dir DIRECTORY`: Specify the directory where Obsidian notes should be saved. Defaults to the value in `OBSIDIAN_VAULT_PATH`.
    ```bash
    python -m yt_obsidian.main process dQw4w9WgXcQ --output-dir ./my_notes
    ```
-   `--overwrite`: Allow overwriting existing note files. By default, the tool skips existing files.
    ```bash
    python -m yt_obsidian.main process dQw4w9WgXcQ --overwrite
    ```
-   `--max-depth INTEGER`: For channels, limit the number of playlists to process. Defaults to 0 (process all playlists).
    ```bash
    python -m yt_obsidian.main process UCXgNOWiX_xRl8EiN3HJMVAQ --max-depth 5
    ```
-   `--dry-run`: Simulate the process without fetching transcripts, calling AI, or writing any files. Useful for testing input and configuration.
    ```bash
    python -m yt_obsidian.main process dQw4w9WgXcQ --dry-run
    ```
-   `--verbose`: Enable detailed logging output for debugging.
    ```bash
    python -m yt_obsidian.main process dQw4w9WgXcQ --verbose
    ```
-   `--help`: Show the help message and exit.

### Supported YouTube URL Formats

This tool supports a wide range of YouTube URL formats for videos, playlists, and channels:

#### Video URL Formats
- Standard watch URLs: `https://www.youtube.com/watch?v=VIDEO_ID`
- Shortened URLs: `https://youtu.be/VIDEO_ID`
- Shortened URLs with parameters: `https://youtu.be/VIDEO_ID?si=TRACKING_ID&t=TIMESTAMP`
- Embedded player URLs: `https://www.youtube.com/embed/VIDEO_ID`
- YouTube Shorts: `https://www.youtube.com/shorts/VIDEO_ID`
- Mobile URLs: `https://m.youtube.com/watch?v=VIDEO_ID`
- Legacy v/ format: `https://www.youtube.com/v/VIDEO_ID`
- Web format: `https://www.youtube.com/web/VIDEO_ID`
- Simple video IDs (11 characters): `dQw4w9WgXcQ`

#### Playlist URL Formats
- Standard playlist URLs: `https://www.youtube.com/playlist?list=PLAYLIST_ID`
- Playlist in watch URLs: `https://www.youtube.com/watch?v=VIDEO_ID&list=PLAYLIST_ID`
- Simple playlist IDs (starts with PL): `PLrxxIuPUBEH3pMfkRMe3DxF-6OsMeJM4_`

#### Channel URL Formats
- Standard channel URLs: `https://www.youtube.com/channel/CHANNEL_ID`
- Custom name URLs: `https://www.youtube.com/c/CHANNEL_NAME`
- Channel handles: `https://www.youtube.com/@USERNAME`
- Simple channel IDs (starts with UC): `UCXgNOWiX_xRl8EiN3HJMVAQ`

The tool first attempts to parse the URL format directly and falls back to the YouTube API for verification if needed.

### Content Detection

The tool uses a combination of direct URL pattern matching and YouTube API verification to detect content types:

1. **Pattern Matching**: First attempts to identify video, playlist, or channel IDs directly from the URL structure
2. **API Verification**: Falls back to the YouTube API for verification if pattern matching is unsuccessful

This hybrid approach provides several benefits:
- More reliable detection of content types (videos, playlists, channels)
- Faster processing for standard URL formats without requiring API calls
- Robust handling of a wide range of YouTube URL variants
- Canonical ID resolution for consistent content processing

### Process Overview

When you run the tool, it will:
1. Detect the content type (video, playlist, channel) from the input URL/ID using pattern matching and/or the YouTube API.
2. Fetch relevant metadata and transcript(s).
3. Generate AI summaries and key points using your configured service (see Configuration section).
4. Extract relevant keywords from the transcript for improved searchability.
5. Create formatted Markdown notes in the specified output directory with frontmatter including metadata and keywords.
6. Link related notes (e.g., videos within a playlist).

## Project Structure

```
.
├── src/yt_obsidian/          # Main package directory
│   ├── clients/                    # API clients
│   │   ├── youtube_client.py       # YouTube API integration
│   │   ├── transcript_client.py    # Transcript handling
│   │   └── openai_compatible_client.py  # AI service integration
│   └── writers/                    # Output formatters
│       └── markdown_writer.py # Obsidian note generator
├── tests/                    # Test suite
└── vault/                    # Default output directory
```

## Development

Run tests:
```bash
poetry run pytest
```

## License

[License information to be added]