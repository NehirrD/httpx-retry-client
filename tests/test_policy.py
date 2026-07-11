"""Retry policy testleri."""

import httpx
import pytest

from retry_client.policy import (
    has_idempotency_key,
    is_exception_retryable,
    is_method_retryable,
    is_retryable,
    is_status_retryable,
)


@pytest.mark.parametrize(
    "method",
    ["GET", "HEAD", "OPTIONS", "PUT", "DELETE"],
)
def test_idempotent_methods_are_retryable(method: str) -> None:
    """Güvenli HTTP metotları retry edilebilmelidir."""
    assert is_method_retryable(method) is True


def test_method_check_is_case_insensitive() -> None:
    """HTTP metodu küçük harfle verilse de tanınmalıdır."""
    assert is_method_retryable("get") is True


@pytest.mark.parametrize("method", ["PATCH", "CONNECT", "TRACE"])
def test_unsupported_methods_are_not_retryable(method: str) -> None:
    """Desteklenmeyen metotlar otomatik retry edilmemelidir."""
    assert is_method_retryable(method) is False


def test_post_without_idempotency_key_is_not_retryable() -> None:
    """Idempotency-Key bulunmayan POST isteği retry edilmemelidir."""
    assert is_method_retryable("POST") is False


def test_post_with_idempotency_key_is_retryable() -> None:
    """Idempotency-Key bulunan POST isteği retry edilebilmelidir."""
    headers = {"Idempotency-Key": "order-123"}

    assert is_method_retryable("POST", headers) is True


def test_idempotency_key_is_case_insensitive() -> None:
    """Idempotency-Key başlığı büyük/küçük harfe duyarsız olmalıdır."""
    headers = {"idempotency-key": "payment-456"}

    assert has_idempotency_key(headers) is True


def test_empty_idempotency_key_is_invalid() -> None:
    """Boş Idempotency-Key geçerli kabul edilmemelidir."""
    headers = {"Idempotency-Key": "   "}

    assert has_idempotency_key(headers) is False


@pytest.mark.parametrize("status_code", [429, 502, 503, 504])
def test_retryable_status_codes(status_code: int) -> None:
    """Tanımlanan geçici hata kodları retry edilebilmelidir."""
    assert is_status_retryable(status_code) is True


@pytest.mark.parametrize(
    "status_code",
    [200, 400, 401, 403, 404, 422, 500],
)
def test_non_retryable_status_codes(status_code: int) -> None:
    """Retry kapsamı dışındaki kodlar reddedilmelidir."""
    assert is_status_retryable(status_code) is False


@pytest.mark.parametrize(
    "exception",
    [
        httpx.ConnectError("connection failed"),
        httpx.ConnectTimeout("connect timeout"),
        httpx.ReadTimeout("read timeout"),
        httpx.WriteTimeout("write timeout"),
        httpx.PoolTimeout("pool timeout"),
    ],
)
def test_network_exceptions_are_retryable(exception: Exception) -> None:
    """Ağ ve timeout hataları retry edilebilmelidir."""
    assert is_exception_retryable(exception) is True


def test_unrelated_exception_is_not_retryable() -> None:
    """İlgisiz uygulama hataları retry edilmemelidir."""
    assert is_exception_retryable(ValueError("invalid value")) is False


def test_get_request_with_503_is_retryable() -> None:
    """GET isteği 503 aldığında retry edilebilmelidir."""
    assert is_retryable("GET", status_code=503) is True


def test_post_without_key_with_503_is_not_retryable() -> None:
    """Anahtarsız POST, geçici hata alsa bile retry edilmemelidir."""
    assert is_retryable("POST", status_code=503) is False


def test_post_with_key_and_503_is_retryable() -> None:
    """Anahtarlı POST geçici hata aldığında retry edilebilmelidir."""
    assert (
        is_retryable(
            "POST",
            status_code=503,
            headers={"Idempotency-Key": "request-789"},
        )
        is True
    )