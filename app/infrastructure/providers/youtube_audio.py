from __future__ import annotations

import asyncio
import mimetypes
from urllib.parse import urlparse

import httpx
import yt_dlp

from app.domain.errors import SourceFetchError


class YouTubeAudioProvider:
    async def download_best_audio(
        self,
        *,
        youtube_url: str,
    ) -> tuple[bytes, str]:
        extracted = await self._extract_stream_info(youtube_url)
        audio_url = self._extract_audio_url(extracted)
        if not audio_url:
            raise SourceFetchError(
                "The YouTube link did not expose a downloadable audio stream.",
                reason_code="youtube_audio_not_found",
            )

        audio_bytes = await self._download_audio_bytes(audio_url)
        content_type = self._resolve_content_type(audio_url, extracted)
        return audio_bytes, content_type

    async def _extract_stream_info(self, youtube_url: str) -> dict:
        options = {
            "format": "bestaudio/best",
            "quiet": True,
            "no_warnings": True,
            "skip_download": True,
            "noplaylist": True,
        }

        def _extract() -> dict:
            with yt_dlp.YoutubeDL(options) as ydl:
                payload = ydl.extract_info(youtube_url, download=False)
            if not isinstance(payload, dict):
                raise SourceFetchError(
                    "The YouTube link did not return media metadata.",
                    reason_code="source_invalid",
                )
            if "entries" in payload and isinstance(payload["entries"], list):
                first_entry = next(
                    (entry for entry in payload["entries"] if isinstance(entry, dict)),
                    None,
                )
                if first_entry is None:
                    raise SourceFetchError(
                        "The YouTube playlist did not contain a valid video entry.",
                        reason_code="source_invalid",
                    )
                payload = first_entry
            return payload

        try:
            return await asyncio.to_thread(_extract)
        except yt_dlp.utils.DownloadError as exc:
            raise SourceFetchError(
                "The YouTube link could not be fetched. Check the URL and try again.",
                reason_code="source_unreachable",
            ) from exc

    def _extract_audio_url(self, payload: dict) -> str | None:
        direct_url = payload.get("url")
        if isinstance(direct_url, str) and direct_url.strip():
            return direct_url.strip()

        formats = payload.get("formats")
        if not isinstance(formats, list):
            return None
        audio_only_formats = [
            fmt
            for fmt in formats
            if isinstance(fmt, dict)
            and isinstance(fmt.get("url"), str)
            and fmt["url"].strip()
            and fmt.get("acodec") not in (None, "none")
            and fmt.get("vcodec") in (None, "none")
        ]
        if not audio_only_formats:
            return None
        best = max(audio_only_formats, key=lambda fmt: float(fmt.get("abr") or 0))
        return str(best["url"]).strip()

    async def _download_audio_bytes(self, audio_url: str) -> bytes:
        try:
            async with httpx.AsyncClient(timeout=120, follow_redirects=True) as client:
                response = await client.get(audio_url)
                response.raise_for_status()
                return response.content
        except httpx.HTTPError as exc:
            raise SourceFetchError(
                "The extracted YouTube audio stream could not be downloaded.",
                reason_code="youtube_audio_download_failed",
            ) from exc

    def _resolve_content_type(self, audio_url: str, payload: dict) -> str:
        ext = str(payload.get("ext") or "").strip().lower()
        if ext:
            guessed, _ = mimetypes.guess_type(f"audio.{ext}")
            if guessed:
                return guessed

        guessed_from_url, _ = mimetypes.guess_type(urlparse(audio_url).path)
        if guessed_from_url:
            return guessed_from_url
        return "application/octet-stream"
