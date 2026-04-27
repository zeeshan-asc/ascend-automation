from __future__ import annotations

import asyncio
import logging
from typing import Any

import httpx

from app.domain.enums import TranscriptStatus
from app.domain.errors import TranscriptError, TranscriptTimeoutError
from app.domain.models import TranscriptResult

logger = logging.getLogger(__name__)


class AssemblyAIProvider:
    def __init__(
        self,
        *,
        api_key: str,
        base_url: str,
        poll_interval_seconds: int,
        timeout_seconds: int,
        max_inflight: int,
    ) -> None:
        self._api_key = api_key
        self._base_url = base_url.rstrip("/")
        self._poll_interval_seconds = poll_interval_seconds
        self._timeout_seconds = timeout_seconds
        self._semaphore = asyncio.Semaphore(max_inflight)

    async def submit_transcription(self, audio_url: str) -> str:
        logger.info("assemblyai.submit.started audio_url=%s", audio_url)
        async with self._semaphore, httpx.AsyncClient(timeout=self._timeout_seconds) as client:
            response = await client.post(
                f"{self._base_url}/v2/transcript",
                headers={"authorization": self._api_key},
                json={
                    "audio_url": audio_url,
                    "speech_models": ["universal-3-pro", "universal-2"],
                },
            )
            response.raise_for_status()
        payload = response.json()
        logger.info("assemblyai.submit.completed job_id=%s", payload["id"])
        return str(payload["id"])

    async def poll_transcription(self, job_id: str) -> TranscriptResult:
        deadline = asyncio.get_running_loop().time() + self._timeout_seconds
        logger.info("assemblyai.poll.started job_id=%s", job_id)
        async with self._semaphore, httpx.AsyncClient(timeout=self._timeout_seconds) as client:
            while True:
                response = await client.get(
                    f"{self._base_url}/v2/transcript/{job_id}",
                    headers={"authorization": self._api_key},
                )
                response.raise_for_status()
                payload: dict[str, Any] = response.json()
                status = payload.get("status")
                if status == TranscriptStatus.COMPLETED.value:
                    logger.info("assemblyai.poll.completed job_id=%s", job_id)
                    return TranscriptResult(
                        assemblyai_job_id=job_id,
                        status=TranscriptStatus.COMPLETED,
                        text=payload.get("text"),
                        provider_metadata=payload,
                    )
                if status == "error":
                    error_message = str(payload.get("error", "AssemblyAI transcription failed"))
                    logger.error("assemblyai.poll.failed job_id=%s error=%s", job_id, error_message)
                    raise TranscriptError(error_message)
                if asyncio.get_running_loop().time() > deadline:
                    logger.error("assemblyai.poll.timeout job_id=%s", job_id)
                    raise TranscriptTimeoutError(
                        f"AssemblyAI transcription timed out for job {job_id}",
                    )
                await asyncio.sleep(self._poll_interval_seconds)
