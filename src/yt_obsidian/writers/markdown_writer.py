import os
import yaml
from datetime import datetime
from typing import Dict, Optional, TYPE_CHECKING
from pathlib import Path # Added Path import

# Use TYPE_CHECKING to avoid circular imports
if TYPE_CHECKING:
    from ..container import CachedSession

from ..config import settings
from ..utils import slugify
from ..clients.openai_compatible_client import OpenAICompatibleClient, SummaryRequest

class MarkdownWriter:
    def __init__(self, session: Optional["CachedSession"] = None):
        """
        Initialize the markdown writer with an optional session.
        
        Args:
            session: Optional CachedSession for HTTP requests with retry and timeout handling
        """
        self.session = session

    # Added output_dir parameter and type hint
    def write_video_note(self, video_meta: Dict, transcript: str, output_dir: Path) -> str:
        """
        Generate a markdown note for a single video and save to the specified directory.
        Returns the filepath of the created note.
        """
        snippet = video_meta.get("snippet", {})
        title = snippet.get("title", "untitled")
        description = snippet.get("description", "")
        date_published = snippet.get("publishedAt", "")
        video_id = video_meta.get("contentDetails", {}).get("videoId")
        channel_title = snippet.get("channelTitle", settings.default_author)
        channel_id = snippet.get("channelId", "")
        tags = snippet.get("tags", [])
        category_id = snippet.get("categoryId", "")
        thumbnails = snippet.get("thumbnails", {})
        default_lang = snippet.get("defaultLanguage", "")
        default_audio_lang = snippet.get("defaultAudioLanguage", "")

        # Prepare frontmatter data
        metadata = {
            "title": f'"{title}"',  # Explicit quotes for YAML string
            "date": date_published if date_published else None,  # Keep as string to match test format
            "youtube_id": video_id,
            "channel": channel_title,
            "channel_id": channel_id,
            "url": f"https://youtu.be/{video_id}",
            "description": description,
        }
        if tags:
            metadata["tags"] = tags # Pass as list
        if category_id:
            metadata["category_id"] = category_id
        if thumbnails:
            thumb_url = thumbnails.get("default", {}).get("url")
            if thumb_url:
                metadata["thumbnail"] = thumb_url
        if default_lang:
            metadata["default_language"] = default_lang
        if default_audio_lang:
            metadata["default_audio_language"] = default_audio_lang
        
        # Dump metadata to YAML string using block style, no sorting
        yaml_frontmatter_str = yaml.dump(
            metadata,
            allow_unicode=True,
            sort_keys=False,
            default_flow_style=False,
            width=1000, # Prevent unwanted line wrapping
            default_style='', # Force unquoted style
            explicit_start=True,
            explicit_end=True,
            Dumper=yaml.SafeDumper
        )

        # Construct the final frontmatter block
        frontmatter_block = ["---", yaml_frontmatter_str.strip(), "---"]

        # Build content
        content = []
        content.extend(frontmatter_block)
        content.append(f"![Youtube Video](https://img.youtube.com/vi/{video_id}/0.jpg)")
        content.append(f"[Watch on YouTube](https://youtu.be/{video_id})\n")
        
        # Generate and add summary
        client = OpenAICompatibleClient(session=self.session)
        summary_request = SummaryRequest(transcript=transcript)
        summary = client.generate_summary(summary_request)
        content.append("## Summary\n")
        content.append(summary)
        content.append("\n")

        content.append("## Transcript\n")
        content.append(transcript or "*Transcript not available.*")

        # Write file
        slug = slugify(title)
        filename = f"{date_published[:10]}-{slug}.md"
        # Use the output_dir parameter instead of self.vault_path
        filepath = output_dir / filename # Use Path object directly
        # Ensure the directory exists (though main.py should handle this)
        output_dir.mkdir(parents=True, exist_ok=True)
        with open(filepath, "w", encoding="utf-8") as f:
            f.write("\n".join(content))

        return str(filepath) # Return as string for consistency maybe? Or keep as Path? Let's return str.
