"""Domain exception hierarchy.

Services raise these; FastAPI apps map them to HTTP responses centrally
(lifeops_core.api.register_error_handlers) so route handlers stay thin.
"""


class DomainError(Exception):
    status_code = 400
    title = "Bad Request"

    def __init__(self, message: str, details: dict | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.details = details or {}


class DomainValidationError(DomainError):
    status_code = 422
    title = "Validation Failed"


class NotFoundError(DomainError):
    status_code = 404
    title = "Not Found"


class ConflictError(DomainError):
    status_code = 409
    title = "Conflict"


class SourceUnavailableError(DomainError):
    """Requested ingestion source has no adapter (feature not built yet)."""

    status_code = 501
    title = "Source Adapter Not Available"
