"""Retry-After parser testleri."""

from datetime import datetime, timezone

import pytest

from retry_client.retry_after import parse_retry_after


def test_parse_retry_after_integer_seconds() -> None:
    """Tam sayı saniye değeri işlenmelidir."""
    assert parse_retry_after("10") == 10.0


def test_parse_retry_after_decimal_seconds() -> None:
    """Ondalıklı saniye değeri işlenmelidir."""
    assert parse_retry_after("2.5") == 2.5


def test_parse_retry_after_with_whitespace() -> None:
    """Başta ve sonda bulunan boşluklar temizlenmelidir."""
    assert parse_retry_after("  15  ") == 15.0


def test_parse_retry_after_http_date() -> None:
    """HTTP-date ile mevcut zaman arasındaki fark hesaplanmalıdır."""
    current_time = datetime(
        2015,
        10,
        21,
        7,
        27,
        50,
        tzinfo=timezone.utc,
    )

    result = parse_retry_after(
        "Wed, 21 Oct 2015 07:28:00 GMT",
        now=current_time,
    )

    assert result == 10.0


def test_past_http_date_returns_zero() -> None:
    """Geçmiş tarih negatif bekleme üretmemelidir."""
    current_time = datetime(
        2015,
        10,
        21,
        7,
        29,
        0,
        tzinfo=timezone.utc,
    )

    result = parse_retry_after(
        "Wed, 21 Oct 2015 07:28:00 GMT",
        now=current_time,
    )

    assert result == 0.0


@pytest.mark.parametrize(
    "header_value",
    [None, "", "   ", "invalid-date", "-5"],
)
def test_invalid_retry_after_returns_none(
    header_value: str | None,
) -> None:
    """Geçersiz Retry-After değerleri None döndürmelidir."""
    assert parse_retry_after(header_value) is None