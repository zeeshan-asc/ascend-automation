from __future__ import annotations

from app.infrastructure.providers.youtube_transcript_api import (
    YouTubeTranscriptProvider,
    extract_youtube_video_id,
)


class YouTubeCaptionExtractor:
    def __init__(
        self,
        *,
        timeout_seconds: int,
        minimum_words: int = 80,
    ) -> None:
        self._timeout_seconds = timeout_seconds
        self._minimum_words = minimum_words
        self._provider = YouTubeTranscriptProvider()

    async def extract_transcript(self, source_url: str) -> str | None:
        if not extract_youtube_video_id(source_url):
            return None

        transcript = await self._provider.fetch_transcript(
            video_url=source_url,
            languages=["en"],
        )
        if not self._is_usable_transcript(transcript):
            return None
        return transcript

    def _is_usable_transcript(self, transcript: str) -> bool:
        words = transcript.split()
        word_count = len(words)
        if word_count < self._minimum_words:
            return False
            
        unique_words = len(set(word.lower() for word in words))
        if word_count < 500:
            if unique_words / max(word_count, 1) < 0.2:
                return False
        else:
            if unique_words < 100:
                return False
                
        return True
