# src/yt_obsidian/processor.py

import logging
import os
import yaml
from pathlib import Path
from typing import Set, Tuple, Optional

from .clients.youtube_client import YouTubeClient
from .clients.transcript_client import TranscriptClient
from .writers.markdown_writer import MarkdownWriter

logger = logging.getLogger(__name__)

class VideoProcessor:
    """
    Handles the processing of YouTube videos, playlists, and channels.
    Uses the service container's clients for all operations.
    """
    
    def __init__(self, youtube_client: YouTubeClient, transcript_client: TranscriptClient, writer: MarkdownWriter):
        """
        Initialize the processor with required clients.
        
        Args:
            youtube_client: YouTube API client for fetching video metadata
            transcript_client: Client for fetching video transcripts
            writer: Markdown writer for creating notes
        """
        self.youtube_client = youtube_client
        self.transcript_client = transcript_client
        self.writer = writer
    
    def detect_content_type(self, input_str: str) -> Tuple[Optional[str], Optional[str]]:
        """
        Detects YouTube content type and extracts ID using YouTube API verification.
        
        Args:
            input_str: URL or ID string to analyze
            
        Returns:
            Tuple of (content_type, content_id) or (None, None) if detection fails
        """
        logger.debug(f"Attempting to detect content type for: '{input_str}' using API verification.")

        # Use the YouTube API to verify the input string and get the canonical type and ID
        content_type, content_id = self.youtube_client.verify_input_type(input_str)

        if content_type and content_id:
            logger.info(f"API verification successful for '{input_str}': Type={content_type}, ID={content_id}")
            return content_type, content_id
        else:
            logger.error(f"Could not determine content type or extract valid ID from input via API: {input_str}")
            return None, None
    
    def get_existing_video_ids(self, output_dir: Path) -> Set[str]:
        """
        Get set of video IDs from existing markdown files in the specified directory.
        
        Args:
            output_dir: Directory to scan for existing notes
            
        Returns:
            Set of video IDs found in the frontmatter of markdown files
        """
        video_ids = set()
        if not output_dir.exists():
            logger.warning(f"Output directory not found: {output_dir}. No existing videos detected.")
            return video_ids
        if not output_dir.is_dir():
            logger.error(f"Output path is not a directory: {output_dir}")
            return video_ids

        logger.info(f"Scanning for existing notes in: {output_dir}")
        for filename in os.listdir(output_dir):
            if not filename.endswith('.md'):
                continue

            filepath = output_dir / filename
            try:
                with open(filepath, 'r', encoding='utf-8') as f:
                    content = f.read()
                    if content.startswith('---'):
                        # Find the closing frontmatter delimiter
                        parts = content.split('---', 2)
                        if len(parts) >= 3:  # Ensure we have a proper frontmatter section
                            frontmatter = parts[1]
                            # Handle empty or malformed YAML
                            try:
                                metadata = yaml.safe_load(frontmatter)
                                if metadata and isinstance(metadata, dict) and 'youtube_id' in metadata:
                                    video_ids.add(metadata['youtube_id'])
                            except yaml.YAMLError as yaml_error:
                                logger.warning(f"YAML parsing error in {filename}: {yaml_error}")
                        else:
                            logger.warning(f"File {filename} has incomplete frontmatter (missing closing '---')")
            except Exception as e:
                logger.warning(f"Error reading {filename}: {e}")
                
        logger.info(f"Found {len(video_ids)} existing video notes in {output_dir}")
        return video_ids
    
    def process_video(self, video_id: str, output_dir: Path, overwrite: bool):
        """
        Fetches details & transcript for a video and writes a note.
        
        Args:
            video_id: YouTube video ID
            output_dir: Directory to save the note
            overwrite: Whether to overwrite existing notes
        """
        logger.info(f"Processing video: {video_id}")
        # Check if exists (unless overwrite)
        existing_ids = self.get_existing_video_ids(output_dir)
        if not overwrite and video_id in existing_ids:
            logger.info(f"Skipping existing video note: {video_id}")
            return

        try:
            logger.debug(f"Fetching details for video: {video_id}")
            video_details_list = self.youtube_client.get_video_details([video_id])
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
                transcript = self.transcript_client.get_transcript(video_id)
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
            path = self.writer.write_video_note(video_meta, transcript, output_dir)
            logger.info(f"Successfully wrote note: {path}")

        except Exception as e:
            # Log the specific error for this video but allow loop (if any) to continue
            logger.error(f"Failed to process video {video_id}: {e}", exc_info=logging.getLogger().level == logging.DEBUG)
    
    def process_playlist(self, playlist_id: str, output_dir: Path, overwrite: bool, limit: int = 0):
        """
        Fetches videos from a playlist, filters, and processes them.
        
        Args:
            playlist_id: YouTube playlist ID
            output_dir: Directory to save the notes
            overwrite: Whether to overwrite existing notes
        """
        logger.info(f"Processing playlist: {playlist_id}")
        try:
            logger.debug(f"Fetching videos for playlist: {playlist_id}")
            all_videos_items = self.youtube_client.get_videos_from_playlist(playlist_id) # These are playlistItems
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

            existing_ids = self.get_existing_video_ids(output_dir)
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

            # Apply limit if specified
            if limit > 0 and len(videos_to_process_ids) > limit:
                logger.info(f"Limiting to {limit} videos out of {len(videos_to_process_ids)} based on --limit parameter")
                videos_to_process_ids = videos_to_process_ids[:limit]
            
            # Process the filtered video IDs individually
            processed_count = 0
            total_to_process = len(videos_to_process_ids)
            for i, vid in enumerate(videos_to_process_ids):
                logger.info(f"Processing video {i+1}/{total_to_process} from playlist {playlist_id}: {vid}")
                # Pass overwrite=True because we've already filtered based on the flag
                # Individual video errors are logged within process_video
                self.process_video(vid, output_dir, overwrite=True)
                processed_count += 1

            logger.info(f"Finished processing playlist {playlist_id}. Attempted to process {processed_count} videos.")

        except Exception as e:
            # Log error for the playlist processing itself
            logger.error(f"Failed to process playlist {playlist_id}: {e}", exc_info=logging.getLogger().level == logging.DEBUG)
    
    def process_channel(self, channel_id: str, output_dir: Path, overwrite: bool, max_depth: int):
        """
        Fetches playlists from a channel and delegates processing.
        
        Args:
            channel_id: YouTube channel ID
            output_dir: Directory to save the notes
            overwrite: Whether to overwrite existing notes
            max_depth: Maximum number of playlists to process (0 for all)
        """
        logger.info(f"Processing channel: {channel_id} (max depth: {max_depth if max_depth > 0 else 'all'})")
        try:
            logger.debug(f"Fetching playlists for channel: {channel_id}")
            playlists = self.youtube_client.get_channel_playlists(channel_id)
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
                    self.process_playlist(pl_id, output_dir, overwrite)
                    processed_pl_count += 1
                else:
                    logger.warning(f"Skipping playlist with missing ID in channel {channel_id}: '{pl_title}'")

            logger.info(f"Finished processing channel {channel_id}. Attempted to process {processed_pl_count} playlists.")

        except Exception as e:
            # Log error for the channel processing itself
            logger.error(f"Failed to process channel {channel_id}: {e}", exc_info=logging.getLogger().level == logging.DEBUG)