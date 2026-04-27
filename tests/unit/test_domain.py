from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from app.domain.enums import LeadStatus, RunItemStatus, RunStatus, TranscriptStatus
from app.domain.models import LeadDraft, Run, SubmissionRequest, User


def test_status_enum_values_are_stable() -> None:
    assert RunStatus.QUEUED.value == "queued"
    assert RunItemStatus.DONE.value == "done"
    assert TranscriptStatus.COMPLETED.value == "completed"
    assert LeadStatus.GENERATED.value == "generated"


def test_submission_request_validates_feed_payload() -> None:
    submission = SubmissionRequest(
        rss_url="https://example.com/feed.xml",
        tone_instructions="Keep it crisp",
        submitted_at=datetime.now(UTC),
    )
    assert str(submission.rss_url) == "https://example.com/feed.xml"
    assert submission.tone_instructions == "Keep it crisp"


def test_user_exposes_authenticated_view() -> None:
    user = User(
        name="Zeesh",
        email="zeesh@ascendanalytics.co",
        password_hash="hash",
        password_salt="salt",
    )

    authenticated_user = user.to_authenticated_user()

    assert authenticated_user.user_id == user.user_id
    assert authenticated_user.email == "zeesh@ascendanalytics.co"


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
