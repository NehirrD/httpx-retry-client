"""Basit circuit breaker uygulaması."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Callable


class CircuitState(str, Enum):
    """Circuit breaker durumları."""

    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


class CircuitBreakerOpenError(RuntimeError):
    """Circuit breaker açıkken istek yapılmaya çalışıldığında oluşur."""


@dataclass
class CircuitBreaker:
    """Art arda hatalarda istekleri geçici olarak durduran circuit breaker.

    Args:
        failure_threshold: Devrenin açılması için gereken ardışık hata sayısı.
        recovery_timeout: Devrenin tekrar deneme durumuna geçmesi için bekleme süresi.
        time_provider: Testlerde zamanı kontrol etmek için kullanılan fonksiyon.
    """

    failure_threshold: int = 5
    recovery_timeout: float = 30.0
    time_provider: Callable[[], float] = time.monotonic

    _state: CircuitState = field(
        default=CircuitState.CLOSED,
        init=False,
    )
    _failure_count: int = field(default=0, init=False)
    _opened_at: float | None = field(default=None, init=False)

    def __post_init__(self) -> None:
        """Yapılandırma değerlerini doğrular."""
        if self.failure_threshold < 1:
            raise ValueError("failure_threshold en az 1 olmalıdır.")

        if self.recovery_timeout < 0:
            raise ValueError("recovery_timeout negatif olamaz.")

    @property
    def state(self) -> CircuitState:
        """Güncel circuit breaker durumunu döndürür."""
        self._refresh_state()
        return self._state

    @property
    def failure_count(self) -> int:
        """Ardışık hata sayısını döndürür."""
        return self._failure_count

    def allow_request(self) -> bool:
        """Yeni bir isteğe izin verilip verilmediğini döndürür."""
        self._refresh_state()
        return self._state is not CircuitState.OPEN

    def before_request(self) -> None:
        """İstekten önce circuit durumunu kontrol eder.

        Raises:
            CircuitBreakerOpenError: Devre açık durumdaysa.
        """
        if not self.allow_request():
            raise CircuitBreakerOpenError(
                "Circuit breaker açık; istek geçici olarak engellendi."
            )

    def record_success(self) -> None:
        """Başarılı istekte circuit breaker'ı sıfırlar."""
        self._failure_count = 0
        self._opened_at = None
        self._state = CircuitState.CLOSED

    def record_failure(self) -> None:
        """Başarısız isteği kaydeder ve gerekirse devreyi açar."""
        self._failure_count += 1

        if self._state is CircuitState.HALF_OPEN:
            self._open()
            return

        if self._failure_count >= self.failure_threshold:
            self._open()

    def reset(self) -> None:
        """Circuit breaker durumunu manuel olarak sıfırlar."""
        self.record_success()

    def _open(self) -> None:
        """Devreyi açık duruma geçirir."""
        self._state = CircuitState.OPEN
        self._opened_at = self.time_provider()

    def _refresh_state(self) -> None:
        """Bekleme süresi dolduysa OPEN durumundan HALF_OPEN'a geçer."""
        if self._state is not CircuitState.OPEN:
            return

        if self._opened_at is None:
            return

        elapsed = self.time_provider() - self._opened_at

        if elapsed >= self.recovery_timeout:
            self._state = CircuitState.HALF_OPEN