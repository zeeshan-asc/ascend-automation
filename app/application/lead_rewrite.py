from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.domain.errors import InvalidOperationError, ResourceNotFoundError
from app.domain.interfaces import (
    LeadRepositoryProtocol,
    OpenAIProviderProtocol,
    TranscriptRepositoryProtocol,
)
from app.domain.models import utcnow


class ApiModel(BaseModel):
    model_config = ConfigDict(use_enum_values=True)


class LeadRewriteRequest(BaseModel):
    instruction: str = Field(min_length=1, max_length=4000)


class LeadRewriteResult(ApiModel):
    lead_id: str
    email_subject: str
    email_body: str
    updated_at: datetime


class LeadRewriteService:
    def __init__(
        self,
        *,
        lead_repository: LeadRepositoryProtocol,
        transcript_repository: TranscriptRepositoryProtocol,
        openai_provider: OpenAIProviderProtocol,
    ) -> None:
        self._lead_repository = lead_repository
        self._transcript_repository = transcript_repository
        self._openai_provider = openai_provider

    async def rewrite_email(
        self,
        *,
        lead_id: str,
        instruction: str,
    ) -> LeadRewriteResult:
        normalized_instruction = instruction.strip()
        if not normalized_instruction:
            raise InvalidOperationError("Add a rewrite instruction before sending it to OpenAI.")

        lead = await self._lead_repository.get_by_lead_id(lead_id)
        if lead is None:
            raise ResourceNotFoundError(f"Lead {lead_id} was not found.")

        transcript = await self._transcript_repository.get_by_episode_id(lead.episode_id)
        if transcript is None or not transcript.text:
            raise InvalidOperationError(
                "Transcript text is not available for this episode, so the draft "
                "cannot be rewritten yet.",
            )

        rewritten = await self._openai_provider.rewrite_email_draft(
            transcript_text=transcript.text,
            current_email_subject=lead.email_subject,
            current_email_body=lead.email_body,
            user_instruction=normalized_instruction,
        )
        updated = await self._lead_repository.update_email_draft(
            lead_id=lead_id,
            email_subject=rewritten.email_subject,
            email_body=rewritten.email_body,
            now=utcnow(),
        )
        if updated is None:
            raise ResourceNotFoundError(f"Lead {lead_id} was not found.")

        return LeadRewriteResult(
            lead_id=updated.lead_id,
            email_subject=updated.email_subject,
            email_body=updated.email_body,
            updated_at=updated.updated_at,
        )
