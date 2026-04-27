from __future__ import annotations

import asyncio
import logging
from datetime import timedelta

from app.config import Settings
from app.domain.enums import RunItemStatus, RunStatus, TranscriptStatus
from app.domain.interfaces import (
    AssemblyAIProviderProtocol,
    EpisodeRepositoryProtocol,
    LeadRepositoryProtocol,
    OpenAIProviderProtocol,
    RSSProviderProtocol,
    RunItemRepositoryProtocol,
    RunRepositoryProtocol,
    TranscriptRepositoryProtocol,
)
from app.domain.models import Episode, Lead, Run, RunItem, Transcript, utcnow

logger = logging.getLogger(__name__)

FINALIZED_RUN_ITEM_STATUSES = {RunItemStatus.DONE.value, RunItemStatus.REUSED.value}


class PipelineOrchestrator:
    def __init__(
        self,
        *,
        settings: Settings,
        run_repository: RunRepositoryProtocol,
        episode_repository: EpisodeRepositoryProtocol,
        run_item_repository: RunItemRepositoryProtocol,
        transcript_repository: TranscriptRepositoryProtocol,
        lead_repository: LeadRepositoryProtocol,
        rss_provider: RSSProviderProtocol,
        assemblyai_provider: AssemblyAIProviderProtocol,
        openai_provider: OpenAIProviderProtocol,
    ) -> None:
        self._settings = settings
        self._run_repository = run_repository
        self._episode_repository = episode_repository
        self._run_item_repository = run_item_repository
        self._transcript_repository = transcript_repository
        self._lead_repository = lead_repository
        self._rss_provider = rss_provider
        self._assemblyai_provider = assemblyai_provider
        self._openai_provider = openai_provider

    async def process_run(self, *, run_id: str, worker_id: str) -> Run | None:
        run = await self._run_repository.get_by_run_id(run_id)
        if run is None:
            return None
        logger.info(
            "pipeline.run.started run_id=%s worker_id=%s rss_url=%s",
            run_id,
            worker_id,
            run.rss_url,
        )
        await self._run_repository.mark_running(run_id, utcnow())
        try:
            all_items, items_to_process = await self._prepare_run_items(run=run)
        except Exception as exc:
            await self._run_repository.finalize(
                run_id=run_id,
                status=RunStatus.FAILED,
                total_items=0,
                completed_items=0,
                failed_items=0,
                error=str(exc),
                now=utcnow(),
            )
            logger.exception("pipeline.run.failed run_id=%s during_feed_fetch", run_id)
            return await self._run_repository.get_by_run_id(run_id)

        total_items = len(all_items)
        baseline_items = [
            run_item
            for _, run_item in all_items
            if run_item.run_item_id not in {item.run_item_id for _, item in items_to_process}
        ]
        baseline_completed = sum(
            1
            for run_item in baseline_items
            if str(run_item.status) in FINALIZED_RUN_ITEM_STATUSES
        )
        baseline_failed = sum(
            1 for run_item in baseline_items if str(run_item.status) == RunItemStatus.FAILED.value
        )
        await self._run_repository.update_progress(
            run_id=run_id,
            total_items=total_items,
            completed_items=baseline_completed,
            failed_items=baseline_failed,
            error=None,
            now=utcnow(),
        )

        semaphore = asyncio.Semaphore(self._settings.episodes_per_run_concurrency)
        counter_lock = asyncio.Lock()
        progress = {"completed": baseline_completed, "failed": baseline_failed}

        async def process_pair(episode: Episode, run_item: RunItem) -> None:
            async with semaphore:
                success = await self._process_episode(
                    run=run,
                    episode=episode,
                    run_item=run_item,
                    worker_id=worker_id,
                )
                async with counter_lock:
                    if success:
                        progress["completed"] += 1
                    else:
                        progress["failed"] += 1
                    await self._run_repository.update_progress(
                        run_id=run_id,
                        completed_items=progress["completed"],
                        failed_items=progress["failed"],
                        now=utcnow(),
                    )

        await asyncio.gather(*(process_pair(episode, item) for episode, item in items_to_process))

        if progress["failed"] == 0:
            final_status = RunStatus.COMPLETED
        elif progress["completed"] == 0:
            final_status = RunStatus.FAILED
        else:
            final_status = RunStatus.PARTIAL_FAILED

        await self._run_repository.finalize(
            run_id=run_id,
            status=final_status,
            total_items=total_items,
            completed_items=progress["completed"],
            failed_items=progress["failed"],
            error=None if progress["failed"] == 0 else "One or more episodes failed.",
            now=utcnow(),
        )
        logger.info(
            "pipeline.run.finalized run_id=%s status=%s total=%s completed=%s failed=%s",
            run_id,
            final_status.value,
            total_items,
            progress["completed"],
            progress["failed"],
        )
        return await self._run_repository.get_by_run_id(run_id)

    async def _prepare_run_items(
        self,
        *,
        run: Run,
    ) -> tuple[list[tuple[Episode, RunItem]], list[tuple[Episode, RunItem]]]:
        if run.retry_run_item_ids:
            logger.info(
                "pipeline.run.retry_mode run_id=%s retry_run_item_ids=%s",
                run.run_id,
                ",".join(run.retry_run_item_ids),
            )
            run_items = await self._run_item_repository.list_all_by_run_id(run.run_id)
            episodes = await self._episode_repository.list_by_episode_ids(
                [run_item.episode_id for run_item in run_items],
            )
            episodes_by_id = {episode.episode_id: episode for episode in episodes}
            all_items = [
                (episodes_by_id[run_item.episode_id], run_item)
                for run_item in run_items
                if run_item.episode_id in episodes_by_id
            ]
            retry_ids = set(run.retry_run_item_ids)
            retry_items = [
                pair for pair in all_items if pair[1].run_item_id in retry_ids
            ]
            if not retry_items:
                raise RuntimeError("Retry targets could not be resolved for this run.")
            return all_items, retry_items

        parsed_episodes = await self._rss_provider.fetch_episodes(
            run.rss_url,
            self._settings.max_episodes_per_run,
        )
        prepared_items: list[tuple[Episode, RunItem]] = []
        new_items: list[RunItem] = []
        for parsed in parsed_episodes:
            episode = await self._episode_repository.upsert(
                Episode(
                    dedupe_key=parsed.dedupe_key,
                    title=parsed.title,
                    episode_url=parsed.episode_url,
                    audio_url=parsed.audio_url,
                    published_at=parsed.published_at,
                    feed_url=parsed.feed_url,
                ),
            )
            existing_item = await self._run_item_repository.get_by_run_and_episode(
                run.run_id,
                episode.episode_id,
            )
            if existing_item is None:
                new_item = RunItem(
                    run_id=run.run_id,
                    episode_id=episode.episode_id,
                    title=episode.title,
                )
                prepared_items.append((episode, new_item))
                new_items.append(new_item)
            else:
                prepared_items.append((episode, existing_item))

        if new_items:
            await self._run_item_repository.create_many(new_items)
        return prepared_items, prepared_items

    async def _process_episode(
        self,
        *,
        run: Run,
        episode: Episode,
        run_item: RunItem,
        worker_id: str,
    ) -> bool:
        try:
            logger.info(
                "pipeline.episode.started run_id=%s episode_id=%s title=%s",
                run.run_id,
                episode.episode_id,
                episode.title,
            )
            transcript, lead, reused = await self._ensure_episode_artifacts(
                run=run,
                episode=episode,
                run_item=run_item,
                worker_id=worker_id,
            )
            final_status = RunItemStatus.REUSED if reused else RunItemStatus.DONE
            await self._run_item_repository.update_status(
                run_item_id=run_item.run_item_id,
                status=final_status,
                now=utcnow(),
            )
            logger.info(
                "pipeline.episode.completed run_id=%s episode_id=%s reused=%s lead_id=%s",
                run.run_id,
                episode.episode_id,
                reused,
                lead.lead_id if lead else None,
            )
            return transcript is not None and lead is not None
        except Exception as exc:
            await self._run_item_repository.update_status(
                run_item_id=run_item.run_item_id,
                status=RunItemStatus.FAILED,
                error=str(exc),
                now=utcnow(),
            )
            logger.exception(
                "pipeline.episode.failed run_id=%s episode_id=%s error=%s",
                run.run_id,
                episode.episode_id,
                exc,
            )
            return False

    async def _ensure_episode_artifacts(
        self,
        *,
        run: Run,
        episode: Episode,
        run_item: RunItem,
        worker_id: str,
    ) -> tuple[Transcript | None, Lead | None, bool]:
        deadline = asyncio.get_running_loop().time() + self._settings.assemblyai_timeout_seconds
        reused = False
        while True:
            transcript = await self._transcript_repository.get_by_episode_id(episode.episode_id)
            lead = await self._lead_repository.get_by_episode_id(episode.episode_id)
            if transcript is not None and lead is not None:
                logger.info("pipeline.episode.reused episode_id=%s", episode.episode_id)
                return transcript, lead, True

            claimed = await self._episode_repository.claim_processing(
                episode_id=episode.episode_id,
                owner=worker_id,
                now=utcnow(),
                stale_before=utcnow() - timedelta(seconds=self._settings.stale_run_seconds),
            )
            if claimed is not None:
                try:
                    transcript = transcript or await self._create_transcript(
                        episode=episode,
                        run_item=run_item,
                    )
                    lead = lead or await self._create_lead(
                        run=run,
                        episode=episode,
                        run_item=run_item,
                        transcript=transcript,
                    )
                    return transcript, lead, reused
                finally:
                    await self._episode_repository.release_processing(
                        episode_id=episode.episode_id,
                        now=utcnow(),
                    )

            if asyncio.get_running_loop().time() > deadline:
                raise TimeoutError(f"Timed out waiting for canonical episode {episode.episode_id}")
            await asyncio.sleep(self._settings.assemblyai_poll_interval_seconds)

    async def _create_transcript(self, *, episode: Episode, run_item: RunItem) -> Transcript:
        logger.info("pipeline.transcript.started episode_id=%s", episode.episode_id)
        await self._run_item_repository.update_status(
            run_item_id=run_item.run_item_id,
            status=RunItemStatus.TRANSCRIBING,
            now=utcnow(),
        )
        job_id = await self._assemblyai_provider.submit_transcription(episode.audio_url)
        result = await self._assemblyai_provider.poll_transcription(job_id)
        transcript = Transcript(
            episode_id=episode.episode_id,
            assemblyai_job_id=result.assemblyai_job_id,
            status=result.status or TranscriptStatus.COMPLETED,
            text=result.text,
            provider_metadata=result.provider_metadata,
        )
        await self._transcript_repository.create(transcript)
        await self._run_item_repository.update_status(
            run_item_id=run_item.run_item_id,
            status=RunItemStatus.TRANSCRIBED,
            now=utcnow(),
        )
        logger.info("pipeline.transcript.completed episode_id=%s", episode.episode_id)
        return transcript

    async def _create_lead(
        self,
        *,
        run: Run,
        episode: Episode,
        run_item: RunItem,
        transcript: Transcript,
    ) -> Lead:
        logger.info("pipeline.lead.started episode_id=%s", episode.episode_id)
        await self._run_item_repository.update_status(
            run_item_id=run_item.run_item_id,
            status=RunItemStatus.GENERATING,
            now=utcnow(),
        )
        draft = await self._openai_provider.generate_lead_draft(
            transcript_text=transcript.text or "",
            tone_instructions=run.tone_instructions,
        )
        lead = Lead(
            run_id=run.run_id,
            episode_id=episode.episode_id,
            guest_name=draft.guest_name,
            guest_company=draft.guest_company,
            role=draft.role,
            pain_point=draft.pain_point,
            memorable_quote=draft.memorable_quote,
            email_subject=draft.email_subject,
            email_body=draft.email_body,
            prompt_version=self._openai_provider.prompt_version,
            model_name=self._openai_provider.model,
        )
        await self._lead_repository.create(lead)
        logger.info(
            "pipeline.lead.completed episode_id=%s lead_id=%s",
            episode.episode_id,
            lead.lead_id,
        )
        return lead
