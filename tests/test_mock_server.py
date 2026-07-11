"""Maket (mock) sunucu senaryolarıyla RetryClient testleri.

Gerçek bir ağ bağlantısı kurulmaz; httpx.Client/AsyncClient'ın taşıma (transport)
katmanı `respx` ile taklit edilir. Örnek URL'ler her zaman RFC 6761'de ayrılmış
`example.test` alan adını kullanır, gerçek bir sunucuya işaret etmez.
"""

from __future__ import annotations

import random

import httpx
import pytest
import respx

from retry_client.circuit_breaker import CircuitBreaker, CircuitBreakerOpenError
from retry_client.client import RetryClient
from retry_client.config import RetryConfig

BASE_URL = "https://example.test"


def _fast_config(**overrides: object) -> RetryConfig:
    """Testlerin gerçek zaman beklemeden hızlı çalışması için küçük gecikmeli config."""
    defaults: dict[str, object] = {
        "max_retries": 3,
        "base_delay": 0.01,
        "max_delay": 0.02,
        "multiplier": 2.0,
    }
    defaults.update(overrides)
    return RetryConfig(**defaults)


@respx.mock
def test_http_429_with_retry_after_then_success() -> None:
    """429 + Retry-After alındıktan sonra başarılı yanıt dönmeli."""
    route = respx.get(f"{BASE_URL}/resource").mock(
        side_effect=[
            httpx.Response(429, headers={"Retry-After": "0"}),
            httpx.Response(200, json={"ok": True}),
        ]
    )

    with RetryClient(config=_fast_config(), rng=random.Random(0)) as client:
        response = client.get(f"{BASE_URL}/resource")

    assert response.status_code == 200
    assert route.call_count == 2


@respx.mock
def test_http_503_retried_with_backoff_then_success() -> None:
    """Retry-After olmayan 503 yanıtı exponential backoff ile tekrar denenmeli."""
    route = respx.get(f"{BASE_URL}/resource").mock(
        side_effect=[
            httpx.Response(503),
            httpx.Response(503),
            httpx.Response(200, json={"ok": True}),
        ]
    )

    with RetryClient(config=_fast_config(), rng=random.Random(0)) as client:
        response = client.get(f"{BASE_URL}/resource")

    assert response.status_code == 200
    assert route.call_count == 3


@respx.mock
def test_network_error_retried_then_success() -> None:
    """Bağlantı hatası (ConnectError) sonrası retry ile başarıya ulaşılmalı."""
    route = respx.get(f"{BASE_URL}/resource").mock(
        side_effect=[
            httpx.ConnectError("connection refused"),
            httpx.Response(200, json={"ok": True}),
        ]
    )

    with RetryClient(config=_fast_config(), rng=random.Random(0)) as client:
        response = client.get(f"{BASE_URL}/resource")

    assert response.status_code == 200
    assert route.call_count == 2


@respx.mock
def test_post_without_idempotency_key_is_not_retried() -> None:
    """Idempotency-Key olmayan POST, 503 alsa bile tekrar denenmemeli."""
    route = respx.post(f"{BASE_URL}/orders").mock(return_value=httpx.Response(503))

    with RetryClient(config=_fast_config(), rng=random.Random(0)) as client:
        response = client.post(f"{BASE_URL}/orders", json={"item": "book"})

    assert response.status_code == 503
    assert route.call_count == 1


@respx.mock
def test_post_with_idempotency_key_is_retried_then_success() -> None:
    """Idempotency-Key bulunan POST, geçici hatadan sonra retry edilip başarmalı."""
    route = respx.post(f"{BASE_URL}/orders").mock(
        side_effect=[
            httpx.Response(503),
            httpx.Response(201, json={"id": "order-1"}),
        ]
    )

    with RetryClient(config=_fast_config(), rng=random.Random(0)) as client:
        response = client.post(
            f"{BASE_URL}/orders",
            json={"item": "book"},
            headers={"Idempotency-Key": "order-1"},
        )

    assert response.status_code == 201
    assert route.call_count == 2


@respx.mock
def test_retries_exhausted_returns_last_response_without_raising() -> None:
    """max_retries dolduğunda son (başarısız) response exception fırlatmadan döner."""
    route = respx.get(f"{BASE_URL}/resource").mock(return_value=httpx.Response(503))

    with RetryClient(
        config=_fast_config(max_retries=2), rng=random.Random(0)
    ) as client:
        response = client.get(f"{BASE_URL}/resource")

    assert response.status_code == 503
    assert route.call_count == 3  # ilk deneme + 2 retry


@respx.mock
def test_non_retryable_status_returns_immediately() -> None:
    """404 gibi retry kapsamı dışındaki durumlarda tek deneme yapılmalı."""
    route = respx.get(f"{BASE_URL}/missing").mock(return_value=httpx.Response(404))

    with RetryClient(config=_fast_config(), rng=random.Random(0)) as client:
        response = client.get(f"{BASE_URL}/missing")

    assert response.status_code == 404
    assert route.call_count == 1


@respx.mock
def test_circuit_breaker_opens_and_blocks_further_requests() -> None:
    """Ardışık hatalar eşiği aştığında circuit breaker sonraki isteği engellemeli."""
    respx.get(f"{BASE_URL}/resource").mock(return_value=httpx.Response(503))
    breaker = CircuitBreaker(failure_threshold=2, recovery_timeout=60)

    with RetryClient(
        config=_fast_config(max_retries=0),
        circuit_breaker=breaker,
        rng=random.Random(0),
    ) as client:
        client.get(f"{BASE_URL}/resource")
        client.get(f"{BASE_URL}/resource")

        with pytest.raises(CircuitBreakerOpenError):
            client.get(f"{BASE_URL}/resource")


@respx.mock
@pytest.mark.asyncio
async def test_async_get_retries_on_503_then_success() -> None:
    """Async istekte de aynı retry mantığı uygulanmalı."""
    route = respx.get(f"{BASE_URL}/resource").mock(
        side_effect=[
            httpx.Response(503),
            httpx.Response(200, json={"ok": True}),
        ]
    )

    async with RetryClient(config=_fast_config(), rng=random.Random(0)) as client:
        response = await client.aget(f"{BASE_URL}/resource")

    assert response.status_code == 200
    assert route.call_count == 2
