import math
import re
import unicodedata
from urllib.parse import urlsplit


def string(value: str, name: str) -> str:
    if not isinstance(value, str):
        raise ValueError(f"{name} must be a string")
    return value


def header_value(value: str, name: str) -> bytes:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be a nonempty string")
    if any(unicodedata.category(character) == "Cc" for character in value):
        raise ValueError(f"{name} must not contain control characters")
    try:
        return value.encode("utf-8")
    except UnicodeEncodeError:
        raise ValueError(f"{name} must be valid UTF-8") from None


def base_url(value: str) -> str:
    if (
        not isinstance(value, str)
        or not value
        or any(
            character.isspace() or unicodedata.category(character) == "Cc" for character in value
        )
        or any(character in value for character in ("?", "#", "\\"))
    ):
        raise ValueError("base_url must be an HTTP(S) URL without credentials, query or fragment")
    try:
        parts = urlsplit(value)
        valid = (
            parts.scheme in ("http", "https")
            and parts.hostname
            and parts.username is None
            and parts.password is None
            and (parts.port is None or 0 < parts.port <= 65535)
        )
    except ValueError:
        valid = False
    if not valid:
        raise ValueError("base_url must be an HTTP(S) URL without credentials, query or fragment")
    return value.rstrip("/")


def timeout(value: float) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError("timeout must be a finite, strictly positive number of seconds")
    try:
        valid = math.isfinite(value) and value > 0
    except OverflowError:
        valid = False
    if not valid:
        raise ValueError("timeout must be a finite, strictly positive number of seconds")
    return float(value)


def send_id(value: str) -> str:
    if not isinstance(value, str) or re.fullmatch(r"[A-Za-z0-9_-]+", value) is None:
        raise ValueError("id must contain only ASCII letters, digits, underscores or hyphens")
    return value


def idempotency_key(value: str) -> bytes:
    encoded = header_value(value, "idempotency_key")
    if len(encoded) > 255:
        raise ValueError("idempotency_key must not exceed 255 UTF-8 bytes")
    return encoded
