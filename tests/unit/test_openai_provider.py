import json

import pytest
import respx
from httpx import Response
from pydantic import ValidationError

from app.domain.errors import OpenAIRefusalError
from app.infrastructure.providers.openai_client import ASCEND_PROMPT, OpenAIProvider


@pytest.mark.asyncio
@respx.mock
async def test_openai_provider_builds_payload_with_instructions_and_input() -> None:
    provider = OpenAIProvider(
        api_key="openai-key",
        model="gpt-4.1-2025-04-14",
        prompt_version="v1.0-test",
        max_inflight=2,
    )
    payload = provider.build_request_payload(
        transcript_text="Transcript body",
        tone_instructions="Use a concise tone",
    )

    assert payload["instructions"] == ASCEND_PROMPT
    assert "Use a concise tone" in payload["input"][0]["content"][0]["text"]
    assert "Use a concise tone" not in payload["instructions"]


@pytest.mark.asyncio
@respx.mock
async def test_openai_provider_returns_structured_lead_draft() -> None:
    provider = OpenAIProvider(
        api_key="openai-key",
        model="gpt-4.1-2025-04-14",
        prompt_version="v1.0-test",
        max_inflight=2,
    )
    response_payload = {
        "output": [
            {
                "type": "message",
                "content": [
                    {
                        "type": "output_text",
                        "text": json.dumps(
                            {
                                "guest_name": "Dr. Chen",
                                "guest_company": "Ascend",
                                "role": "CMO",
                                "pain_point": "Broken patient flow",
                                "memorable_quote": "Four keyholes",
                                "email_subject": "The four keyholes you mentioned",
                                "email_body": "Email body",
                            },
                        ),
                    }
                ],
            }
        ]
    }
    respx.post("https://api.openai.com/v1/responses").mock(
        return_value=Response(200, json=response_payload),
    )

    draft = await provider.generate_lead_draft(
        transcript_text="Transcript body",
        tone_instructions="Be concise",
    )

    assert draft.guest_name == "Dr. Chen"
    assert draft.email_subject == "The four keyholes you mentioned"


@pytest.mark.asyncio
@respx.mock
async def test_openai_provider_raises_on_refusal() -> None:
    provider = OpenAIProvider(
        api_key="openai-key",
        model="gpt-4.1-2025-04-14",
        prompt_version="v1.0-test",
        max_inflight=2,
    )
    response_payload = {"output": [{"type": "refusal", "refusal": "I can't help with that"}]}
    respx.post("https://api.openai.com/v1/responses").mock(
        return_value=Response(200, json=response_payload),
    )

    with pytest.raises(OpenAIRefusalError):
        await provider.generate_lead_draft(
            transcript_text="Transcript body",
            tone_instructions=None,
        )


@pytest.mark.asyncio
@respx.mock
async def test_openai_provider_fails_on_malformed_output() -> None:
    provider = OpenAIProvider(
        api_key="openai-key",
        model="gpt-4.1-2025-04-14",
        prompt_version="v1.0-test",
        max_inflight=2,
    )
    response_payload = {
        "output": [{"type": "message", "content": [{"type": "output_text", "text": "{}"}]}],
    }
    respx.post("https://api.openai.com/v1/responses").mock(
        return_value=Response(200, json=response_payload),
    )

    with pytest.raises(ValidationError):
        await provider.generate_lead_draft(
            transcript_text="Transcript body",
            tone_instructions=None,
        )


def test_openai_provider_exposes_prompt_version() -> None:
    provider = OpenAIProvider(
        api_key="openai-key",
        model="gpt-4.1-2025-04-14",
        prompt_version="v1.0-test",
        max_inflight=2,
    )
    assert provider.prompt_version == "v1.0-test"
