class AdoAiReviewError(Exception):
    """Base exception for worker failures."""


class ConfigurationError(AdoAiReviewError):
    """Raised when required configuration is absent or invalid."""


class CommandRejectedError(AdoAiReviewError):
    """Raised when a command violates the CLI execution policy."""


class CommandExecutionError(AdoAiReviewError):
    """Raised when an allowlisted command exits unsuccessfully."""


class WorkspaceBoundaryError(AdoAiReviewError):
    """Raised when a path or process cwd escapes the request workspace."""


class ModelOutputError(AdoAiReviewError):
    """Raised when model output cannot be parsed or validated."""
