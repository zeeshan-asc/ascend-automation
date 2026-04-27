from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from app.domain.enums import LeadStatus, RunItemStatus, RunStatus, TranscriptStatus
from app.domain.models import LeadDraft, Run, SubmissionRequest


def test_status_enum_values_are_stable() -> None:
    assert RunStatus.QUEUED.value == "queued"
    assert RunItemStatus.DONE.value == "done"
    assert TranscriptStatus.COMPLETED.value == "completed"
    assert LeadStatus.GENERATED.value == "generated"


def test_submission_request_validates_user_payload() -> None:
    submission = SubmissionRequest(
        user_name="Zeesh",
        user_email="zeesh@example.com",
        rss_url="https://example.com/feed.xml",
        tone_instructions="Keep it crisp",
        submitted_at=datetime.now(UTC),
    )
    assert submission.user_name == "Zeesh"
    assert submission.user_email == "zeesh@example.com"


def test_run_defaults_to_queued_status() -> None:
    run = Run(
        rss_url="https://example.com/feed.xml",
        submitted_by="User",
        submitted_by_email="user@example.com",
        submitted_at=datetime.now(UTC),
    )
    assert run.status == RunStatus.QUEUED
    assert run.total_items == 0


def test_lead_draft_requires_all_fields() -> None:
    with pytest.raises(ValidationError):
        LeadDraft(guest_name="Only One Field")
