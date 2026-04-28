class DomainError(Exception):
    """Base error for domain-specific failures."""


class InvalidStateTransitionError(DomainError):
    """Raised when a model attempts an invalid status transition."""


class InvalidOperationError(DomainError):
    """Raised when a requested operation cannot be completed in the current state."""


class ResourceNotFoundError(DomainError):
    """Raised when a requested resource does not exist."""


class DuplicateResourceError(DomainError):
    """Raised when a unique resource already exists."""


class AuthenticationError(DomainError):
    """Raised when authentication fails."""


class AuthorizationError(DomainError):
    """Raised when an authenticated action is not permitted."""


class SourceFetchError(DomainError):
    """Raised when a source URL cannot be fetched or resolved."""

    def __init__(self, message: str, *, reason_code: str = "source_invalid") -> None:
        super().__init__(message)
        self.reason_code = reason_code


class FeedFetchError(SourceFetchError):
    """Raised when an RSS feed cannot be fetched or parsed."""

    def __init__(self, message: str, *, reason_code: str = "feed_invalid") -> None:
        super().__init__(message)
        self.reason_code = reason_code


class TranscriptError(DomainError):
    """Raised when a transcription provider reports failure."""


class TranscriptTimeoutError(TranscriptError):
    """Raised when a transcription request times out."""


class OpenAIRefusalError(DomainError):
    """Raised when OpenAI refuses to fulfill a request."""
