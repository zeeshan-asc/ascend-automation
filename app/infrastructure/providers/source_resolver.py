from __future__ import annotations

import json
import posixpath
from collections import defaultdict
from html.parser import HTMLParser
from typing import Any
from urllib.parse import unquote, urljoin, urlparse

import httpx

from app.domain.enums import SourceKind
from app.domain.errors import FeedFetchError, SourceFetchError
from app.domain.interfaces import RSSProviderProtocol, SourceResolverProtocol
from app.domain.models import ParsedEpisode
from app.infrastructure.providers.rss import RSS_REQUEST_HEADERS

HTML_REQUEST_HEADERS = {
    **RSS_REQUEST_HEADERS,
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}
DIRECT_AUDIO_EXTENSIONS = (
    ".mp3",
    ".m4a",
    ".wav",
    ".aac",
    ".ogg",
    ".opus",
    ".flac",
)
EPISODE_PAGE_AUDIO_META_KEYS = (
    "og:audio",
    "og:audio:url",
    "twitter:player:stream",
)
PUBLISHED_META_KEYS = ("article:published_time", "og:published_time")


class _EpisodePageParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.meta_values: dict[str, list[str]] = defaultdict(list)
        self.audio_sources: list[str] = []
        self.title_parts: list[str] = []
        self.json_ld_parts: list[str] = []
        self._in_title = False
        self._in_json_ld = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attributes = {key.lower(): value for key, value in attrs if value is not None}
        tag_name = tag.lower()

        if tag_name == "meta":
            key = (attributes.get("property") or attributes.get("name") or "").strip().lower()
            content = (attributes.get("content") or "").strip()
            if key and content:
                self.meta_values[key].append(content)
            return

        if tag_name == "audio":
            source = (attributes.get("src") or "").strip()
            if source:
                self.audio_sources.append(source)
            return

        if tag_name == "source":
            source = (attributes.get("src") or "").strip()
            if source:
                self.audio_sources.append(source)
            return

        if tag_name == "title":
            self._in_title = True
            return

        if tag_name == "script":
            script_type = (attributes.get("type") or "").strip().lower()
            if script_type == "application/ld+json":
                self._in_json_ld = True
                self.json_ld_parts.append("")

    def handle_endtag(self, tag: str) -> None:
        tag_name = tag.lower()
        if tag_name == "title":
            self._in_title = False
        if tag_name == "script":
            self._in_json_ld = False

    def handle_data(self, data: str) -> None:
        if self._in_title:
            self.title_parts.append(data)
        if self._in_json_ld and self.json_ld_parts:
            self.json_ld_parts[-1] += data

    @property
    def title(self) -> str | None:
        title = "".join(self.title_parts).strip()
        return title or None


class DirectAudioResolver:
    def __init__(self, *, timeout_seconds: int) -> None:
        self._timeout_seconds = timeout_seconds

    def looks_like_audio_url(self, source_url: str) -> bool:
        path = urlparse(source_url).path.lower()
        return any(path.endswith(extension) for extension in DIRECT_AUDIO_EXTENSIONS)

    async def resolve_audio_url(self, source_url: str) -> list[ParsedEpisode]:
        try:
            async with httpx.AsyncClient(
                timeout=self._timeout_seconds,
                follow_redirects=True,
                headers=RSS_REQUEST_HEADERS,
            ) as client:
                response = await client.head(source_url)
                if response.status_code in {405, 501}:
                    response = await client.get(source_url, headers={"Range": "bytes=0-0"})
                response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code == 404:
                raise SourceFetchError(
                    "The source URL returned 404 Not Found.",
                    reason_code="source_not_found",
                ) from exc
            raise SourceFetchError(
                "The source URL could not be reached. Check the URL and try again.",
                reason_code="source_unreachable",
            ) from exc
        except httpx.RequestError as exc:
            raise SourceFetchError(
                "The source URL could not be reached. Check the URL and try again.",
                reason_code="source_unreachable",
            ) from exc

        resolved_audio_url = str(response.url)
        content_type = (response.headers.get("content-type") or "").split(
            ";",
            1,
        )[0].strip().lower()
        if not content_type.startswith("audio/") and not self.looks_like_audio_url(
            resolved_audio_url,
        ):
            raise SourceFetchError(
                "The URL did not point to a direct audio file.",
                reason_code="source_invalid",
            )

        title = self._build_title_from_url(resolved_audio_url)
        return [
            ParsedEpisode(
                title=title,
                episode_url=None,
                audio_url=resolved_audio_url,
                published_at=None,
                source_url=source_url,
                source_kind=SourceKind.AUDIO_FILE,
                dedupe_key=f"audio:{resolved_audio_url}",
            )
        ]

    def _build_title_from_url(self, audio_url: str) -> str:
        path = urlparse(audio_url).path
        filename = posixpath.basename(path)
        stem = posixpath.splitext(filename)[0]
        cleaned = unquote(stem).replace("-", " ").replace("_", " ").strip()
        return cleaned or "Direct audio episode"


class EpisodePageResolver:
    def __init__(self, *, timeout_seconds: int) -> None:
        self._timeout_seconds = timeout_seconds

    async def resolve_episode_page(self, source_url: str) -> list[ParsedEpisode]:
        html = await self._fetch_page_html(source_url)
        parser = _EpisodePageParser()
        parser.feed(html)

        audio_url = self._extract_audio_url(parser, source_url)
        if not audio_url:
            raise SourceFetchError(
                "The episode page did not expose a usable audio file.",
                reason_code="episode_audio_not_found",
            )

        title = self._extract_title(parser) or "Podcast episode"
        published_at = self._extract_published_at(parser)
        return [
            ParsedEpisode(
                title=title,
                episode_url=source_url,
                audio_url=audio_url,
                published_at=published_at,
                source_url=source_url,
                source_kind=SourceKind.EPISODE_PAGE,
                dedupe_key=f"audio:{audio_url}",
            )
        ]

    async def _fetch_page_html(self, source_url: str) -> str:
        try:
            async with httpx.AsyncClient(
                timeout=self._timeout_seconds,
                follow_redirects=True,
                headers=HTML_REQUEST_HEADERS,
            ) as client:
                response = await client.get(source_url)
                response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code == 404:
                raise SourceFetchError(
                    "The source URL returned 404 Not Found.",
                    reason_code="source_not_found",
                ) from exc
            raise SourceFetchError(
                "The source URL could not be reached. Check the URL and try again.",
                reason_code="source_unreachable",
            ) from exc
        except httpx.RequestError as exc:
            raise SourceFetchError(
                "The source URL could not be reached. Check the URL and try again.",
                reason_code="source_unreachable",
            ) from exc

        content_type = (response.headers.get("content-type") or "").split(";", 1)[0].strip().lower()
        if content_type and "html" not in content_type and "xml" not in content_type:
            raise SourceFetchError(
                "The URL did not return a podcast episode page.",
                reason_code="source_invalid",
            )
        return response.text

    def _extract_audio_url(self, parser: _EpisodePageParser, source_url: str) -> str | None:
        for key in EPISODE_PAGE_AUDIO_META_KEYS:
            value = self._first_meta(parser, key)
            if value:
                return urljoin(source_url, value)

        for candidate in self._iter_json_ld_audio_candidates(parser, source_url):
            return candidate

        for candidate in parser.audio_sources:
            if candidate:
                return urljoin(source_url, candidate)
        return None

    def _extract_title(self, parser: _EpisodePageParser) -> str | None:
        return self._first_meta(parser, "og:title") or parser.title

    def _extract_published_at(self, parser: _EpisodePageParser) -> str | None:
        for key in PUBLISHED_META_KEYS:
            value = self._first_meta(parser, key)
            if value:
                return value
        for candidate in self._iter_json_ld_dates(parser):
            return candidate
        return None

    def _first_meta(self, parser: _EpisodePageParser, key: str) -> str | None:
        values = parser.meta_values.get(key.lower(), [])
        if not values:
            return None
        return values[0].strip() or None

    def _iter_json_ld_audio_candidates(
        self,
        parser: _EpisodePageParser,
        source_url: str,
    ) -> list[str]:
        audio_urls: list[str] = []
        for blob in parser.json_ld_parts:
            if not blob.strip():
                continue
            try:
                payload = json.loads(blob)
            except json.JSONDecodeError:
                continue
            self._collect_json_ld_audio_urls(payload, audio_urls, source_url)
        return audio_urls

    def _iter_json_ld_dates(self, parser: _EpisodePageParser) -> list[str]:
        dates: list[str] = []
        for blob in parser.json_ld_parts:
            if not blob.strip():
                continue
            try:
                payload = json.loads(blob)
            except json.JSONDecodeError:
                continue
            self._collect_json_ld_dates(payload, dates)
        return dates

    def _collect_json_ld_audio_urls(
        self,
        payload: Any,
        audio_urls: list[str],
        source_url: str,
    ) -> None:
        if isinstance(payload, list):
            for item in payload:
                self._collect_json_ld_audio_urls(item, audio_urls, source_url)
            return
        if not isinstance(payload, dict):
            return

        for key in ("contentUrl", "embedUrl"):
            value = payload.get(key)
            if isinstance(value, str) and value.strip():
                audio_urls.append(urljoin(source_url, value.strip()))

        associated_media = payload.get("associatedMedia")
        encoding = payload.get("encoding")
        if associated_media is not None:
            self._collect_json_ld_audio_urls(associated_media, audio_urls, source_url)
        if encoding is not None:
            self._collect_json_ld_audio_urls(encoding, audio_urls, source_url)

        for value in payload.values():
            if isinstance(value, (dict, list)):
                self._collect_json_ld_audio_urls(value, audio_urls, source_url)

    def _collect_json_ld_dates(self, payload: Any, dates: list[str]) -> None:
        if isinstance(payload, list):
            for item in payload:
                self._collect_json_ld_dates(item, dates)
            return
        if not isinstance(payload, dict):
            return

        for key in ("datePublished", "uploadDate"):
            value = payload.get(key)
            if isinstance(value, str) and value.strip():
                dates.append(value.strip())

        for value in payload.values():
            if isinstance(value, (dict, list)):
                self._collect_json_ld_dates(value, dates)


class SourceResolver(SourceResolverProtocol):
    def __init__(
        self,
        *,
        rss_resolver: RSSProviderProtocol,
        direct_audio_resolver: DirectAudioResolver,
        episode_page_resolver: EpisodePageResolver,
    ) -> None:
        self._rss_resolver = rss_resolver
        self._direct_audio_resolver = direct_audio_resolver
        self._episode_page_resolver = episode_page_resolver

    async def resolve_source(
        self,
        *,
        source_url: str,
        source_kind: SourceKind,
        max_results: int,
    ) -> list[ParsedEpisode]:
        if source_kind == SourceKind.RSS_FEED:
            return await self._rss_resolver.fetch_episodes(source_url, max_results)
        if source_kind == SourceKind.AUDIO_FILE:
            return await self._direct_audio_resolver.resolve_audio_url(source_url)
        if source_kind == SourceKind.EPISODE_PAGE:
            return await self._episode_page_resolver.resolve_episode_page(source_url)
        return await self._resolve_auto(source_url=source_url, max_results=max_results)

    async def _resolve_auto(self, *, source_url: str, max_results: int) -> list[ParsedEpisode]:
        if self._direct_audio_resolver.looks_like_audio_url(source_url):
            return await self._direct_audio_resolver.resolve_audio_url(source_url)

        rss_error: FeedFetchError | None = None
        try:
            return await self._rss_resolver.fetch_episodes(source_url, max_results)
        except FeedFetchError as exc:
            rss_error = exc

        try:
            return await self._episode_page_resolver.resolve_episode_page(source_url)
        except SourceFetchError as page_error:
            if rss_error and rss_error.reason_code == "feed_has_no_audio_items":
                raise rss_error from page_error
            raise page_error
