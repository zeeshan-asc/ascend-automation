from __future__ import annotations

import logging

from app.config import Settings
from app.domain.errors import FeedFetchError
from app.domain.interfaces import RSSProviderProtocol, RunRepositoryProtocol
from app.domain.models import AuthenticatedUser, Run, SubmissionRequest, utcnow

logger = logging.getLogger(__name__)


class SubmissionService:
    def __init__(
        self,
        settings: Settings,
        run_repository: RunRepositoryProtocol,
        rss_provider: RSSProviderProtocol,
    ) -> None:
        self._settings = settings
        self._run_repository = run_repository
        self._rss_provider = rss_provider

    async def create_submission(
        self,
        request: SubmissionRequest,
        *,
        current_user: AuthenticatedUser,
    ) -> Run:
        try:
            await self._rss_provider.fetch_episodes(
                str(request.rss_url),
                self._settings.max_episodes_per_run,
            )
        except FeedFetchError as exc:
            logger.warning(
                "submission.rejected rss_url=%s reason_code=%s detail=%s submitted_by=%s",
                request.rss_url,
                exc.reason_code,
                str(exc),
                current_user.email,
            )
            raise

        submitted_at = request.submitted_at
        run = Run(
            rss_url=str(request.rss_url),
            submitted_by=current_user.name,
            submitted_by_email=current_user.email,
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
