from __future__ import annotations

import logging

from app.config import Settings
from app.domain.errors import SourceFetchError
from app.domain.interfaces import RunRepositoryProtocol, SourceResolverProtocol
from app.domain.models import AuthenticatedUser, Run, SubmissionRequest, utcnow

logger = logging.getLogger(__name__)


class SubmissionService:
    def __init__(
        self,
        settings: Settings,
        run_repository: RunRepositoryProtocol,
        source_resolver: SourceResolverProtocol,
    ) -> None:
        self._settings = settings
        self._run_repository = run_repository
        self._source_resolver = source_resolver

    async def create_submission(
        self,
        request: SubmissionRequest,
        *,
        current_user: AuthenticatedUser,
    ) -> Run:
        resolved_source_url = str(request.source_url)
        try:
            resolved_items = await self._source_resolver.resolve_source(
                source_url=resolved_source_url,
                source_kind=request.source_kind,
                max_results=self._settings.max_episodes_per_run,
            )
        except SourceFetchError as exc:
            logger.warning(
                "submission.rejected source_url=%s source_kind=%s "
                "reason_code=%s detail=%s submitted_by=%s",
                resolved_source_url,
                request.source_kind,
                exc.reason_code,
                str(exc),
                current_user.email,
            )
            raise

        submitted_at = request.submitted_at
        resolved_source_kind = (
            resolved_items[0].source_kind if resolved_items else request.source_kind
        )
        run = Run(
            source_url=resolved_source_url,
            source_kind=resolved_source_kind,
            submitted_by=current_user.name,
            submitted_by_email=current_user.email,
            tone_instructions=request.tone_instructions,
            submitted_at=submitted_at,
            created_at=utcnow(),
            updated_at=utcnow(),
        )
        created = await self._run_repository.create(run)
        logger.info(
            "submission.created run_id=%s source_url=%s source_kind=%s submitted_by=%s",
            created.run_id,
            created.source_url,
            created.source_kind,
            created.submitted_by_email,
        )
        return created

    def build_dashboard_url(self, run_id: str) -> str:
        return f"{self._settings.app_base_url}/dashboard?run_id={run_id}"
