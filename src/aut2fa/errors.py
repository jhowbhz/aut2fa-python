from typing import Any


class ApiError(RuntimeError):
    """Describes an HTTP rejection without exposing an unexpected response body."""

    def __init__(
        self,
        *,
        status: int,
        code: str,
        detail: str,
        errors: Any = None,
        retry_after: str | None = None,
    ):
        self.status = status
        self.code = code
        self.detail = detail
        self.errors = errors
        self.retry_after = retry_after
        super().__init__(f"{code} (HTTP {status}): {detail}")


class InvalidResponseError(RuntimeError):
    """Identifies a success response that does not satisfy the API contract."""

    def __init__(self, status: int):
        self.status = status
        self.code = "invalid_response"
        super().__init__(f"API returned an invalid response (HTTP {status}).")


class NetworkError(RuntimeError):
    """Identifies a transport failure whose original cause remains available."""

    code = "network_error"

    def __init__(self):
        super().__init__("The API request could not be completed.")


class RequestTimeoutError(NetworkError, TimeoutError):
    """Identifies a timed-out request without retrying an uncertain operation."""

    code = "request_timeout"
