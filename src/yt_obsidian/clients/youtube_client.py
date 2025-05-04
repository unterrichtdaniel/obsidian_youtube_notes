import logging
import httplib2
from googleapiclient.discovery import build
from googleapiclient.http import HttpRequest
from typing import Optional, Any, Dict, TYPE_CHECKING
import re

# Use TYPE_CHECKING to avoid circular imports
if TYPE_CHECKING:
    from ..container import CachedSession

logger = logging.getLogger(__name__)

class SessionAwareHttp(httplib2.Http):
    """Custom HTTP class that uses the provided requests session for HTTP requests."""
    
    def __init__(self, session=None, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.session = session
        
    def request(self, uri, method="GET", body=None, headers=None, **kwargs):
        """Override request method to use the session if available."""
        if self.session is None:
            return super().request(uri, method, body, headers, **kwargs)
        
        # Convert httplib2 request to requests format
        if headers is None:
            headers = {}
        
        try:
            # Use the session to make the request
            response = self.session.request(
                method=method,
                url=uri,
                data=body,
                headers=headers
            )
            
            # Convert requests response to httplib2 format
            content = response.content
            response_headers = dict(response.headers)
            status = response.status_code
            
            return (httplib2.Response(response_headers), content)
        except Exception as e:
            # Log the error and fall back to httplib2
            logging.error(f"Error using session for request: {e}")
            return super().request(uri, method, body, headers, **kwargs)

class YouTubeClient:
    def __init__(self, api_key: str, session: Optional["CachedSession"] = None):
        """
        Initialize the YouTube client with API key and optional session.
        
        Args:
            api_key: YouTube API key for authentication
            session: Optional CachedSession for HTTP requests with retry and timeout handling
        """
        self.api_key = api_key
        self.session = session
        
        # Create a custom HTTP object that uses our session if provided
        http = None
        if session:
            http = SessionAwareHttp(session=session)
            
        self.youtube = build("youtube", "v3", developerKey=api_key, http=http)
        
    def _paginate_results(self, resource, **kwargs) -> list[dict]:
        """
        Helper method to handle pagination for YouTube API requests.
        
        Args:
            resource: The YouTube API resource method to call (e.g., self.youtube.playlistItems().list)
            **kwargs: The parameters to pass to the resource method
            
        Returns:
            A list of items from all pages
        """
        results = []
        next_page_token = None
        
        while True:
            # Add page token to kwargs if we have one
            if next_page_token:
                kwargs["pageToken"] = next_page_token
                
            # Execute the API request
            response = resource(**kwargs).execute()
            
            # Add items to our results
            results.extend(response.get("items", []))
            
            # Get next page token if available
            next_page_token = response.get("nextPageToken")
            if not next_page_token:
                break
                
        return results

    def get_videos_from_playlist(self, playlist_id: str) -> list[dict]:
        """
        Fetch all videos metadata from a given playlist.
        Returns list of video resource dicts.
        """
        videos = self._paginate_results(
            self.youtube.playlistItems().list,
            part="snippet,contentDetails",
            playlistId=playlist_id,
            maxResults=50
        )
        logger.info(f"Fetched {len(videos)} videos from playlist {playlist_id}")
        return videos

    # Indented this method
    def get_video_details(self, video_ids: list[str]) -> list[dict]:
        """
        Fetch details for a list of video IDs.
        Handles potential API limits by batching requests if necessary (though 50 is usually fine).
        """
        video_details = []
        # The API allows up to 50 IDs per request
        for i in range(0, len(video_ids), 50):
            batch_ids = video_ids[i:i+50]
            try:
                res = self.youtube.videos().list(
                    part="snippet,contentDetails,statistics", # Added statistics
                    id=",".join(batch_ids)
                ).execute()
                video_details.extend(res.get("items", []))
                logger.debug(f"Fetched details for video IDs: {batch_ids}")
            except Exception as e:
                logger.error(f"Failed to fetch details for video IDs {batch_ids}: {e}")
                # Decide whether to continue with other batches or raise/return partial
                # For now, log error and continue
        logger.info(f"Fetched details for {len(video_details)} out of {len(video_ids)} requested videos.")
        return video_details

    def get_channel_playlists(self, channel_id: str) -> list[dict]:
        """
        List all playlists for a given channel.
        """
        playlists = self._paginate_results(
            self.youtube.playlists().list,
            part="snippet,contentDetails",
            channelId=channel_id,
            maxResults=50
        )
        logger.info(f"Fetched {len(playlists)} playlists from channel {channel_id}")
        return playlists

    def verify_input_type(self, input_str: str) -> tuple[Optional[str], Optional[str]]:
        """
        Uses the YouTube Search API to determine the type (video, playlist, channel)
        and canonical ID of an input string (URL, ID, handle, etc.).

        Returns:
            A tuple (content_type, content_id) or (None, None) if not found/identifiable.
            content_type will be one of 'video', 'playlist', 'channel'.
        """
        logger.debug(f"Attempting API verification for input: '{input_str}'")
        # Handle YouTube handle URLs like https://www.youtube.com/@handle
        if "youtube.com" in input_str and "@" in input_str:
            m = re.search(r'@(?P<handle>[^/?&#]+)', input_str)
            if m:
                handle = m.group("handle")
                logger.debug(f"Extracted handle: '{handle}' from URL: '{input_str}'")
                try:
                    # Search for channel by handle
                    logger.debug(f"Searching for channel with query: '@{handle}'")
                    search_resp = self.youtube.search().list(
                        q=f"@{handle}",
                        part="id",
                        type="channel",
                        maxResults=1
                    ).execute()
                    
                    # Log the full response for debugging
                    logger.debug(f"Channel handle search response: {search_resp}")
                    
                    items = search_resp.get("items", [])
                    logger.debug(f"Found {len(items)} items in search response")
                    
                    if items:
                        channel_id = items[0].get("id", {}).get("channelId")
                        if channel_id:
                            logger.info(f"Detected channel handle '{handle}', ID={channel_id}")
                            return "channel", channel_id
                        else:
                            logger.warning(f"Channel ID not found in search result for handle '{handle}'. Result item: {items[0]}")
                    else:
                        logger.warning(f"No items found in search results for handle '{handle}'")
                        
                    # Try an alternative approach - search by channel name without @ symbol
                    logger.debug(f"Trying alternative search without @ symbol for handle: '{handle}'")
                    alt_search_resp = self.youtube.search().list(
                        q=handle,
                        part="id",
                        type="channel",
                        maxResults=1
                    ).execute()
                    
                    alt_items = alt_search_resp.get("items", [])
                    logger.debug(f"Found {len(alt_items)} items in alternative search response")
                    
                    if alt_items:
                        alt_channel_id = alt_items[0].get("id", {}).get("channelId")
                        if alt_channel_id:
                            logger.info(f"Detected channel via alternative search for '{handle}', ID={alt_channel_id}")
                            return "channel", alt_channel_id
                except Exception as e:
                    logger.warning(f"Error resolving handle '{handle}': {e}", exc_info=True)
        try:
            # Search for the input string, prioritizing exact matches if possible.
            # We limit results to 1 as we only need the top hit to identify the type.
            # We specify the types we are interested in.
            search_response = self.youtube.search().list(
                q=input_str,
                part="id", # Only need the ID part to determine kind
                maxResults=1,
                type="video,playlist,channel" # Search across all relevant types
            ).execute()

            items = search_response.get("items", [])
            if not items:
                logger.debug(f"API search returned no results for '{input_str}'")
                return None, None

            top_result = items[0]
            kind = top_result.get("id", {}).get("kind")
            content_id = None
            content_type = None

            if kind == "youtube#video":
                content_type = "video"
                content_id = top_result.get("id", {}).get("videoId")
            elif kind == "youtube#playlist":
                content_type = "playlist"
                content_id = top_result.get("id", {}).get("playlistId")
            elif kind == "youtube#channel":
                content_type = "channel"
                content_id = top_result.get("id", {}).get("channelId")
            else:
                logger.warning(f"API search returned unknown kind '{kind}' for '{input_str}'")
                return None, None

            if content_id:
                logger.info(f"API verification successful for '{input_str}': Type={content_type}, ID={content_id}")
                return content_type, content_id
            else:
                logger.warning(f"API search returned kind '{kind}' but no ID for '{input_str}'")
                return None, None

        except Exception as e:
            logger.error(f"API error during verification for '{input_str}': {e}", exc_info=True)
            # Treat API errors as non-verification
            return None, None