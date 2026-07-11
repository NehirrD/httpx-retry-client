"""
Retry-After header parsing utilities.

Bu modül Retry-After değerini saniye veya HTTP-date formatında işler.
"""

from __future__ import annotations

from datetime import datetime, timezone
from email.utils import parsedate_to_datetime


def parse_retry_after(
    header_value: str | None,
    *,
    now: datetime | None = None,
) -> float | None:
    """
    Retry-After header değerini saniye cinsinden döndürür.

    Desteklenen formatlar:
    - Saniye: "10"
    - HTTP-date: "Wed, 21 Oct 2015 07:28:00 GMT"

    Args:
        header_value: Retry-After header değeri.
        now: HTTP-date hesaplamasında kullanılacak mevcut zaman.
            Testlerde deterministik sonuç üretmek için verilebilir.

    Returns:
        Beklenmesi gereken saniye miktarı.
        Geçersiz veya boş değerlerde None.
    """
    if header_value is None:
        return None

    value = header_value.strip()

    if not value:
        return None

    try:
        seconds = float(value)
    except ValueError:
        seconds = None

    if seconds is not None:
        if seconds < 0:
            return None
        return seconds

    try:
        retry_date = parsedate_to_datetime(value)
    except (TypeError, ValueError, OverflowError):
        return None

    if retry_date is None:
        return None

    if retry_date.tzinfo is None:
        retry_date = retry_date.replace(tzinfo=timezone.utc)
    else:
        retry_date = retry_date.astimezone(timezone.utc)

    current_time = now or datetime.now(timezone.utc)

    if current_time.tzinfo is None:
        current_time = current_time.replace(tzinfo=timezone.utc)
    else:
        current_time = current_time.astimezone(timezone.utc)

    delay = (retry_date - current_time).total_seconds()

    return max(0.0, delay)