import pytest
import respx
from httpx import Response

from app.domain.enums import SourceKind
from app.domain.errors import SourceFetchError
from app.infrastructure.providers.rss import RSSProvider
from app.infrastructure.providers.source_resolver import (
    DirectAudioResolver,
    EpisodePageResolver,
    SourceResolver,
)


@pytest.mark.asyncio
@respx.mock
async def test_direct_audio_resolver_accepts_public_audio_urls() -> None:
    audio_url = "https://cdn.example.com/episode-1.mp3"
    respx.head(audio_url).mock(
        return_value=Response(
            200,
            headers={"content-type": "audio/mpeg", "content-length": "12345"},
        ),
    )
    resolver = DirectAudioResolver(timeout_seconds=10)

    episodes = await resolver.resolve_audio_url(audio_url)

    assert len(episodes) == 1
    assert episodes[0].audio_url == audio_url
    assert episodes[0].source_kind == SourceKind.AUDIO_FILE
    assert episodes[0].dedupe_key == f"audio:{audio_url}"


@pytest.mark.asyncio
@respx.mock
async def test_episode_page_resolver_extracts_og_audio_metadata() -> None:
    page_url = "https://podcast.show/1461261/episode/153801033/"
    html = """
    <html>
      <head>
        <title>How CVS Health Is Using Agentic AI Twins</title>
        <meta
          property="og:title"
          content="How CVS Health Is Using Agentic AI Twins to Transform Patient Experience"
        />
        <meta property="og:audio" content="https://media.example.com/episode.mp3" />
        <meta property="article:published_time" content="2026-04-10T00:00:00Z" />
      </head>
      <body><h1>Episode</h1></body>
    </html>
    """
    respx.get(page_url).mock(
        return_value=Response(200, text=html, headers={"content-type": "text/html"}),
    )
    resolver = EpisodePageResolver(timeout_seconds=10)

    episodes = await resolver.resolve_episode_page(page_url)

    assert len(episodes) == 1
    assert (
        episodes[0].title
        == "How CVS Health Is Using Agentic AI Twins to Transform Patient Experience"
    )
    assert episodes[0].audio_url == "https://media.example.com/episode.mp3"
    assert episodes[0].episode_url == page_url
    assert episodes[0].source_kind == SourceKind.EPISODE_PAGE


@pytest.mark.asyncio
@respx.mock
async def test_source_resolver_auto_detects_episode_pages_after_invalid_feed_parse() -> None:
    source_url = "https://podcast.show/1461261/episode/153801033/"
    html = """
    <html>
      <head>
        <title>Episode page</title>
        <meta property="og:audio" content="https://media.example.com/episode.mp3" />
      </head>
    </html>
    """
    respx.get(source_url).mock(
        return_value=Response(200, text=html, headers={"content-type": "text/html"}),
    )
    resolver = SourceResolver(
        rss_resolver=RSSProvider(timeout_seconds=10),
        direct_audio_resolver=DirectAudioResolver(timeout_seconds=10),
        episode_page_resolver=EpisodePageResolver(timeout_seconds=10),
    )

    episodes = await resolver.resolve_source(
        source_url=source_url,
        source_kind=SourceKind.AUTO,
        max_results=5,
    )

    assert len(episodes) == 1
    assert episodes[0].source_kind == SourceKind.EPISODE_PAGE
    assert episodes[0].audio_url == "https://media.example.com/episode.mp3"


@pytest.mark.asyncio
@respx.mock
async def test_episode_page_resolver_rejects_pages_without_audio() -> None:
    page_url = "https://example.com/no-audio"
    respx.get(page_url).mock(
        return_value=Response(
            200,
            text="<html><head><title>No audio</title></head><body>Missing</body></html>",
            headers={"content-type": "text/html"},
        ),
    )
    resolver = EpisodePageResolver(timeout_seconds=10)

    with pytest.raises(SourceFetchError) as exc_info:
        await resolver.resolve_episode_page(page_url)

    assert exc_info.value.reason_code == "episode_audio_not_found"
