from __future__ import annotations

import asyncio
import logging
import re
from collections.abc import Sequence
from urllib.parse import parse_qs, urlparse

from youtube_transcript_api import YouTubeTranscriptApi

from app.domain.errors import SourceFetchError

logger = logging.getLogger(__name__)

YOUTUBE_HOSTS = {
    "youtube.com",
    "www.youtube.com",
    "m.youtube.com",
    "music.youtube.com",
    "youtu.be",
    "www.youtu.be",
}
VIDEO_ID_PATTERN = re.compile(r"^[A-Za-z0-9_-]{11}$")


def extract_youtube_video_id(source_url: str) -> str | None:
    parsed = urlparse(source_url)
    host = (parsed.hostname or "").lower()
    if host not in YOUTUBE_HOSTS:
        return None

    if host in {"youtu.be", "www.youtu.be"}:
        candidate = parsed.path.strip("/").split("/", 1)[0]
        return candidate if VIDEO_ID_PATTERN.fullmatch(candidate or "") else None

    query_video_id = parse_qs(parsed.query).get("v", [None])[0]
    if query_video_id and VIDEO_ID_PATTERN.fullmatch(query_video_id):
        return query_video_id

    path_parts = [part for part in parsed.path.split("/") if part]
    if len(path_parts) >= 2 and path_parts[0] in {"shorts", "embed", "live"}:
        candidate = path_parts[1]
        if VIDEO_ID_PATTERN.fullmatch(candidate):
            return candidate
    return None


def canonical_youtube_video_url(video_id: str) -> str:
    return f"https://www.youtube.com/watch?v={video_id}"


class YouTubeTranscriptProvider:
    def __init__(self) -> None:
        self._client = YouTubeTranscriptApi()

    async def fetch_transcript(
        self,
        *,
        video_url: str,
        languages: Sequence[str],
    ) -> str:
        video_id = extract_youtube_video_id(video_url)
        if not video_id:
            logger.warning(
                "youtube_transcript.invalid_url source_url=%s",
                video_url,
            )
            raise SourceFetchError(
                "The YouTube URL is invalid or missing a video ID.",
                reason_code="youtube_invalid_url",
            )

        requested_languages = [lang.strip() for lang in languages if lang.strip()] or ["en"]
        logger.info(
            "youtube_transcript.fetch.started video_id=%s source_url=%s languages=%s",
            video_id,
            video_url,
            ",".join(requested_languages),
        )
        try:
            fetched = await asyncio.to_thread(
                self._client.fetch,
                video_id,
                languages=requested_languages,
            )
        except Exception as exc:  # pragma: no cover - external library exceptions vary by version
            mapped = self._map_library_error(exc)
            logger.warning(
                "youtube_transcript.fetch.failed video_id=%s source_url=%s reason_code=%s upstream_exception=%s upstream_message=%s",
                video_id,
                video_url,
                mapped.reason_code,
                exc.__class__.__name__,
                str(exc),
            )
            raise mapped from exc

        lines = [snippet.text.strip() for snippet in fetched if snippet.text and snippet.text.strip()]
        transcript = " ".join(lines).strip()
        if not transcript:
            logger.warning(
                "youtube_transcript.fetch.empty video_id=%s source_url=%s",
                video_id,
                video_url,
            )
            raise SourceFetchError(
                "The YouTube video has no usable transcript text.",
                reason_code="youtube_transcript_unavailable",
            )
        logger.info(
            "youtube_transcript.fetch.completed video_id=%s source_url=%s snippet_count=%s transcript_chars=%s",
            video_id,
            video_url,
            len(lines),
            len(transcript),
        )
        return transcript

    def _map_library_error(self, error: Exception) -> SourceFetchError:
        error_name = error.__class__.__name__.lower()
        message = str(error).lower()
        if "requestblocked" in error_name or "ipblocked" in error_name:
            return SourceFetchError(
                "YouTube blocked transcript requests from this IP. Try again later or use a proxy.",
                reason_code="youtube_request_blocked",
            )
        if "novideofound" in error_name:
            return SourceFetchError(
                "The YouTube video could not be found.",
                reason_code="youtube_invalid_url",
            )
        if (
            "notranscriptfound" in error_name
            or "transcriptsdisabled" in error_name
            or "no transcript" in message
            or ("transcript" in message and "disabled" in message)
        ):
            return SourceFetchError(
                "No transcript is available for this YouTube video.",
                reason_code="youtube_transcript_unavailable",
            )
        return SourceFetchError(
            "The YouTube transcript could not be fetched.",
            reason_code="source_unreachable",
        )
