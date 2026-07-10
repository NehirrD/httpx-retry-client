"""
RetryConfig için birim (unit) testleri
Sorumlu: Nehir Doğan
Test edilen modül: retry_client/config.py
Bu dosyada 3 grup test vardır:
    1) Varsayılan değerlerin ve geçerli konfigürasyonların doğru oluşması
    2) Her bir validasyon kuralının gerçekten hata fırlattığının kontrolü
    3) from_env() ile ortam değişkenlerinden okuma
"""
from __future__ import annotations
import dataclasses
import pytest
from retry_client.config import RetryConfig

#Varsayılan değerler ve normal (geçerli) kullanım:

def test_default_values(): #config.py de verilen default değerleri kullanır:
    config = RetryConfig()

    assert config.max_retries == 3
    assert config.base_delay == 1.0
    assert config.max_delay == 30.0
    assert config.multiplier == 2.0
    assert config.jitter_range == (0.0, 1.0)
    assert config.connect_timeout == 5.0
    assert config.read_timeout == 10.0
    assert config.write_timeout == 10.0
    assert config.pool_timeout == 5.0


def test_custom_values_are_accepted(): #amaç: özel değerler verildiğinde hata fırlatmadan saklanabilmeli
    config = RetryConfig(
        max_retries=5,
        base_delay=0.5,
        max_delay=20.0,
        multiplier=1.5,
        jitter_range=(0.2, 0.8),
        connect_timeout=2.0,
        read_timeout=15.0,
        write_timeout=15.0,
        pool_timeout=3.0,
    )

    assert config.max_retries == 5
    assert config.base_delay == 0.5
    assert config.max_delay == 20.0
    assert config.multiplier == 1.5
    assert config.jitter_range == (0.2, 0.8)


def test_max_retries_zero_is_valid(): #max_retries= 0 geçerli bir değer olup olmadığını kontrol eder
    config = RetryConfig(max_retries=0)
    assert config.max_retries == 0


def test_config_is_immutable(): #RetryConfig @dataclass(frozen=True) olarak tanimlandigi icin, olusturulduktan sonra hicbir alani degistirilemez olmali.
    config = RetryConfig()

    with pytest.raises(dataclasses.FrozenInstanceError):
        # noinspection PyDataclass
        config.max_retries = 10 #Değiştirilemiyor testten başarıyla geçti



#Validasyon kurallari - her birinin gercekten hata firlattigini kontrol ediyoruz.
#pytest.raises(...) bir "context manager": "with" blogu icinde calisan kod beklenen hatayi firlatirsa test basarili olur; firlatmazsa test basarisiz (fail) olur.


def test_negative_max_retries_raises():
    with pytest.raises(ValueError, match="max_retries negatif olamaz"):
        RetryConfig(max_retries=-1)


def test_zero_base_delay_raises():
    with pytest.raises(ValueError, match="base_delay pozitif bir değer olmalıdır"):
        RetryConfig(base_delay=0)


def test_negative_base_delay_raises():
    with pytest.raises(ValueError, match="base_delay pozitif bir değer olmalıdır"):
        RetryConfig(base_delay=-1.0)


def test_zero_max_delay_raises():
    with pytest.raises(ValueError, match="max_delay pozitif bir değer olmalıdır"):
        RetryConfig(max_delay=0)


def test_max_delay_smaller_than_base_delay_raises(): #max_delay, base_delay'den küçük olursa exponential backoff ilk adimda üst sınıra takılır.
    with pytest.raises(
        ValueError, match="max_delay, base_delay değerinden küçük olamaz"
    ):
        RetryConfig(base_delay=10.0, max_delay=5.0)


def test_multiplier_equal_to_one_raises(): #multiplier=1.0 olursa gecikme hic artmaz - 1.0'dan büyük olması zorunlu.
    with pytest.raises(ValueError, match="multiplier 1.0'dan büyük olmalıdır"):
        RetryConfig(multiplier=1.0)


def test_multiplier_smaller_than_one_raises():
    with pytest.raises(ValueError, match="multiplier 1.0'dan büyük olmalıdır"):
        RetryConfig(multiplier=0.5)


def test_negative_jitter_range_raises():
    with pytest.raises(ValueError, match="jitter_range değerleri negatif olamaz"):
        RetryConfig(jitter_range=(-0.1, 1.0))


def test_jitter_range_min_greater_than_max_raises():
    with pytest.raises(
        ValueError, match="jitter_range içindeki min değer, max değerden büyük olamaz"
    ):
        RetryConfig(jitter_range=(0.9, 0.1))


@pytest.mark.parametrize(
    "timeout_field",
    ["connect_timeout", "read_timeout", "write_timeout", "pool_timeout"],
)
def test_zero_or_negative_timeout_raises(timeout_field):
    #tek bir test fonksiyonunu 4 farklı değer için (connect/read/write/pool) otomatik olarak 4 kez çalıştırır.
    with pytest.raises(ValueError, match=f"{timeout_field} pozitif bir değer olmalıdır"):
        RetryConfig(**{timeout_field: 0})



# from_env() -- ortam degiskenlerinden okuma

def test_from_env_uses_defaults_when_no_env_vars_set(monkeypatch): #hiçbir env variable tanımlı değilse default kullanılmalı:
    for name in ("RETRY_MAX_RETRIES", "RETRY_BASE_DELAY", "RETRY_MAX_DELAY", "RETRY_MULTIPLIER"):
        monkeypatch.delenv(name, raising=False)

    config = RetryConfig.from_env()

    assert config.max_retries == 3
    assert config.base_delay == 1.0
    assert config.max_delay == 30.0
    assert config.multiplier == 2.0


def test_from_env_reads_environment_variables(monkeypatch): #env variable tanımlıyken doğru tipe çevrilir
    monkeypatch.setenv("RETRY_MAX_RETRIES", "7")
    monkeypatch.setenv("RETRY_BASE_DELAY", "2.5")
    monkeypatch.setenv("RETRY_MAX_DELAY", "60")
    monkeypatch.setenv("RETRY_MULTIPLIER", "3.0")

    config = RetryConfig.from_env()

    assert config.max_retries == 7
    assert config.base_delay == 2.5
    assert config.max_delay == 60.0
    assert config.multiplier == 3.0


def test_from_env_respects_custom_prefix(monkeypatch): #farklı prefixlerde doğru variable okunabilmeli:
    monkeypatch.setenv("MYAPP_MAX_RETRIES", "9")
    monkeypatch.delenv("RETRY_MAX_RETRIES", raising=False)

    config = RetryConfig.from_env(prefix="MYAPP_")

    assert config.max_retries == 9


def test_from_env_still_validates(): #geçersiz değerlerde hata fırlatılmalı:
    import os

    os.environ["RETRY_MULTIPLIER"] = "1.0"
    try:
        with pytest.raises(ValueError, match="multiplier 1.0'dan büyük olmalıdır"):
            RetryConfig.from_env()
    finally:
        del os.environ["RETRY_MULTIPLIER"]