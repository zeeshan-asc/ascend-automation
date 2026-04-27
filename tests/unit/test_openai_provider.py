import json

import httpx
import pytest
import respx
from httpx import Response
from pydantic import ValidationError

import app.infrastructure.providers.openai_client as openai_client_module
from app.domain.errors import OpenAIRefusalError
from app.infrastructure.providers.openai_client import (
    ASCEND_PROMPT,
    ASCEND_REWRITE_PROMPT,
    OpenAIProvider,
)


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


def test_openai_provider_builds_rewrite_payload_with_instruction_and_existing_draft() -> None:
    provider = OpenAIProvider(
        api_key="openai-key",
        model="gpt-4.1-2025-04-14",
        prompt_version="v1.0-test",
        max_inflight=2,
    )

    payload = provider.build_rewrite_request_payload(
        transcript_text="Transcript body",
        current_email_subject="Current subject",
        current_email_body="Current body",
        user_instruction="Make it shorter and sharper",
    )

    assert payload["instructions"] == ASCEND_REWRITE_PROMPT
    text_block = payload["input"][0]["content"][0]["text"]
    assert "Make it shorter and sharper" in text_block
    assert "Current subject" in text_block
    assert "Current body" in text_block
    assert "Transcript body" in text_block


@pytest.mark.asyncio
@respx.mock
async def test_openai_provider_returns_structured_email_rewrite() -> None:
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
                                "email_subject": "Updated subject",
                                "email_body": "Updated body",
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

    draft = await provider.rewrite_email_draft(
        transcript_text="Transcript body",
        current_email_subject="Current subject",
        current_email_body="Current body",
        user_instruction="Make it shorter and sharper",
    )

    assert draft.email_subject == "Updated subject"
    assert draft.email_body == "Updated body"


@pytest.mark.asyncio
@respx.mock
async def test_openai_provider_waits_and_retries_after_rate_limit(monkeypatch) -> None:
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
    route = respx.post("https://api.openai.com/v1/responses").mock(
        side_effect=[
            Response(429, json={"error": {"message": "rate limit"}}),
            Response(200, json=response_payload),
        ],
    )
    sleep_calls: list[int] = []

    async def fake_sleep(duration: float) -> None:
        sleep_calls.append(int(duration))

    monkeypatch.setattr(openai_client_module.asyncio, "sleep", fake_sleep)

    draft = await provider.generate_lead_draft(
        transcript_text="Transcript body",
        tone_instructions=None,
    )

    assert draft.guest_name == "Dr. Chen"
    assert sleep_calls == [openai_client_module.OPENAI_RATE_LIMIT_RETRY_SECONDS]
    assert route.call_count == 2


@pytest.mark.asyncio
@respx.mock
async def test_openai_provider_raises_after_exhausting_rate_limit_retries(monkeypatch) -> None:
    provider = OpenAIProvider(
        api_key="openai-key",
        model="gpt-4.1-2025-04-14",
        prompt_version="v1.0-test",
        max_inflight=2,
    )
    route = respx.post("https://api.openai.com/v1/responses").mock(
        side_effect=[
            Response(429, json={"error": {"message": "rate limit"}}),
            Response(429, json={"error": {"message": "rate limit"}}),
            Response(429, json={"error": {"message": "rate limit"}}),
            Response(429, json={"error": {"message": "rate limit"}}),
        ],
    )
    sleep_calls: list[int] = []

    async def fake_sleep(duration: float) -> None:
        sleep_calls.append(int(duration))

    monkeypatch.setattr(openai_client_module.asyncio, "sleep", fake_sleep)

    with pytest.raises(httpx.HTTPStatusError):
        await provider.generate_lead_draft(
            transcript_text="Transcript body",
            tone_instructions=None,
        )

    assert sleep_calls == [
        openai_client_module.OPENAI_RATE_LIMIT_RETRY_SECONDS,
        openai_client_module.OPENAI_RATE_LIMIT_RETRY_SECONDS,
        openai_client_module.OPENAI_RATE_LIMIT_RETRY_SECONDS,
    ]
    assert route.call_count == 4
