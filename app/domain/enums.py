from enum import StrEnum


class RunStatus(StrEnum):
    QUEUED = "queued"
    CLAIMED = "claimed"
    RUNNING = "running"
    COMPLETED = "completed"
    PARTIAL_FAILED = "partial_failed"
    FAILED = "failed"


class RunItemStatus(StrEnum):
    PENDING = "pending"
    REUSED = "reused"
    TRANSCRIBING = "transcribing"
    TRANSCRIBED = "transcribed"
    GENERATING = "generating"
    DONE = "done"
    FAILED = "failed"


class TranscriptStatus(StrEnum):
    SUBMITTED = "submitted"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"
    TIMEOUT = "timeout"


class LeadStatus(StrEnum):
    GENERATED = "generated"
    REVIEW_NEEDED = "review_needed"
    FAILED = "failed"


class OutreachStatus(StrEnum):
    NOT_CONTACTED = "not_contacted"
    CONTACTED = "contacted"


class SourceKind(StrEnum):
    AUTO = "auto"
    RSS_FEED = "rss_feed"
    EPISODE_PAGE = "episode_page"
    AUDIO_FILE = "audio_file"
