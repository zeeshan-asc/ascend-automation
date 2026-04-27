from __future__ import annotations

import logging

from app.config import Settings
from app.domain.interfaces import RunRepositoryProtocol
from app.domain.models import Run, SubmissionRequest, utcnow

logger = logging.getLogger(__name__)


class SubmissionService:
    def __init__(self, settings: Settings, run_repository: RunRepositoryProtocol) -> None:
        self._settings = settings
        self._run_repository = run_repository

    async def create_submission(self, request: SubmissionRequest) -> Run:
        submitted_at = request.submitted_at
        run = Run(
            rss_url=str(request.rss_url),
            submitted_by=request.user_name,
            submitted_by_email=request.user_email,
            tone_instructions=request.tone_instructions,
            submitted_at=submitted_at,
            created_at=utcnow(),
            updated_at=utcnow(),
        )
        created = await self._run_repository.create(run)
        logger.info(
            "submission.created run_id=%s rss_url=%s submitted_by=%s",
            created.run_id,
            created.rss_url,
            created.submitted_by_email,
        )
        return created

    def build_dashboard_url(self, run_id: str) -> str:
        return f"{self._settings.app_base_url}/dashboard?run_id={run_id}"
