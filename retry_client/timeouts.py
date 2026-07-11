"""
Timeout yönetimi katmanı. RetryConfig içindeki 4 ayrı zaman aşımı değerini (connect/read/write/pool) alıp
httpx'in anlayacağı bir `httpx.Timeout`
nesnesine çevirir.

Sorumlu: Nehir Doğan
Bağımlılık: config.py (RetryConfig), httpx (sadece Timeout tipi için).
"""
from __future__ import annotations
import httpx
from .config import RetryConfig

#her aşamanın bekleme süresini birbirinden ayrı değerlendiriyoruz çünkü
#sunucuya bağlanmak veya bağlantı havuzunda boşta bağlantı aramak için beklenmesi gereken süreler birbirinden farklıdır
def build_httpx_timeout(config: RetryConfig) -> httpx.Timeout:
    return httpx.Timeout(
        connect=config.connect_timeout,
        read=config.read_timeout,
        write=config.write_timeout,
        pool=config.pool_timeout,
    )

#belirli istekler için belirli aşamaların timemout değerlerini değiştirmek için kullanılır.
def override_timeout(
    config: RetryConfig,
    *,
    connect: float | None = None,
    read: float | None = None,
    write: float | None = None,
    pool: float | None = None,
) -> httpx.Timeout:

    return httpx.Timeout(
        connect=connect if connect is not None else config.connect_timeout,
        read=read if read is not None else config.read_timeout,
        write=write if write is not None else config.write_timeout,
        pool=pool if pool is not None else config.pool_timeout,
    )


def total_worst_case_timeout(config: RetryConfig, max_retries: int | None = None) -> float:
    retries = max_retries if max_retries is not None else config.max_retries

    # Her denemenin kendi ağ zaman aşımı (en kötü ihtimalle connect+read+write)
    per_attempt_network_timeout = (
        config.connect_timeout + config.read_timeout + config.write_timeout
    )

    # Her deneme arasındaki en uzun olası bekleme, max_delay ile sınırlıdır
    worst_case_wait_between_attempts = config.max_delay

    total_attempts = retries + 1  # ilk istek + retry'ler
    return (total_attempts * per_attempt_network_timeout) + (
        retries * worst_case_wait_between_attempts
    )