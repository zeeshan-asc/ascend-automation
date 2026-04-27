class DomainError(Exception):
    """Base error for domain-specific failures."""


class InvalidStateTransitionError(DomainError):
    """Raised when a model attempts an invalid status transition."""


class ResourceNotFoundError(DomainError):
    """Raised when a requested resource does not exist."""


class DuplicateResourceError(DomainError):
    """Raised when a unique resource already exists."""


class FeedFetchError(DomainError):
    """Raised when an RSS feed cannot be fetched or parsed."""


class TranscriptError(DomainError):
    """Raised when a transcription provider reports failure."""


class TranscriptTimeoutError(TranscriptError):
    """Raised when a transcription request times out."""


class OpenAIRefusalError(DomainError):
    """Raised when OpenAI refuses to fulfill a request."""
