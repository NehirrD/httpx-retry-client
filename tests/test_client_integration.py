"""Uçtan uca RetryClient entegrasyon testleri.

Nehir'in config/backoff/timeout katmanı ile Dilara'nın policy/retry-after/
circuit-breaker/logging katmanının RetryClient üzerinden doğru şekilde bir
araya geldiğini doğrular. Gerçek bir sunucuya bağlanılmaz; `respx` ile taklit
edilen, RFC 6761 test alan adı `example.test` kullanılır.
"""

from __future__ import annotations

import random

import httpx
import pytest
import respx

from retry_client import RetryClient
from retry_client.config import RetryConfig

BASE_URL = "https://example.test"


@pytest.mark.parametrize("method", ["GET", "HEAD", "OPTIONS", "PUT", "DELETE"])
@respx.mock
def test_safe_methods_are_retried_on_502(method: str) -> None:
    """GET/HEAD/OPTIONS/PUT/DELETE her zaman güvenli sayılıp retry edilmeli."""
    route = respx.route(method=method, url=f"{BASE_URL}/resource").mock(
        side_effect=[httpx.Response(502), httpx.Response(200)]
    )

    config = RetryConfig(max_retries=2, base_delay=0.01, max_delay=0.02)
    with RetryClient(config=config, rng=random.Random(0)) as client:
        response = client.request(method, f"{BASE_URL}/resource")

    assert response.status_code == 200
    assert route.call_count == 2


@respx.mock
def test_base_url_and_relative_path_are_combined() -> None:
    """RetryClient base_url ile oluşturulduğunda göreli path'ler doğru birleşmeli."""
    route = respx.get(f"{BASE_URL}/v1/ping").mock(return_value=httpx.Response(200))

    with RetryClient(base_url=BASE_URL, config=RetryConfig()) as client:
        response = client.get("/v1/ping")

    assert response.status_code == 200
    assert route.called


@respx.mock
def test_custom_headers_are_forwarded() -> None:
    """Kullanıcının verdiği header'lar isteğe olduğu gibi iletilmeli."""
    route = respx.get(f"{BASE_URL}/resource").mock(return_value=httpx.Response(200))

    with RetryClient(config=RetryConfig()) as client:
        client.get(f"{BASE_URL}/resource", headers={"X-Trace-Id": "abc-123"})

    sent_request = route.calls.last.request
    assert sent_request.headers["X-Trace-Id"] == "abc-123"


@respx.mock
def test_default_config_is_used_when_not_provided() -> None:
    """Config verilmezse RetryConfig() varsayılanları geçerli olmalı."""
    route = respx.get(f"{BASE_URL}/resource").mock(return_value=httpx.Response(200))

    with RetryClient() as client:
        response = client.get(f"{BASE_URL}/resource")

    assert response.status_code == 200
    assert route.called


@respx.mock
@pytest.mark.asyncio
async def test_async_context_manager_closes_client() -> None:
    """`async with` bloğu bittiğinde async client kapatılmalı."""
    respx.get(f"{BASE_URL}/resource").mock(return_value=httpx.Response(200))

    async with RetryClient() as client:
        response = await client.aget(f"{BASE_URL}/resource")
        assert response.status_code == 200

    assert client._async_client.is_closed


@respx.mock
def test_sync_context_manager_closes_client() -> None:
    """`with` bloğu bittiğinde sync client kapatılmalı."""
    respx.get(f"{BASE_URL}/resource").mock(return_value=httpx.Response(200))

    with RetryClient() as client:
        client.get(f"{BASE_URL}/resource")

    assert client._client.is_closed
