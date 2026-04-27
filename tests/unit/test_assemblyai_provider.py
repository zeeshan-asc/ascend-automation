import asyncio

import httpx
import pytest
import respx
from httpx import Response

from app.domain.enums import TranscriptStatus
from app.domain.errors import TranscriptError, TranscriptTimeoutError
from app.infrastructure.providers.assemblyai import AssemblyAIProvider


@pytest.mark.asyncio
@respx.mock
async def test_assemblyai_submit_and_poll_success() -> None:
    provider = AssemblyAIProvider(
        api_key="assembly-key",
        base_url="https://api.assemblyai.com",
        poll_interval_seconds=0,
        timeout_seconds=10,
        max_inflight=2,
    )
    respx.post("https://api.assemblyai.com/v2/transcript").mock(
        return_value=Response(200, json={"id": "job-1", "status": "queued"}),
    )
    respx.get("https://api.assemblyai.com/v2/transcript/job-1").mock(
        side_effect=[
            Response(200, json={"status": "processing"}),
            Response(200, json={"status": "completed", "text": "Transcript body"}),
        ],
    )

    job_id = await provider.submit_transcription("https://cdn.example.com/audio.mp3")
    result = await provider.poll_transcription(job_id)

    assert job_id == "job-1"
    assert result.status == TranscriptStatus.COMPLETED
    assert result.text == "Transcript body"


@pytest.mark.asyncio
@respx.mock
async def test_assemblyai_raises_on_provider_error() -> None:
    provider = AssemblyAIProvider(
        api_key="assembly-key",
        base_url="https://api.assemblyai.com",
        poll_interval_seconds=0,
        timeout_seconds=10,
        max_inflight=2,
    )
    respx.get("https://api.assemblyai.com/v2/transcript/job-error").mock(
        return_value=Response(200, json={"status": "error", "error": "bad audio"}),
    )

    with pytest.raises(TranscriptError):
        await provider.poll_transcription("job-error")


@pytest.mark.asyncio
@respx.mock
async def test_assemblyai_timeout_is_raised() -> None:
    provider = AssemblyAIProvider(
        api_key="assembly-key",
        base_url="https://api.assemblyai.com",
        poll_interval_seconds=0,
        timeout_seconds=0,
        max_inflight=2,
    )
    respx.get("https://api.assemblyai.com/v2/transcript/job-timeout").mock(
        return_value=Response(200, json={"status": "processing"}),
    )

    with pytest.raises(TranscriptTimeoutError):
        await provider.poll_transcription("job-timeout")


@pytest.mark.asyncio
@respx.mock
async def test_assemblyai_uses_configured_eu_base_url() -> None:
    provider = AssemblyAIProvider(
        api_key="assembly-key",
        base_url="https://api.eu.assemblyai.com",
        poll_interval_seconds=0,
        timeout_seconds=10,
        max_inflight=2,
    )
    route = respx.post("https://api.eu.assemblyai.com/v2/transcript").mock(
        return_value=Response(200, json={"id": "job-eu"}),
    )

    job_id = await provider.submit_transcription("https://cdn.example.com/audio.mp3")

    assert route.called
    assert job_id == "job-eu"


@pytest.mark.asyncio
async def test_assemblyai_inflight_limit_is_enforced(monkeypatch: pytest.MonkeyPatch) -> None:
    provider = AssemblyAIProvider(
        api_key="assembly-key",
        base_url="https://api.assemblyai.com",
        poll_interval_seconds=0,
        timeout_seconds=10,
        max_inflight=1,
    )
    active = 0
    max_seen = 0

    async def fake_post(self: httpx.AsyncClient, *args, **kwargs) -> Response:
        nonlocal active, max_seen
        active += 1
        max_seen = max(max_seen, active)
        await asyncio.sleep(0.01)
        active -= 1
        request = httpx.Request("POST", "https://api.assemblyai.com/v2/transcript")
        return Response(200, json={"id": "job-limit"}, request=request)

    monkeypatch.setattr(httpx.AsyncClient, "post", fake_post)

    await asyncio.gather(
        provider.submit_transcription("https://cdn.example.com/a.mp3"),
        provider.submit_transcription("https://cdn.example.com/b.mp3"),
    )

    assert max_seen == 1
