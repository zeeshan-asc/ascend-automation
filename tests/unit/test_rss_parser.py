from pathlib import Path

import httpx
import pytest
import respx
from httpx import Response

from app.domain.errors import FeedFetchError
from app.infrastructure.providers.rss import RSS_REQUEST_HEADERS, RSSProvider


def fixture_text(name: str) -> str:
    fixture_path = Path(__file__).resolve().parent.parent / "fixtures" / name
    return fixture_path.read_text(encoding="utf-8")


@pytest.mark.asyncio
@respx.mock
async def test_rss_provider_parses_latest_five_audio_episodes() -> None:
    feed_url = "https://example.com/feed.xml"
    respx.get(feed_url).mock(return_value=Response(200, text=fixture_text("sample_feed.xml")))
    provider = RSSProvider(timeout_seconds=10)

    episodes = await provider.fetch_episodes(feed_url, max_results=5)

    assert len(episodes) == 5
    assert episodes[0].dedupe_key == "guid-6"
    assert episodes[-1].dedupe_key == "guid-2"


@pytest.mark.asyncio
@respx.mock
async def test_rss_provider_deduplicates_by_guid() -> None:
    feed_url = "https://example.com/duplicate.xml"
    respx.get(feed_url).mock(
        return_value=Response(200, text=fixture_text("duplicate_guid_feed.xml")),
    )
    provider = RSSProvider(timeout_seconds=10)

    episodes = await provider.fetch_episodes(feed_url, max_results=5)

    assert len(episodes) == 1
    assert episodes[0].dedupe_key == "shared-guid"


@pytest.mark.asyncio
@respx.mock
async def test_rss_provider_raises_when_no_audio_entries_exist() -> None:
    feed_url = "https://example.com/no-audio.xml"
    respx.get(feed_url).mock(return_value=Response(200, text=fixture_text("no_audio_feed.xml")))
    provider = RSSProvider(timeout_seconds=10)

    with pytest.raises(FeedFetchError) as exc_info:
        await provider.fetch_episodes(feed_url, max_results=5)

    assert exc_info.value.reason_code == "feed_has_no_audio_items"


@pytest.mark.asyncio
@respx.mock
async def test_rss_provider_raises_for_unreachable_feed() -> None:
    feed_url = "https://example.com/unreachable.xml"
    respx.get(feed_url).mock(return_value=Response(404, text="missing"))
    provider = RSSProvider(timeout_seconds=10)

    with pytest.raises(FeedFetchError) as exc_info:
        await provider.fetch_episodes(feed_url, max_results=5)

    assert exc_info.value.reason_code == "feed_not_found"


@pytest.mark.asyncio
@respx.mock
async def test_rss_provider_raises_for_timeout_or_connection_errors() -> None:
    feed_url = "https://example.com/timeout.xml"
    respx.get(feed_url).mock(side_effect=httpx.ConnectTimeout("timed out"))
    provider = RSSProvider(timeout_seconds=10)

    with pytest.raises(FeedFetchError) as exc_info:
        await provider.fetch_episodes(feed_url, max_results=5)

    assert exc_info.value.reason_code == "feed_unreachable"


@pytest.mark.asyncio
@respx.mock
async def test_rss_provider_raises_for_invalid_feed_documents() -> None:
    feed_url = "https://example.com/not-a-feed.xml"
    respx.get(feed_url).mock(return_value=Response(200, text="<html>no feed here</html>"))
    provider = RSSProvider(timeout_seconds=10)

    with pytest.raises(FeedFetchError) as exc_info:
        await provider.fetch_episodes(feed_url, max_results=5)

    assert exc_info.value.reason_code == "feed_invalid"


@pytest.mark.asyncio
@respx.mock
async def test_rss_provider_sends_browser_like_feed_headers() -> None:
    feed_url = "https://example.com/feed-headers.xml"
    route = respx.get(feed_url)

    def responder(request: httpx.Request) -> Response:
        assert request.headers["User-Agent"] == RSS_REQUEST_HEADERS["User-Agent"]
        assert request.headers["Accept"] == RSS_REQUEST_HEADERS["Accept"]
        return Response(200, text=fixture_text("sample_feed.xml"))

    route.mock(side_effect=responder)
    provider = RSSProvider(timeout_seconds=10)

    episodes = await provider.fetch_episodes(feed_url, max_results=1)

    assert len(episodes) == 1
