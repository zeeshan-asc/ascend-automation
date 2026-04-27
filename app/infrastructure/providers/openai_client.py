from __future__ import annotations

import asyncio
import json
import logging
from typing import Any, TypeVar

import httpx
from pydantic import BaseModel

from app.domain.errors import OpenAIRefusalError
from app.domain.models import LeadDraft, LeadEmailDraft

logger = logging.getLogger(__name__)
ModelT = TypeVar("ModelT", bound=BaseModel)

ASCEND_PROMPT = """
You are a BD assistant for Ascend Analytics, a data engineering and AI company
that helps organizations build the data infrastructure and analytics layers they
need to operate intelligently. Ascend works vendor-agnostically across a
client's existing tech stack to unify disparate data sources, enable AI-powered
workflows, and surface actionable insights without requiring a costly overhaul
of current systems.

Read the podcast transcript and do two things:
1. Identify the guest and the most relevant outreach hooks.
2. Write a highly personalized outreach email from Ascend to that guest.

Rules:
- Ground the email in the guest's specific business problem or domain, whether
  that is operations, logistics, healthcare, finance, retail, or anything else.
- Tailor the value proposition to how Ascend's data engineering and AI
  capabilities address that specific problem.
- Reflect the guest's own language and framing where useful.
- The subject line must feel like it was written specifically for this person.
  It should reference a specific pain point, goal, or idea they voiced in the
  transcript, so that reading it feels like someone actually listened. Never
  mention Ascend. Never use generic phrases like "partnership opportunity" or
  "quick question." Make it so relevant and specific that ignoring it feels
  like a mistake.
- Keep the email between 150 and 200 words.
- Do not use generic sales language.
- Return only the fields requested by the schema.
- Do not use en-dashes or em-dashes at all.
""".strip()

ASCEND_REWRITE_PROMPT = """
You are revising an existing outreach email draft for Ascend.
Use the transcript as the source of truth and apply the user's rewrite instruction.

Rules:
- Rewrite the subject line and email body only.
- Keep the draft specific to the transcript and the guest.
- Do not invent facts that are not supported by the transcript.
- Respect the user's rewrite instruction unless it conflicts with the transcript.
- Keep the subject line specific and never mention Ascend in it.
- Keep the email body between 150 and 200 words.
- Return only the fields requested by the schema.
- Do not use en-dashes or em-dashes at all.
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

    def build_rewrite_request_payload(
        self,
        *,
        transcript_text: str,
        current_email_subject: str,
        current_email_body: str,
        user_instruction: str,
    ) -> dict[str, Any]:
        return {
            "model": self._model,
            "instructions": ASCEND_REWRITE_PROMPT,
            "input": [
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "input_text",
                            "text": (
                                "Rewrite instruction:\n"
                                f"{user_instruction.strip()}\n\n"
                                "Current draft subject:\n"
                                f"{current_email_subject}\n\n"
                                "Current draft body:\n"
                                f"{current_email_body}\n\n"
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
                    "name": "LeadEmailDraft",
                    "strict": True,
                    "schema": {
                        "type": "object",
                        "properties": {
                            "email_subject": {"type": "string"},
                            "email_body": {"type": "string"},
                        },
                        "required": ["email_subject", "email_body"],
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
        response_payload = await self._post_response(payload)
        draft = self._parse_response(response_payload, LeadDraft)
        logger.info(
            "openai.generate.completed model=%s prompt_version=%s guest_name=%s",
            self._model,
            self._prompt_version,
            draft.guest_name,
        )
        return draft

    async def rewrite_email_draft(
        self,
        *,
        transcript_text: str,
        current_email_subject: str,
        current_email_body: str,
        user_instruction: str,
    ) -> LeadEmailDraft:
        logger.info(
            "openai.rewrite.started model=%s prompt_version=%s "
            "transcript_chars=%s instruction_chars=%s",
            self._model,
            self._prompt_version,
            len(transcript_text),
            len(user_instruction),
        )
        payload = self.build_rewrite_request_payload(
            transcript_text=transcript_text,
            current_email_subject=current_email_subject,
            current_email_body=current_email_body,
            user_instruction=user_instruction,
        )
        response_payload = await self._post_response(payload)
        rewritten = self._parse_response(response_payload, LeadEmailDraft)
        logger.info(
            "openai.rewrite.completed model=%s prompt_version=%s subject_chars=%s",
            self._model,
            self._prompt_version,
            len(rewritten.email_subject),
        )
        return rewritten

    async def _post_response(self, payload: dict[str, Any]) -> dict[str, Any]:
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
        return dict(response.json())

    def _parse_response(self, payload: dict[str, Any], model: type[ModelT]) -> ModelT:
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
                    return model.model_validate(json.loads(content_item["text"]))
        if payload.get("output_text"):
            return model.model_validate(json.loads(payload["output_text"]))
        raise ValueError("OpenAI response did not contain structured output text.")
