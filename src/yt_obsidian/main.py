import logging
import sys
import click
import os
import yaml
from pathlib import Path
from typing import Dict, Set, Tuple, Optional

from .clients.youtube_client import YouTubeClient
from .clients.transcript_client import TranscriptClient
from .writers.markdown_writer import MarkdownWriter
from .config import settings

# --- Logging Configuration ---
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger(__name__)


# --- Helper Functions ---

def detect_content_type(input_str: str, yt_client: YouTubeClient) -> Tuple[Optional[str], Optional[str]]:
    """
    Detects YouTube content type and extracts ID using YouTube API verification.
    """
    logger.debug(f"Attempting to detect content type for: '{input_str}' using API verification.")

    # Use the YouTube API to verify the input string and get the canonical type and ID
    content_type, content_id = yt_client.verify_input_type(input_str)

    if content_type and content_id:
        logger.info(f"API verification successful for '{input_str}': Type={content_type}, ID={content_id}")
        return content_type, content_id
    else:
        logger.error(f"Could not determine content type or extract valid ID from input via API: {input_str}")
        return None, None


def get_existing_video_ids(output_dir: Path) -> Set[str]:
    """Get set of video IDs from existing markdown files in the specified directory."""
    video_ids = set()
    if not output_dir.exists():
        logger.warning(f"Output directory not found: {output_dir}. No existing videos detected.")
        return video_ids
    if not output_dir.is_dir():
        logger.error(f"Output path is not a directory: {output_dir}")
        return video_ids # Or raise error?

    logger.info(f"Scanning for existing notes in: {output_dir}")
    for filename in os.listdir(output_dir):
        if not filename.endswith('.md'):
            continue

        filepath = output_dir / filename
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                content = f.read()
                if content.startswith('---'):
                    _, frontmatter, _ = content.split('---', 2)
                    metadata = yaml.safe_load(frontmatter)
                    if 'youtube_id' in metadata:
                        video_ids.add(metadata['youtube_id'])
        except Exception as e:
            logger.warning(f"Error reading {filename}: {e}")
            
    logger.info(f"Found {len(video_ids)} existing video notes in {output_dir}")
    return video_ids

# --- Processing Functions ---

def process_video(video_id: str, writer: MarkdownWriter, yt: YouTubeClient, tr: TranscriptClient, output_dir: Path, overwrite: bool):
    """Fetches details & transcript for a video and writes a note."""
    logger.info(f"Processing video: {video_id}")
    # Check if exists (unless overwrite)
    # Optimization: Could pass existing_ids set down if processing many videos
    existing_ids = get_existing_video_ids(output_dir)
    if not overwrite and video_id in existing_ids:
        logger.info(f"Skipping existing video note: {video_id}")
        return

    try:
        logger.debug(f"Fetching details for video: {video_id}")
        video_details_list = yt.get_video_details([video_id])
        if not video_details_list:
             logger.error(f"Could not fetch details for video: {video_id}. Skipping.")
             return
        # The API returns a list, even for one ID. Get the first item.
        # Ensure the item has the expected structure before proceeding.
        video_meta = video_details_list[0]
        if not isinstance(video_meta, dict) or "snippet" not in video_meta:
             logger.error(f"Received unexpected video details format for {video_id}. Skipping.")
             return

        logger.debug(f"Fetching transcript for video: {video_id}")
        # Handle potential transcript errors gracefully
        transcript = None
        try:
            transcript = tr.get_transcript(video_id)
            if transcript:
                logger.debug(f"Transcript fetched successfully for {video_id}.")
            else:
                logger.info(f"No transcript available for video {video_id}.")
                transcript = "" # Use empty string if transcript is None or empty
        except Exception as transcript_error:
            # Log specific transcript errors but continue to write note without it
            logger.warning(f"Could not fetch transcript for video {video_id}: {transcript_error}. Proceeding without transcript.")
            transcript = "" # Use empty string on error

        logger.debug(f"Writing note for video: {video_id}")
        # Pass the actual video metadata dict
        path = writer.write_video_note(video_meta, transcript, output_dir)
        logger.info(f"Successfully wrote note: {path}")

    except Exception as e:
        # Log the specific error for this video but allow loop (if any) to continue
        logger.error(f"Failed to process video {video_id}: {e}", exc_info=logging.getLogger().level == logging.DEBUG)


def process_playlist(playlist_id: str, writer: MarkdownWriter, yt: YouTubeClient, tr: TranscriptClient, output_dir: Path, overwrite: bool):
    """Fetches videos from a playlist, filters, and processes them."""
    logger.info(f"Processing playlist: {playlist_id}")
    try:
        logger.debug(f"Fetching videos for playlist: {playlist_id}")
        all_videos_items = yt.get_videos_from_playlist(playlist_id) # These are playlistItems
        logger.info(f"Found {len(all_videos_items)} total video items in playlist {playlist_id}")

        if not all_videos_items:
            logger.info(f"Playlist {playlist_id} is empty or videos could not be fetched.")
            return

        # Extract video IDs, ensuring they exist
        video_ids_in_playlist = []
        for item in all_videos_items:
            vid = item.get("contentDetails", {}).get("videoId")
            if vid:
                video_ids_in_playlist.append(vid)
            else:
                logger.warning(f"Skipping item in playlist {playlist_id} due to missing videoId: {item.get('id')}")
        logger.debug(f"Extracted {len(video_ids_in_playlist)} valid video IDs from playlist items.")

        if not video_ids_in_playlist:
             logger.info(f"No valid video IDs found in playlist {playlist_id}.")
             return

        existing_ids = get_existing_video_ids(output_dir)
        videos_to_process_ids = []
        if overwrite:
            videos_to_process_ids = video_ids_in_playlist
            logger.info(f"Overwrite enabled, processing all {len(videos_to_process_ids)} videos in playlist {playlist_id}.")
        else:
            videos_to_process_ids = [
                vid for vid in video_ids_in_playlist if vid not in existing_ids
            ]
            skipped_count = len(video_ids_in_playlist) - len(videos_to_process_ids)
            if skipped_count > 0:
                logger.info(f"Skipping {skipped_count} existing video notes.")
            logger.info(f"Found {len(videos_to_process_ids)} new videos to process in playlist {playlist_id}")

        if not videos_to_process_ids:
            logger.info(f"No new videos to process for playlist {playlist_id}.")
            return

        # Process the filtered video IDs individually
        processed_count = 0
        total_to_process = len(videos_to_process_ids)
        for i, vid in enumerate(videos_to_process_ids):
             logger.info(f"Processing video {i+1}/{total_to_process} from playlist {playlist_id}: {vid}")
             # Pass overwrite=True because we've already filtered based on the flag
             # Individual video errors are logged within process_video
             process_video(vid, writer, yt, tr, output_dir, overwrite=True)
             processed_count += 1

        logger.info(f"Finished processing playlist {playlist_id}. Attempted to process {processed_count} videos.")

    except Exception as e:
        # Log error for the playlist processing itself
        logger.error(f"Failed to process playlist {playlist_id}: {e}", exc_info=logging.getLogger().level == logging.DEBUG)


def process_channel(channel_id: str, writer: MarkdownWriter, yt: YouTubeClient, tr: TranscriptClient, output_dir: Path, overwrite: bool, max_depth: int):
    """Fetches playlists from a channel and delegates processing."""
    logger.info(f"Processing channel: {channel_id} (max depth: {max_depth if max_depth > 0 else 'all'})")
    try:
        logger.debug(f"Fetching playlists for channel: {channel_id}")
        playlists = yt.get_channel_playlists(channel_id)
        logger.info(f"Found {len(playlists)} playlists for channel {channel_id}")

        if not playlists:
            logger.warning(f"No playlists found for channel {channel_id}. Nothing to process.")
            return

        # Apply max_depth limit (0 means no limit)
        playlists_to_process = playlists[:max_depth] if max_depth > 0 else playlists
        if max_depth > 0 and len(playlists) > max_depth:
             logger.info(f"Processing the first {len(playlists_to_process)} playlists based on max_depth={max_depth}")
        else:
             logger.info(f"Processing all {len(playlists_to_process)} found playlists.")

        processed_pl_count = 0
        total_pl_to_process = len(playlists_to_process)
        for i, pl in enumerate(playlists_to_process):
            pl_id = pl.get("id")
            pl_title = pl.get("snippet", {}).get("title", "Untitled Playlist")
            if pl_id:
                logger.info(f"--- Processing Playlist {i+1}/{total_pl_to_process}: '{pl_title}' ({pl_id}) ---")
                # Individual playlist errors are logged within process_playlist
                process_playlist(pl_id, writer, yt, tr, output_dir, overwrite)
                processed_pl_count += 1
            else:
                 logger.warning(f"Skipping playlist with missing ID in channel {channel_id}: '{pl_title}'")

        logger.info(f"Finished processing channel {channel_id}. Attempted to process {processed_pl_count} playlists.")

    except Exception as e:
        # Log error for the channel processing itself
        logger.error(f"Failed to process channel {channel_id}: {e}", exc_info=logging.getLogger().level == logging.DEBUG)


# --- CLI Definition ---

@click.group()
def cli():
    """
    Generate Obsidian markdown notes from YouTube videos, playlists, or channels.
    """
    pass

@cli.command()
@click.argument('input_str', metavar='INPUT')
@click.option('--output-dir', type=click.Path(file_okay=False, dir_okay=True, writable=True, resolve_path=True),
              help=f"Directory to save notes. [Default: {settings.obsidian_vault_path}]")
@click.option('--overwrite', is_flag=True, default=False, help="Regenerate notes even if they already exist.")
@click.option('--max-depth', type=int, default=0, help="Max number of playlists to process per channel (0 for all).")
@click.option('--dry-run', is_flag=True, default=False, help="Detect content and plan actions without writing files.")
@click.option('--verbose', '-v', is_flag=True, default=False, help="Enable detailed (DEBUG) logging.")
def process(input_str: str, output_dir: Optional[str], overwrite: bool, max_depth: int, dry_run: bool, verbose: bool):
    """
    Processes a YouTube video, playlist, or channel URL/ID.

    INPUT: Can be a URL or just the ID for a video, playlist, or channel.
           The tool will attempt to automatically detect the type.
    """
    if verbose:
        logging.getLogger().setLevel(logging.DEBUG)
        logger.debug("Verbose logging enabled.")

    # Determine output directory
    target_output_dir = Path(output_dir if output_dir else settings.obsidian_vault_path)
    logger.info(f"Using output directory: {target_output_dir}")
    if not target_output_dir.exists():
        logger.info(f"Creating output directory: {target_output_dir}")
        try:
            target_output_dir.mkdir(parents=True, exist_ok=True)
        except OSError as e:
            logger.error(f"Failed to create output directory {target_output_dir}: {e}")
            sys.exit(1)


    # --- Initialization ---
    try:
        yt = YouTubeClient(settings.youtube_api_key)
        tr = TranscriptClient()
        # Pass target_output_dir to writer if it needs it, or handle path construction later
        writer = MarkdownWriter() # Assuming writer doesn't need output_dir at init
    except Exception as e:
        logger.error(f"Failed to initialize clients: {e}")
        sys.exit(1)


    # --- Content Detection and Routing ---
    # Pass the initialized YouTube client to the detection function
    content_type, content_id = detect_content_type(input_str, yt)

    if not content_type or not content_id:
        # Error message now comes from detect_content_type if API also fails
        sys.exit(1)

    logger.info(f"Detected type: {content_type}, ID: {content_id}")

    if dry_run:
        logger.info("Dry run enabled. Skipping actual processing.")
        print(f"--- Dry Run Plan ---")
        print(f"Input: {input_str}")
        print(f"Detected Type: {content_type}")
        print(f"Detected ID: {content_id}")
        print(f"Output Directory: {target_output_dir}")
        print(f"Overwrite: {overwrite}")
        print(f"Max Depth (for channels): {max_depth}")
        print(f"--------------------")
        sys.exit(0)

    # --- Processing ---
    try:
        if content_type == "video":
            process_video(content_id, writer, yt, tr, target_output_dir, overwrite)
        elif content_type == "playlist":
            process_playlist(content_id, writer, yt, tr, target_output_dir, overwrite)
        elif content_type == "channel":
            process_channel(content_id, writer, yt, tr, target_output_dir, overwrite, max_depth)
        else:
            # This case should ideally be caught earlier
            logger.error(f"Unsupported content type '{content_type}' somehow reached processing stage.")
            sys.exit(1)

        logger.info("Processing complete.")

    except Exception as e:
        logger.error(f"An unexpected error occurred during processing: {e}", exc_info=verbose) # Show traceback if verbose
        sys.exit(1)


if __name__ == "__main__":
    cli()