"""
Retry policy helpers.

Bu modül bir isteğin yeniden denenip denenmeyeceğine karar verir.
"""

from __future__ import annotations

from collections.abc import Mapping

import httpx

IDEMPOTENT_METHODS = {
    "GET",
    "HEAD",
    "OPTIONS",
    "PUT",
    "DELETE",
}

RETRYABLE_STATUS_CODES = {
    429,
    502,
    503,
    504,
}

RETRYABLE_EXCEPTIONS = (
    httpx.ConnectError,
    httpx.ConnectTimeout,
    httpx.ReadTimeout,
    httpx.WriteTimeout,
    httpx.PoolTimeout,
)


def has_idempotency_key(headers: Mapping[str, str] | None) -> bool:
    """İstek header'ında Idempotency-Key var mı?"""

    if not headers:
        return False

    return any(
        key.lower() == "idempotency-key" and value.strip()
        for key, value in headers.items()
    )


def is_method_retryable(
    method: str,
    headers: Mapping[str, str] | None = None,
) -> bool:
    """
    HTTP metodunun retry edilebilir olup olmadığını döndürür.
    """

    method = method.upper()

    if method in IDEMPOTENT_METHODS:
        return True

    if method == "POST":
        return has_idempotency_key(headers)

    return False


def is_status_retryable(status_code: int | None) -> bool:
    """HTTP status kodu retry edilmeli mi?"""

    return status_code in RETRYABLE_STATUS_CODES


def is_exception_retryable(exception: Exception | None) -> bool:
    """Exception retry edilmeli mi?"""

    return isinstance(exception, RETRYABLE_EXCEPTIONS)


def is_retryable(
    method: str,
    *,
    status_code: int | None = None,
    exception: Exception | None = None,
    headers: Mapping[str, str] | None = None,
) -> bool:
    """
    Genel retry kararı.
    """

    if not is_method_retryable(method, headers):
        return False

    return (
        is_status_retryable(status_code)
        or is_exception_retryable(exception)
    )