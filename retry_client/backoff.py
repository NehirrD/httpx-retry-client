"""
Exponential backoff ve jitter hesaplama katmanı.
Sorumlu: Nehir Doğan
Bağımlılık: config.py (RetryConfig) — bu modül SADECE config.py'a bağımlıdır,
"""

from __future__ import annotations
import random
from typing import Callable, Dict, Optional
from .config import RetryConfig

# Bir "jitter stratejisi", (hesaplanan_gecikme, config, rng) alıp yeni bir gecikme (float) döndüren bir fonksiyonlar.
JitterStrategy = Callable[[float, RetryConfig, random.Random], float]


def no_jitter(delay: float, config: RetryConfig, rng: random.Random) -> float: #testler için jitter uygulamadan gecikme döndürür:
    return delay


def full_jitter(delay: float, config: RetryConfig, rng: random.Random) -> float: #klasik jitter yöntemi. 0.0 - 1.0 arası çarpanlar kullanarak rastgele gecikme üretir
    min_factor, max_factor = config.jitter_range
    factor = rng.uniform(min_factor, max_factor)
    return delay * factor


def equal_jitter(delay: float, config: RetryConfig, rng: random.Random) -> float: #gecikmenin yarısı sabit kalır, diğer yarısına rastgelelik uygular
    half = delay / 2
    min_factor, max_factor = config.jitter_range
    extra = half * rng.uniform(min_factor, max_factor)
    return half + extra


def decorrelated_jitter(delay: float, config: RetryConfig, rng: random.Random) -> float:
    #bir önceki gecikmeyi baz alarak, base_delay ile arasında rastgele bir değer seçer.
    #diğer stratejilerden farkı sadece mevcut "attempt" sayısına değil, bir önceki denemede gerçekten üretilen gecikmeye bağlıdır:
    upper_bound = max(config.base_delay, delay * 3)
    return rng.uniform(config.base_delay, upper_bound)


# İsimden stratejiye erişim:
# "RETRY_JITTER_STRATEGY=full" gibi bir ortam değişkeniyle string olarak strateji seçmek isterse burası kullanılır:

_JITTER_STRATEGIES: Dict[str, JitterStrategy] = {
    "none": no_jitter,
    "full": full_jitter,
    "equal": equal_jitter,
    "decorrelated": decorrelated_jitter,
}


def get_jitter_strategy(name: str) -> JitterStrategy:
    try:
        return _JITTER_STRATEGIES[name]
    except KeyError as exc:
        valid = ", ".join(_JITTER_STRATEGIES)
        raise ValueError(
            f"Bilinmeyen jitter stratejisi: {name!r}. Geçerli değerler: {valid}"
        ) from exc

def calculate_delay(
    attempt: int,
    config: RetryConfig,
    jitter_strategy: JitterStrategy = full_jitter,
    rng: Optional[random.Random] = None,
) -> float:

    if attempt < 0:
        raise ValueError("attempt negatif olamaz.")

    if rng is None:
        rng = random.Random()

    # 1) Exponential backoff hesapla:
    raw_delay = config.base_delay * (config.multiplier ** attempt)

    # 2) max_delay ile sınırla:
    capped_delay = min(raw_delay, config.max_delay)

    # 3) Seçilen jitter stratejisini uygula:
    jittered_delay = jitter_strategy(capped_delay, config, rng)

    # 4) Güvenlik ağı: jitter fonksiyonu hatalı bir değer üretse bile sonucu güvenli aralığa çek:
    return max(0.0, min(jittered_delay, config.max_delay))