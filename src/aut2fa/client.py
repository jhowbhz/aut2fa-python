import json
from http.client import HTTPException
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import HTTPRedirectHandler, Request, build_opener

from . import _validation
from .errors import ApiError, InvalidResponseError, NetworkError, RequestTimeoutError
from .models import SendResponse, VerificationResponse


def _reject_json_constant(value: str):
    raise ValueError("Nonstandard JSON constant")


def _json_object(body: bytes) -> dict[str, Any]:
    payload = json.loads(body.decode("utf-8"), parse_constant=_reject_json_constant)
    if not isinstance(payload, dict):
        raise ValueError("JSON response must be an object")
    return payload


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


class Aut2fa:
    def __init__(
        self,
        api_key: str,
        *,
        base_url: str = "https://api.aut2fa.com",
        timeout: float = 10,
    ):
        self._api_key = _validation.header_value(api_key, "api_key")
        self._base_url = _validation.base_url(base_url)
        self._timeout = _validation.timeout(timeout)
        self._opener = build_opener(_NoRedirect())

    def send(
        self,
        *,
        to: str,
        code: str | None = None,
        locale: str | None = None,
        idempotency_key: str | None = None,
    ) -> SendResponse:
        data = {"to": _validation.string(to, "to")}
        if code is not None:
            data["code"] = _validation.string(code, "code")
        if locale is not None:
            data["locale"] = _validation.string(locale, "locale")
        return self._send_response(self._request("POST", "/v1/send", data, idempotency_key))

    def status(self, id: str) -> SendResponse:
        id = _validation.send_id(id)
        return self._send_response(self._request("GET", f"/v1/send/{id}/status"))

    def verify(self, id: str, *, code: str) -> VerificationResponse:
        id = _validation.send_id(id)
        code = _validation.string(code, "code")
        status, payload = self._request("POST", f"/v1/send/{id}/verify", {"code": code})
        if (
            not isinstance(payload.get("valid"), bool)
            or not isinstance(payload.get("verification"), str)
            or not payload["verification"]
            or type(payload.get("attempts_left")) is not int
            or payload["attempts_left"] < 0
        ):
            raise InvalidResponseError(status)
        return VerificationResponse(payload)

    @staticmethod
    def _send_response(response: tuple[int, dict[str, Any]]) -> SendResponse:
        status, payload = response
        if any(
            not isinstance(payload.get(key), str) or not payload[key] for key in ("id", "status")
        ):
            raise InvalidResponseError(status)
        return SendResponse(payload)

    def _request(
        self,
        method: str,
        path: str,
        data: dict[str, str] | None = None,
        idempotency_key: str | None = None,
    ) -> tuple[int, dict[str, Any]]:
        headers = {"Authorization": b"Bearer " + self._api_key, "Accept": "application/json"}
        body = None
        if data is not None:
            headers["Content-Type"] = "application/json"
            body = json.dumps(data).encode("utf-8")
        if idempotency_key is not None:
            headers["Idempotency-Key"] = _validation.idempotency_key(idempotency_key)
        request = Request(
            f"{self._base_url}{path}",
            data=body,
            headers=headers,
            method=method,
        )
        try:
            with self._opener.open(request, timeout=self._timeout) as response:
                try:
                    return response.status, _json_object(response.read())
                except (ValueError, UnicodeDecodeError):
                    raise InvalidResponseError(response.status) from None
        except HTTPError as response:
            with response:
                try:
                    problem = _json_object(response.read())
                except (ValueError, UnicodeDecodeError, OSError, HTTPException):
                    problem = None
            if (
                not isinstance(problem, dict)
                or not isinstance(problem.get("code"), str)
                or not problem["code"]
                or ("detail" in problem and not isinstance(problem["detail"], str))
            ):
                problem = {}
            raise ApiError(
                status=response.code,
                code=problem.get("code", "http_error"),
                detail=problem.get("detail", f"HTTP request failed with status {response.code}."),
                errors=problem.get("errors"),
                retry_after=response.headers.get("Retry-After"),
            ) from None
        except TimeoutError as error:
            raise RequestTimeoutError() from error
        except URLError as error:
            if isinstance(error.reason, TimeoutError):
                raise RequestTimeoutError() from error
            raise NetworkError() from error
        except (OSError, HTTPException) as error:
            raise NetworkError() from error
