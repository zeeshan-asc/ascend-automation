from __future__ import annotations

import logging
from collections.abc import Iterable

import feedparser  # type: ignore[import-untyped]
import httpx

from app.domain.errors import FeedFetchError
from app.domain.models import ParsedEpisode

logger = logging.getLogger(__name__)

RSS_REQUEST_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/135.0.0.0 Safari/537.36"
    ),
    "Accept": "application/rss+xml, application/xml, text/xml;q=0.9, */*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}


class RSSProvider:
    def __init__(self, *, timeout_seconds: int) -> None:
        self._timeout_seconds = timeout_seconds

    async def fetch_episodes(self, rss_url: str, max_results: int) -> list[ParsedEpisode]:
        logger.info("rss.fetch.started rss_url=%s max_results=%s", rss_url, max_results)
        async with httpx.AsyncClient(
            timeout=self._timeout_seconds,
            follow_redirects=True,
            headers=RSS_REQUEST_HEADERS,
        ) as client:
            response = await client.get(rss_url)
            response.raise_for_status()
        parsed = feedparser.parse(response.text)
        entries = parsed.entries[:max_results]
        episodes: list[ParsedEpisode] = []
        seen_keys: set[str] = set()
        for entry in entries:
            audio_url = self._extract_audio_url(entry)
            if not audio_url:
                continue
            guid = entry.get("id") or entry.get("guid")
            episode_url = entry.get("link")
            dedupe_key = str(guid or episode_url or audio_url)
            if dedupe_key in seen_keys:
                continue
            seen_keys.add(dedupe_key)
            episodes.append(
                ParsedEpisode(
                    guid=str(guid) if guid else None,
                    title=str(entry.get("title", "Untitled episode")),
                    episode_url=str(episode_url) if episode_url else None,
                    audio_url=str(audio_url),
                    published_at=str(entry.get("published", "")) or None,
                    feed_url=rss_url,
                    dedupe_key=dedupe_key,
                ),
            )
        if not episodes:
            raise FeedFetchError("No usable audio episodes were found in the RSS feed.")
        logger.info("rss.fetch.completed rss_url=%s episodes=%s", rss_url, len(episodes))
        return episodes

    def _extract_audio_url(self, entry: feedparser.util.FeedParserDict) -> str | None:
        enclosure_candidates: Iterable[dict[str, str]] = entry.get("enclosures", []) or []
        for enclosure in enclosure_candidates:
            mime_type = str(enclosure.get("type", ""))
            if mime_type.startswith("audio/") and enclosure.get("href"):
                return str(enclosure["href"])
            if enclosure.get("url"):
                return str(enclosure["url"])
        for link in entry.get("links", []) or []:
            if link.get("rel") == "enclosure" and link.get("href"):
                return str(link["href"])
        return None
