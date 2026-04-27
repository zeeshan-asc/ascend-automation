from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

import httpx

from app.domain.errors import OpenAIRefusalError
from app.domain.models import LeadDraft

logger = logging.getLogger(__name__)

ASCEND_PROMPT = """
You are a BD assistant for Ascend, a healthcare data and analytics company.
Ascend sits vendor-agnostically across existing hospital and health system
infrastructure to create a unified analytics layer that tracks patient flow,
clinical outcomes, and risk without requiring a global EMR overhaul.

Read the podcast transcript and do two things:
1. Identify the guest and the most relevant outreach hooks.
2. Write a highly personalized outreach email from Ascend to that guest.

Rules:
- Be specific to the transcript and the guest.
- Reflect the guest's own language where useful.
- Keep the subject line specific and never mention Ascend in it.
- Keep the email between 150 and 200 words.
- Do not use generic sales language.
- Return only the fields requested by the schema.
""".strip()


class OpenAIProvider:
    def __init__(
        self,
        *,
        api_key: str,
        model: str,
        prompt_version: str,
        max_inflight: int,
    ) -> None:
        self._api_key = api_key
        self._model = model
        self._prompt_version = prompt_version
        self._semaphore = asyncio.Semaphore(max_inflight)

    @property
    def prompt_version(self) -> str:
        return self._prompt_version

    @property
    def model(self) -> str:
        return self._model

    def build_request_payload(
        self,
        *,
        transcript_text: str,
        tone_instructions: str | None,
    ) -> dict[str, Any]:
        tone_block = (
            tone_instructions.strip()
            if tone_instructions
            else "No additional tone instructions provided."
        )
        return {
            "model": self._model,
            "instructions": ASCEND_PROMPT,
            "input": [
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "input_text",
                            "text": (
                                "Tone instructions:\n"
                                f"{tone_block}\n\n"
                                "Transcript:\n"
                                f"{transcript_text}"
                            ),
                        }
                    ],
                }
            ],
            "text": {
                "format": {
                    "type": "json_schema",
                    "name": "LeadDraft",
                    "strict": True,
                    "schema": {
                        "type": "object",
                        "properties": {
                            "guest_name": {"type": "string"},
                            "guest_company": {"type": "string"},
                            "role": {"type": "string"},
                            "pain_point": {"type": "string"},
                            "memorable_quote": {"type": "string"},
                            "email_subject": {"type": "string"},
                            "email_body": {"type": "string"},
                        },
                        "required": [
                            "guest_name",
                            "guest_company",
                            "role",
                            "pain_point",
                            "memorable_quote",
                            "email_subject",
                            "email_body",
                        ],
                        "additionalProperties": False,
                    },
                }
            },
        }

    async def generate_lead_draft(
        self,
        *,
        transcript_text: str,
        tone_instructions: str | None,
    ) -> LeadDraft:
        logger.info(
            "openai.generate.started model=%s prompt_version=%s transcript_chars=%s",
            self._model,
            self._prompt_version,
            len(transcript_text),
        )
        payload = self.build_request_payload(
            transcript_text=transcript_text,
            tone_instructions=tone_instructions,
        )
        async with self._semaphore, httpx.AsyncClient(timeout=120) as client:
            response = await client.post(
                "https://api.openai.com/v1/responses",
                headers={
                    "Authorization": f"Bearer {self._api_key}",
                    "Content-Type": "application/json",
                },
                json=payload,
            )
            response.raise_for_status()
        draft = self._parse_response(response.json())
        logger.info(
            "openai.generate.completed model=%s prompt_version=%s guest_name=%s",
            self._model,
            self._prompt_version,
            draft.guest_name,
        )
        return draft

    def _parse_response(self, payload: dict[str, Any]) -> LeadDraft:
        for output_item in payload.get("output", []):
            if output_item.get("type") == "refusal":
                logger.error("openai.generate.refusal")
                raise OpenAIRefusalError(
                    str(output_item.get("refusal", "OpenAI refused the request")),
                )
            for content_item in output_item.get("content", []):
                if content_item.get("type") == "refusal":
                    logger.error("openai.generate.refusal")
                    raise OpenAIRefusalError(
                        str(content_item.get("text", "OpenAI refused the request")),
                    )
                if content_item.get("type") == "output_text":
                    return LeadDraft.model_validate(json.loads(content_item["text"]))
        if payload.get("output_text"):
            return LeadDraft.model_validate(json.loads(payload["output_text"]))
        raise ValueError("OpenAI response did not contain structured output text.")
