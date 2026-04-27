import pytest
from httpx import AsyncClient

from app.application.container import AppContainer
from app.domain.models import Lead, LeadEmailDraft
from tests.integration.test_dashboard_api import seed_dashboard_state


class FakeRewriteOpenAIProvider:
    def __init__(self) -> None:
        self.prompt_version = "v1.0-test"
        self.model = "gpt-4.1-2025-04-14"
        self.calls: list[dict[str, str]] = []

    async def generate_lead_draft(self, *, transcript_text: str, tone_instructions: str | None):
        raise NotImplementedError

    async def rewrite_email_draft(
        self,
        *,
        transcript_text: str,
        current_email_subject: str,
        current_email_body: str,
        user_instruction: str,
    ) -> LeadEmailDraft:
        self.calls.append(
            {
                "transcript_text": transcript_text,
                "current_email_subject": current_email_subject,
                "current_email_body": current_email_body,
                "user_instruction": user_instruction,
            }
        )
        return LeadEmailDraft(
            email_subject="Rewritten subject",
            email_body="Rewritten body",
        )


@pytest.mark.asyncio
async def test_rewrite_lead_updates_stored_subject_and_body(
    client: AsyncClient,
    app_container: AppContainer,
) -> None:
    seeded = await seed_dashboard_state(app_container)
    fake_provider = FakeRewriteOpenAIProvider()
    app_container.openai_provider = fake_provider

    response = await client.post(
        f"/api/leads/{seeded['leads']['one'].lead_id}/rewrite",
        json={"instruction": "Make it more concise and more executive."},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["lead_id"] == seeded["leads"]["one"].lead_id
    assert payload["email_subject"] == "Rewritten subject"
    assert payload["email_body"] == "Rewritten body"
    assert fake_provider.calls == [
        {
            "transcript_text": "Transcript one",
            "current_email_subject": "The four keyholes you mentioned",
            "current_email_body": "Draft one",
            "user_instruction": "Make it more concise and more executive.",
        }
    ]

    updated_detail = await client.get(f"/api/leads/{seeded['leads']['one'].lead_id}")
    assert updated_detail.status_code == 200
    assert updated_detail.json()["email_subject"] == "Rewritten subject"
    assert updated_detail.json()["email_body"] == "Rewritten body"


@pytest.mark.asyncio
async def test_rewrite_lead_returns_conflict_when_transcript_text_is_missing(
    client: AsyncClient,
    app_container: AppContainer,
) -> None:
    seeded = await seed_dashboard_state(app_container)
    fake_provider = FakeRewriteOpenAIProvider()
    app_container.openai_provider = fake_provider

    lead_without_transcript = Lead(
        run_id=seeded["runs"]["partial"].run_id,
        episode_id=seeded["episodes"]["three"].episode_id,
        guest_name="Dana Brooks",
        guest_company="Westview Health",
        role="COO",
        pain_point="Manual reconciliation across departments",
        memorable_quote="We close the month on three different truths.",
        email_subject="The three truths you mentioned",
        email_body="Draft missing transcript",
        prompt_version="v1.0",
        model_name="gpt-4.1-2025-04-14",
    )
    await app_container.lead_repository.create(lead_without_transcript)

    response = await client.post(
        f"/api/leads/{lead_without_transcript.lead_id}/rewrite",
        json={"instruction": "Make it more direct."},
    )

    assert response.status_code == 409
    assert "Transcript text is not available" in response.json()["detail"]
    assert fake_provider.calls == []


@pytest.mark.asyncio
async def test_rewrite_lead_returns_404_for_missing_lead(client: AsyncClient) -> None:
    response = await client.post(
        "/api/leads/missing-lead/rewrite",
        json={"instruction": "Shorten it."},
    )

    assert response.status_code == 404


@pytest.mark.asyncio
async def test_rewrite_lead_rejects_blank_instruction(
    client: AsyncClient,
    app_container: AppContainer,
) -> None:
    seeded = await seed_dashboard_state(app_container)

    response = await client.post(
        f"/api/leads/{seeded['leads']['one'].lead_id}/rewrite",
        json={"instruction": "   "},
    )

    assert response.status_code == 409
    assert "Add a rewrite instruction" in response.json()["detail"]
