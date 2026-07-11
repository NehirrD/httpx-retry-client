"""Circuit breaker testleri."""

import pytest

from retry_client.circuit_breaker import (
    CircuitBreaker,
    CircuitBreakerOpenError,
    CircuitState,
)


class FakeClock:
    """Testlerde zamanı elle ilerletmek için sahte saat."""

    def __init__(self) -> None:
        self.current = 0.0

    def __call__(self) -> float:
        return self.current

    def advance(self, seconds: float) -> None:
        self.current += seconds


def test_initial_state_is_closed() -> None:
    """Circuit breaker başlangıçta kapalı olmalıdır."""
    breaker = CircuitBreaker()

    assert breaker.state is CircuitState.CLOSED
    assert breaker.failure_count == 0
    assert breaker.allow_request() is True


def test_circuit_opens_after_threshold() -> None:
    """Hata eşiğine ulaşıldığında devre açılmalıdır."""
    breaker = CircuitBreaker(
        failure_threshold=3,
        recovery_timeout=10,
    )

    breaker.record_failure()
    breaker.record_failure()

    assert breaker.state is CircuitState.CLOSED

    breaker.record_failure()

    assert breaker.state is CircuitState.OPEN
    assert breaker.allow_request() is False


def test_open_circuit_rejects_request() -> None:
    """Açık devre yeni isteği reddetmelidir."""
    breaker = CircuitBreaker(
        failure_threshold=1,
        recovery_timeout=10,
    )
    breaker.record_failure()

    with pytest.raises(CircuitBreakerOpenError):
        breaker.before_request()


def test_open_circuit_moves_to_half_open_after_timeout() -> None:
    """Recovery süresi dolduğunda devre half-open olmalıdır."""
    clock = FakeClock()
    breaker = CircuitBreaker(
        failure_threshold=1,
        recovery_timeout=5,
        time_provider=clock,
    )

    breaker.record_failure()
    assert breaker.state is CircuitState.OPEN

    clock.advance(5)

    assert breaker.state is CircuitState.HALF_OPEN
    assert breaker.allow_request() is True


def test_success_in_half_open_closes_circuit() -> None:
    """Half-open durumdaki başarılı istek devreyi kapatmalıdır."""
    clock = FakeClock()
    breaker = CircuitBreaker(
        failure_threshold=1,
        recovery_timeout=5,
        time_provider=clock,
    )

    breaker.record_failure()
    clock.advance(5)

    assert breaker.state is CircuitState.HALF_OPEN

    breaker.record_success()

    assert breaker.state is CircuitState.CLOSED
    assert breaker.failure_count == 0


def test_failure_in_half_open_reopens_circuit() -> None:
    """Half-open durumdaki hata devreyi yeniden açmalıdır."""
    clock = FakeClock()
    breaker = CircuitBreaker(
        failure_threshold=1,
        recovery_timeout=5,
        time_provider=clock,
    )

    breaker.record_failure()
    clock.advance(5)

    assert breaker.state is CircuitState.HALF_OPEN

    breaker.record_failure()

    assert breaker.state is CircuitState.OPEN
    assert breaker.allow_request() is False


def test_success_resets_failure_count() -> None:
    """Başarı ardışık hata sayısını sıfırlamalıdır."""
    breaker = CircuitBreaker(failure_threshold=3)

    breaker.record_failure()
    breaker.record_failure()

    assert breaker.failure_count == 2

    breaker.record_success()

    assert breaker.failure_count == 0
    assert breaker.state is CircuitState.CLOSED


@pytest.mark.parametrize(
    ("failure_threshold", "recovery_timeout"),
    [
        (0, 10),
        (-1, 10),
        (1, -1),
    ],
)
def test_invalid_configuration_raises_value_error(
    failure_threshold: int,
    recovery_timeout: float,
) -> None:
    """Geçersiz ayarlar ValueError üretmelidir."""
    with pytest.raises(ValueError):
        CircuitBreaker(
            failure_threshold=failure_threshold,
            recovery_timeout=recovery_timeout,
        )