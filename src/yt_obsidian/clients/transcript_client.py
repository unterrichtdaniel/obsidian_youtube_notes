import logging
from youtube_transcript_api import YouTubeTranscriptApi, TranscriptsDisabled

logger = logging.getLogger(__name__)

class TranscriptClient:
    def get_transcript(self, video_id: str) -> str:
        """
        Retrieve full transcript text for a given video_id, with timestamps.
        """
        try:
            transcript_list = YouTubeTranscriptApi.get_transcript(video_id)
            # Format each segment as "[mm:ss] text"
            def format_time(seconds):
                minutes = int(seconds // 60)
                secs = int(seconds % 60)
                return f"{minutes:02}:{secs:02}"
            return "\n".join(
                [f"[{format_time(seg['start'])}] {seg['text']}" for seg in transcript_list]
            )
        except TranscriptsDisabled:
            logger.warning(f"Transcripts are disabled for video {video_id}")
            return ""
