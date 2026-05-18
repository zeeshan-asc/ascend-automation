from __future__ import annotations

import asyncio
import re
from html import unescape
from typing import Any
from urllib.parse import urlparse

import httpx
import yt_dlp

YOUTUBE_HOSTS = {
    "youtube.com",
    "www.youtube.com",
    "m.youtube.com",
    "youtu.be",
    "www.youtu.be",
}

TIMESTAMP_PATTERN = re.compile(
    r"^\d{2}:\d{2}:\d{2}\.\d{3}\s+-->\s+\d{2}:\d{2}:\d{2}\.\d{3}",
)
NUMERIC_LINE_PATTERN = re.compile(r"^\d+$")
TAG_PATTERN = re.compile(r"<[^>]+>")
MULTISPACE_PATTERN = re.compile(r"\s+")


def is_youtube_url(source_url: str) -> bool:
    host = (urlparse(source_url).hostname or "").lower()
    return host in YOUTUBE_HOSTS


class YouTubeCaptionExtractor:
    def __init__(
        self,
        *,
        timeout_seconds: int,
        minimum_words: int = 80,
    ) -> None:
        self._timeout_seconds = timeout_seconds
        self._minimum_words = minimum_words

    async def extract_transcript(self, source_url: str) -> str | None:
        if not is_youtube_url(source_url):
            return None

        info = await self._extract_video_info(source_url)
        subtitle_track = self._pick_subtitle_track(info)
        if subtitle_track is None:
            return None

        raw_caption_text = await self._download_caption_text(subtitle_track)
        cleaned = self._clean_caption_text(raw_caption_text)
        if not self._is_usable_transcript(cleaned):
            return None
        return cleaned

    async def _extract_video_info(self, source_url: str) -> dict[str, Any]:
        options: dict[str, Any] = {
            "quiet": True,
            "no_warnings": True,
            "noplaylist": True,
            "socket_timeout": self._timeout_seconds,
            "extract_flat": False,
            "skip_download": True,
            "writesubtitles": True,
            "writeautomaticsub": True,
            "subtitleslangs": ["en.*", "en"],
        }

        def extract() -> dict[str, Any]:
            with yt_dlp.YoutubeDL(options) as client:
                payload = client.extract_info(source_url, download=False)
            if not isinstance(payload, dict):
                return {}
            return payload

        return await asyncio.to_thread(extract)

    async def _download_caption_text(self, subtitle_track: dict[str, Any]) -> str:
        subtitle_url = str(subtitle_track.get("url") or "").strip()
        if not subtitle_url:
            return ""
        try:
            async with httpx.AsyncClient(timeout=self._timeout_seconds) as client:
                response = await client.get(subtitle_url)
                response.raise_for_status()
        except httpx.HTTPError:
            return ""
        return response.text

    def _pick_subtitle_track(self, info: dict[str, Any]) -> dict[str, Any] | None:
        subtitles = info.get("subtitles")
        automatic_captions = info.get("automatic_captions")

        preferred_manual = self._pick_lang_track(subtitles)
        if preferred_manual is not None:
            return preferred_manual

        preferred_auto = self._pick_lang_track(automatic_captions)
        if preferred_auto is not None:
            return preferred_auto
        return None

    def _pick_lang_track(self, tracks_by_lang: Any) -> dict[str, Any] | None:
        if not isinstance(tracks_by_lang, dict):
            return None

        # Prefer english variants first, then any available language.
        ordered_langs = sorted(
            tracks_by_lang.keys(),
            key=lambda key: (0 if str(key).lower().startswith("en") else 1, str(key)),
        )
        for lang in ordered_langs:
            entries = tracks_by_lang.get(lang)
            if not isinstance(entries, list):
                continue
            picked = self._pick_best_track(entries)
            if picked is not None:
                return picked
        return None

    def _pick_best_track(self, entries: list[Any]) -> dict[str, Any] | None:
        preferred_exts = ("vtt", "srv3", "ttml", "srt")
        best_entry: dict[str, Any] | None = None
        best_score = len(preferred_exts) + 1
        for candidate in entries:
            if not isinstance(candidate, dict):
                continue
            if not candidate.get("url"):
                continue
            ext = str(candidate.get("ext") or "").lower()
            try:
                score = preferred_exts.index(ext)
            except ValueError:
                score = len(preferred_exts)
            if score < best_score:
                best_entry = candidate
                best_score = score
        return best_entry

    def _clean_caption_text(self, raw_text: str) -> str:
        if not raw_text.strip():
            return ""

        cleaned_lines: list[str] = []
        previous_line = ""
        for line in raw_text.splitlines():
            stripped = line.strip()
            if not stripped:
                continue
            if stripped.upper() == "WEBVTT":
                continue
            if stripped.startswith("NOTE"):
                continue
            if TIMESTAMP_PATTERN.match(stripped):
                continue
            if NUMERIC_LINE_PATTERN.match(stripped):
                continue

            without_tags = TAG_PATTERN.sub("", stripped)
            normalized = MULTISPACE_PATTERN.sub(" ", unescape(without_tags)).strip()
            if not normalized:
                continue
            if normalized == previous_line:
                continue
            cleaned_lines.append(normalized)
            previous_line = normalized

        return " ".join(cleaned_lines)

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
