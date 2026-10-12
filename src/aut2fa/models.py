from typing import Any


class _Response:
    def __init__(self, data: dict[str, Any]):
        self._data = data.copy()

    def __getattr__(self, name: str) -> Any:
        try:
            return self._data[name]
        except KeyError as error:
            raise AttributeError(name) from error

    def to_dict(self) -> dict[str, Any]:
        return self._data.copy()


class SendResponse(_Response):
    id: str
    status: str
    verification: str
    mode: str
    channel: str | None
    expires_at: str
    created_at: str
    sent_at: str | None
    delivered_at: str | None
    read_at: str | None
    verified_at: str | None
    failed_at: str | None
    failure_reason: str | None

    @property
    def from_(self) -> str | None:
        return self._data["from"]


class VerificationResponse(_Response):
    valid: bool
    verification: str
    attempts_left: int
