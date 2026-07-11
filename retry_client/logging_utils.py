"""HTTP retry istemcisi için logging yardımcıları."""

from __future__ import annotations

import logging
from urllib.parse import urlsplit, urlunsplit


LOGGER_NAME = "retry_client"


def get_logger(
    name: str = LOGGER_NAME,
    *,
    level: int = logging.INFO,
) -> logging.Logger:
    """Yapılandırılmış logger döndürür.

    Args:
        name: Logger adı.
        level: Logging seviyesi.

    Returns:
        Yapılandırılmış logger nesnesi.
    """
    logger = logging.getLogger(name)
    logger.setLevel(level)

    if not logger.handlers:
        handler = logging.StreamHandler()
        formatter = logging.Formatter(
            "%(asctime)s | %(levelname)s | %(name)s | %(message)s"
        )
        handler.setFormatter(formatter)
        logger.addHandler(handler)

    logger.propagate = False
    return logger


def mask_url(url: str) -> str:
    """URL içindeki hassas query parametrelerini gizler.

    Query string tamamen kaldırılır; yalnızca şema, host ve path loglanır.

    Args:
        url: Maskelenecek URL.

    Returns:
        Query ve fragment bilgileri çıkarılmış güvenli URL.
    """
    parsed = urlsplit(url)

    return urlunsplit(
        (
            parsed.scheme,
            parsed.netloc,
            parsed.path,
            "",
            "",
        )
    )


def log_retry_attempt(
    logger: logging.Logger,
    *,
    attempt: int,
    delay: float,
    reason: str,
    method: str,
    url: str,
    status_code: int | None = None,
) -> None:
    """Retry denemesini warning seviyesinde loglar."""
    logger.warning(
        "retry attempt=%s method=%s url=%s delay=%.3f reason=%s status_code=%s",
        attempt,
        method.upper(),
        mask_url(url),
        delay,
        reason,
        status_code,
    )


def log_request_success(
    logger: logging.Logger,
    *,
    attempt: int,
    method: str,
    url: str,
    status_code: int,
) -> None:
    """Başarılı isteği info seviyesinde loglar."""
    logger.info(
        "request_success attempt=%s method=%s url=%s status_code=%s",
        attempt,
        method.upper(),
        mask_url(url),
        status_code,
    )


def log_request_failure(
    logger: logging.Logger,
    *,
    attempt: int,
    method: str,
    url: str,
    reason: str,
    status_code: int | None = None,
) -> None:
    """Nihai başarısızlığı error seviyesinde loglar."""
    logger.error(
        "request_failure attempt=%s method=%s url=%s reason=%s status_code=%s",
        attempt,
        method.upper(),
        mask_url(url),
        reason,
        status_code,
    )