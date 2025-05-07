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
from ..clients.openai_compatible_client import OpenAICompatibleClient, SummaryRequest, KeywordsRequest
import logging

logger = logging.getLogger(__name__)

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
        
        # Initialize OpenAI client
        logger.info(f"Initializing OpenAICompatibleClient for video: {video_id}")
        client = OpenAICompatibleClient(session=self.session)
        
        # Generate and add keywords to frontmatter if transcript is available
        if transcript:
            try:
                logger.info(f"Generating keywords for video: {video_id}")
                logger.info(f"Transcript length: {len(transcript)} characters")
                # Use max_keywords from config
                keywords_request = KeywordsRequest(
                    transcript=transcript,
                    max_keywords=settings.max_keywords
                )
                keywords = client.generate_keywords(keywords_request)
                
                if keywords:
                    logger.info(f"Adding {len(keywords)} keywords to frontmatter")
                    # Add keywords to metadata if they don't already exist in tags
                    existing_tags = set(metadata.get("tags", []))
                    # Convert to lowercase for comparison
                    existing_tags_lower = {tag.lower() if isinstance(tag, str) else tag for tag in existing_tags}
                    
                    # Filter out keywords that already exist in tags (case-insensitive)
                    new_keywords = [kw for kw in keywords if kw.lower() not in existing_tags_lower]
                    
                    if new_keywords:
                        metadata["keywords"] = new_keywords
                        logger.debug(f"Added keywords to frontmatter: {new_keywords}")
                    else:
                        logger.debug("No new keywords to add (all already exist in tags)")
                else:
                    logger.warning("No keywords were generated")
            except Exception as e:
                logger.error(f"Failed to generate keywords: {str(e)}")
                logger.error(f"Error type: {type(e).__name__}")
                # Log the full exception traceback for better debugging
                import traceback
                logger.error(f"Traceback: {traceback.format_exc()}")
                # Continue without keywords rather than failing the whole process
        
        # Regenerate YAML frontmatter with updated metadata (including keywords)
        yaml_frontmatter_str = yaml.dump(
            metadata,
            allow_unicode=True,
            sort_keys=False,
            default_flow_style=False,
            width=1000,
            default_style='',
            explicit_start=True,
            explicit_end=True,
            Dumper=yaml.SafeDumper
        )
        
        # Reconstruct the frontmatter block with updated metadata
        frontmatter_block = ["---", yaml_frontmatter_str.strip(), "---"]
        
        # Rebuild content with updated frontmatter
        content = []
        content.extend(frontmatter_block)
        content.append(f"![Youtube Video](https://img.youtube.com/vi/{video_id}/0.jpg)")
        content.append(f"[Watch on YouTube](https://youtu.be/{video_id})\n")
        
        # Generate and add summary
        logger.info(f"Generating summary for video: {video_id}")
        logger.info(f"Transcript length for summary: {len(transcript)} characters")
        summary_request = SummaryRequest(transcript=transcript)
        try:
            summary = client.generate_summary(summary_request)
            logger.info(f"Summary generation successful, length: {len(summary)} characters")
        except Exception as e:
            logger.error(f"Failed to generate summary: {str(e)}")
            logger.error(f"Error type: {type(e).__name__}")
            import traceback
            logger.error(f"Traceback: {traceback.format_exc()}")
            summary = "*Error generating summary. Please check the logs for details.*"
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
