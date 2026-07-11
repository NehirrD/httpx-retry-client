"""HTTP retry istemcisi - public API.

RetryConfig (config.py), calculate_delay (backoff.py), build_httpx_timeout
(timeouts.py), is_retryable/parse_retry_after (policy.py, retry_after.py) ve
CircuitBreaker/logging (circuit_breaker.py, logging_utils.py) modüllerini
birleştirip httpx.Client/httpx.AsyncClient üzerinde kullanılabilir tek bir
RetryClient sınıfı olarak sunar.

Sorumlu: Zühre Korhan
"""

from __future__ import annotations

import asyncio
import logging
import random
import time
from collections.abc import Mapping
from types import TracebackType
from typing import Any

import httpx

from .backoff import JitterStrategy, calculate_delay, full_jitter
from .circuit_breaker import CircuitBreaker
from .config import RetryConfig
from .logging_utils import (
    get_logger,
    log_request_failure,
    log_request_success,
    log_retry_attempt,
)
from .policy import RETRYABLE_EXCEPTIONS, is_retryable, is_status_retryable
from .retry_after import parse_retry_after
from .timeouts import build_httpx_timeout


class RetryClient:
    """Exponential backoff, jitter ve idempotent retry destekli HTTP istemcisi.

    Sync ve async kullanım aynı örnek üzerinden desteklenir: sync istekler
    için `get`/`post`/... , async istekler için `aget`/`apost`/... metotları
    kullanılır.
    """

    def __init__(
        self,
        base_url: str = "",
        *,
        config: RetryConfig | None = None,
        jitter_strategy: JitterStrategy = full_jitter,
        circuit_breaker: CircuitBreaker | None = None,
        logger: logging.Logger | None = None,
        rng: random.Random | None = None,
        **httpx_kwargs: Any,
    ) -> None:
        """RetryClient oluşturur.

        Args:
            base_url: İsteklerin göreli path'lerle yapılabilmesi için taban URL.
            config: Retry/backoff/timeout ayarları. Verilmezse varsayılan
                `RetryConfig()` kullanılır.
            jitter_strategy: `backoff.py` içindeki jitter stratejilerinden
                biri. Varsayılan `full_jitter`.
            circuit_breaker: Opsiyonel `CircuitBreaker`. Verilmezse circuit
                breaker devre dışıdır.
            logger: Kullanılacak logger. Verilmezse `get_logger()` ile
                oluşturulan standart logger kullanılır.
            rng: Jitter hesaplamasında kullanılacak `random.Random`. Testlerde
                deterministik sonuç için verilebilir.
            **httpx_kwargs: `httpx.Client`/`httpx.AsyncClient`'a olduğu gibi
                aktarılan ek parametreler (örn. `headers`, `auth`, `verify`).
        """
        self._config = config or RetryConfig()
        self._jitter_strategy = jitter_strategy
        self._circuit_breaker = circuit_breaker
        self._logger = logger or get_logger()
        self._rng = rng or random.Random()

        timeout = build_httpx_timeout(self._config)
        self._client = httpx.Client(base_url=base_url, timeout=timeout, **httpx_kwargs)
        self._async_client = httpx.AsyncClient(
            base_url=base_url, timeout=timeout, **httpx_kwargs
        )

    # -- Kaynak yönetimi -------------------------------------------------

    def close(self) -> None:
        """Sync httpx.Client'ı kapatır."""
        self._client.close()

    async def aclose(self) -> None:
        """Async httpx.AsyncClient'ı kapatır."""
        await self._async_client.aclose()

    def __enter__(self) -> "RetryClient":
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        self.close()

    async def __aenter__(self) -> "RetryClient":
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        await self.aclose()

    # -- Retry karar mantığı ----------------------------------------------

    def _decide(
        self,
        method: str,
        headers: Mapping[str, str] | None,
        attempt: int,
        *,
        response: httpx.Response | None = None,
        exception: Exception | None = None,
    ) -> tuple[bool, float, str]:
        """Bir sonraki denemenin yapılıp yapılmayacağına karar verir.

        Returns:
            (should_retry, delay_seconds, reason) üçlüsü.
        """
        status_code = response.status_code if response is not None else None

        if not is_retryable(
            method, status_code=status_code, exception=exception, headers=headers
        ):
            return False, 0.0, "not_retryable"

        if attempt >= self._config.max_retries:
            return False, 0.0, "max_retries_exhausted"

        if response is not None:
            retry_after = parse_retry_after(response.headers.get("Retry-After"))
            reason = f"http_{status_code}"
        else:
            retry_after = None
            reason = type(exception).__name__

        delay = (
            retry_after
            if retry_after is not None
            else calculate_delay(
                attempt, self._config, self._jitter_strategy, self._rng
            )
        )
        return True, delay, reason

    # -- Sync API -----------------------------------------------------------

    def request(
        self,
        method: str,
        url: str,
        *,
        headers: Mapping[str, str] | None = None,
        **kwargs: Any,
    ) -> httpx.Response:
        """Retry mantığı uygulanmış sync HTTP isteği yapar."""
        attempt = 0
        while True:
            if self._circuit_breaker is not None:
                self._circuit_breaker.before_request()

            try:
                response = self._client.request(method, url, headers=headers, **kwargs)
            except RETRYABLE_EXCEPTIONS as exc:
                should_retry, delay, reason = self._decide(
                    method, headers, attempt, exception=exc
                )
                if self._circuit_breaker is not None:
                    self._circuit_breaker.record_failure()
                if not should_retry:
                    log_request_failure(
                        self._logger,
                        attempt=attempt,
                        method=method,
                        url=url,
                        reason=reason,
                    )
                    raise
                log_retry_attempt(
                    self._logger,
                    attempt=attempt,
                    delay=delay,
                    reason=reason,
                    method=method,
                    url=url,
                )
                time.sleep(delay)
                attempt += 1
                continue

            should_retry, delay, reason = self._decide(
                method, headers, attempt, response=response
            )
            if should_retry:
                if self._circuit_breaker is not None:
                    self._circuit_breaker.record_failure()
                log_retry_attempt(
                    self._logger,
                    attempt=attempt,
                    delay=delay,
                    reason=reason,
                    method=method,
                    url=url,
                    status_code=response.status_code,
                )
                time.sleep(delay)
                attempt += 1
                continue

            self._record_outcome(
                response, attempt=attempt, method=method, url=url, reason=reason
            )
            return response

    def get(self, url: str, **kwargs: Any) -> httpx.Response:
        """Retry destekli GET isteği."""
        return self.request("GET", url, **kwargs)

    def head(self, url: str, **kwargs: Any) -> httpx.Response:
        """Retry destekli HEAD isteği."""
        return self.request("HEAD", url, **kwargs)

    def options(self, url: str, **kwargs: Any) -> httpx.Response:
        """Retry destekli OPTIONS isteği."""
        return self.request("OPTIONS", url, **kwargs)

    def put(self, url: str, **kwargs: Any) -> httpx.Response:
        """Retry destekli PUT isteği."""
        return self.request("PUT", url, **kwargs)

    def delete(self, url: str, **kwargs: Any) -> httpx.Response:
        """Retry destekli DELETE isteği."""
        return self.request("DELETE", url, **kwargs)

    def post(self, url: str, **kwargs: Any) -> httpx.Response:
        """POST isteği. Sadece `Idempotency-Key` header'ı varsa retry edilir."""
        return self.request("POST", url, **kwargs)

    # -- Async API ------------------------------------------------------

    async def arequest(
        self,
        method: str,
        url: str,
        *,
        headers: Mapping[str, str] | None = None,
        **kwargs: Any,
    ) -> httpx.Response:
        """Retry mantığı uygulanmış async HTTP isteği yapar."""
        attempt = 0
        while True:
            if self._circuit_breaker is not None:
                self._circuit_breaker.before_request()

            try:
                response = await self._async_client.request(
                    method, url, headers=headers, **kwargs
                )
            except RETRYABLE_EXCEPTIONS as exc:
                should_retry, delay, reason = self._decide(
                    method, headers, attempt, exception=exc
                )
                if self._circuit_breaker is not None:
                    self._circuit_breaker.record_failure()
                if not should_retry:
                    log_request_failure(
                        self._logger,
                        attempt=attempt,
                        method=method,
                        url=url,
                        reason=reason,
                    )
                    raise
                log_retry_attempt(
                    self._logger,
                    attempt=attempt,
                    delay=delay,
                    reason=reason,
                    method=method,
                    url=url,
                )
                await asyncio.sleep(delay)
                attempt += 1
                continue

            should_retry, delay, reason = self._decide(
                method, headers, attempt, response=response
            )
            if should_retry:
                if self._circuit_breaker is not None:
                    self._circuit_breaker.record_failure()
                log_retry_attempt(
                    self._logger,
                    attempt=attempt,
                    delay=delay,
                    reason=reason,
                    method=method,
                    url=url,
                    status_code=response.status_code,
                )
                await asyncio.sleep(delay)
                attempt += 1
                continue

            self._record_outcome(
                response, attempt=attempt, method=method, url=url, reason=reason
            )
            return response

    async def aget(self, url: str, **kwargs: Any) -> httpx.Response:
        """Retry destekli async GET isteği."""
        return await self.arequest("GET", url, **kwargs)

    async def ahead(self, url: str, **kwargs: Any) -> httpx.Response:
        """Retry destekli async HEAD isteği."""
        return await self.arequest("HEAD", url, **kwargs)

    async def aoptions(self, url: str, **kwargs: Any) -> httpx.Response:
        """Retry destekli async OPTIONS isteği."""
        return await self.arequest("OPTIONS", url, **kwargs)

    async def aput(self, url: str, **kwargs: Any) -> httpx.Response:
        """Retry destekli async PUT isteği."""
        return await self.arequest("PUT", url, **kwargs)

    async def adelete(self, url: str, **kwargs: Any) -> httpx.Response:
        """Retry destekli async DELETE isteği."""
        return await self.arequest("DELETE", url, **kwargs)

    async def apost(self, url: str, **kwargs: Any) -> httpx.Response:
        """Async POST isteği. Sadece `Idempotency-Key` varsa retry edilir."""
        return await self.arequest("POST", url, **kwargs)

    # -- Ortak yardımcı ---------------------------------------------------

    def _record_outcome(
        self,
        response: httpx.Response,
        *,
        attempt: int,
        method: str,
        url: str,
        reason: str,
    ) -> None:
        """Retry döngüsü bittiğinde circuit breaker durumunu ve logu günceller."""
        if is_status_retryable(response.status_code):
            if self._circuit_breaker is not None:
                self._circuit_breaker.record_failure()
            log_request_failure(
                self._logger,
                attempt=attempt,
                method=method,
                url=url,
                reason=reason,
                status_code=response.status_code,
            )
        else:
            if self._circuit_breaker is not None:
                self._circuit_breaker.record_success()
            log_request_success(
                self._logger,
                attempt=attempt,
                method=method,
                url=url,
                status_code=response.status_code,
            )
