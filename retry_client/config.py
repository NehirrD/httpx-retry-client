"""Retry istemcisi için yapılandırma (configuration) katmanı.
Sorumlu: Nehir Doğan
Bağımlılık: yok (paketin en temel modülüdür).
"""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import Tuple


@dataclass(frozen=True)
class RetryConfig:

    max_retries: int = 3 #Bir isteğin en fazla kaç kez yeniden denenebileceği - ilk deneme hariç
    base_delay: float = 1.0 #İlk retry denemesi öncesi beklenecek taban süre - saniye
    max_delay: float = 30.0 #Exponential backoff'un ulaşabileceği üst sınır
    multiplier: float = 2.0 #Her denemede bekleme süresinin çarpılacağı katsayı
    jitter_range: Tuple[float, float] = field(default=(0.0, 1.0)) #hesaplanan gecikmeye uygulanacak rastgele çarpan

    connect_timeout: float = 5.0 #bağlantı için zamanaşımı
    read_timeout: float = 10.0 #sunucudan veri okuma için zaman aşımı
    write_timeout: float = 10.0 #sunucuya veri gönderme için zaman aşımı
    pool_timeout: float = 5.0 #bağlantı havuzundan bağlantı almak için zaman aşımı

    def __post_init__(self) -> None: #mantıksal tutarlılık doğrular

        if self.max_retries < 0:
            raise ValueError("max_retries negatif olamaz.")

        if self.base_delay <= 0:
            raise ValueError("base_delay pozitif bir değer olmalıdır.")

        if self.max_delay <= 0:
            raise ValueError("max_delay pozitif bir değer olmalıdır.")

        if self.max_delay < self.base_delay:
            raise ValueError("max_delay, base_delay değerinden küçük olamaz.")

        if self.multiplier <= 1.0:
            raise ValueError(
                "multiplier 1.0'dan büyük olmalıdır (aksi halde exponential "
                "backoff artış göstermez)."
            )

        min_jitter, max_jitter = self.jitter_range
        if min_jitter < 0 or max_jitter < 0:
            raise ValueError("jitter_range değerleri negatif olamaz.")
        if min_jitter > max_jitter:
            raise ValueError(
                "jitter_range içindeki min değer, max değerden büyük olamaz."
            )

        for name, value in (
            ("connect_timeout", self.connect_timeout),
            ("read_timeout", self.read_timeout),
            ("write_timeout", self.write_timeout),
            ("pool_timeout", self.pool_timeout),
        ):
            if value <= 0:
                raise ValueError(f"{name} pozitif bir değer olmalıdır.")

    @classmethod
    def from_env(cls, prefix: str = "RETRY_") -> "RetryConfig": #Ortam değişkenlerinden bir RetryConfig oluşturur.

        import os

        def _get_float(name: str, default: float) -> float:
            raw = os.environ.get(f"{prefix}{name}")
            return float(raw) if raw is not None else default

        def _get_int(name: str, default: int) -> int:
            raw = os.environ.get(f"{prefix}{name}")
            return int(raw) if raw is not None else default

        return cls(
            max_retries=_get_int("MAX_RETRIES", 3),
            base_delay=_get_float("BASE_DELAY", 1.0),
            max_delay=_get_float("MAX_DELAY", 30.0),
            multiplier=_get_float("MULTIPLIER", 2.0),
        )