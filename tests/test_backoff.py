"""
Backoff ve jitter hesaplama katmanı için birim (unit) testleri.
Sorumlu: Nehir Doğan
Test edilen modül: retry_client/backoff.py
Bu dosyada 3 grup test vardır:
    1) calculate_delay() -- exponential backoff'un doğru hesaplandığı, max_delay ile sınırlandığı ve hatalı girdilerde hata fırlattığı
    2) Jitter stratejileri (no_jitter / full_jitter / equal_jitter / decorrelated_jitter) -- her birinin kendi matematiksel kuralına
       uyduğu, deterministik (seed'li) random.Random ile test edilir
    3) get_jitter_strategy() -- isimden stratejiye doğru eşleme yapıldığı ve bilinmeyen isimlerde hata fırlatıldığı

Not: Jitter fonksiyonları rastgelelik içerdiği için testlerde her zaman
sabit bir seed ile oluşturulmuş random.Random(seed) kullanıyoruz. - böylece her zaman aynı sonucu üretiyoruz.
"""
from __future__ import annotations
import random
import pytest
from retry_client.backoff import (
    calculate_delay,
    decorrelated_jitter,
    equal_jitter,
    full_jitter,
    get_jitter_strategy,
    no_jitter,
)
from retry_client.config import RetryConfig


# Ortak sabit config -- testler arasında tutarlılık için tek bir yerden tanımlanıyor. Farklı bir davranış test edilmek istendiğinde config
# doğrudan üzerine yazılamadığı için yeni bri RetryConfig örneği oluşturulur

BASE_CONFIG = RetryConfig(
    max_retries=5,
    base_delay=1.0,
    max_delay=30.0,
    multiplier=2.0,
    jitter_range=(0.0, 1.0),
)



#calculate_delay() -- exponential backoff

def test_calculate_delay_exponential_growth_without_jitter(): #no_jitter stratejisiyle, gecikmenin base_delay * multiplier**attempt formülüne tam olarak uyduğunu kontrol eder:
    rng = random.Random(0)

    assert calculate_delay(0, BASE_CONFIG, jitter_strategy=no_jitter, rng=rng) == 1.0
    assert calculate_delay(1, BASE_CONFIG, jitter_strategy=no_jitter, rng=rng) == 2.0
    assert calculate_delay(2, BASE_CONFIG, jitter_strategy=no_jitter, rng=rng) == 4.0
    assert calculate_delay(3, BASE_CONFIG, jitter_strategy=no_jitter, rng=rng) == 8.0
    assert calculate_delay(4, BASE_CONFIG, jitter_strategy=no_jitter, rng=rng) == 16.0


def test_calculate_delay_is_capped_at_max_delay(): #attempt arttıkça hesaplanan ham gecikme max_delay'i aşsa bile, sonuç asla max_delay'den büyük olmamalı.
    rng = random.Random(0)

    # 2^5 * 1.0 = 32.0 bu max_delay=30.0'ı aşar, yani cap devreye girmeli
    assert calculate_delay(5, BASE_CONFIG, jitter_strategy=no_jitter, rng=rng) == 30.0
    # çok yüksek bir attempt değeri de aynı şekilde 30.0'da sabit kalmalı
    assert calculate_delay(50, BASE_CONFIG, jitter_strategy=no_jitter, rng=rng) == 30.0

def test_calculate_delay_negative_attempt_raises():
    with pytest.raises(ValueError, match="attempt negatif olamaz"):
        calculate_delay(-1, BASE_CONFIG)


def test_calculate_delay_zero_attempt_equals_base_delay():
    rng = random.Random(0)
    assert calculate_delay(0, BASE_CONFIG, jitter_strategy=no_jitter, rng=rng) == BASE_CONFIG.base_delay


def test_calculate_delay_is_deterministic_with_same_seed(): #Aynı seed ile oluşturulmuş iki random.Random örneği, aynı attempt ve aynı jitter stratejisiyle her zaman aynı sonucu üretmeli.
    rng1 = random.Random(123)
    rng2 = random.Random(123)
    result1 = calculate_delay(3, BASE_CONFIG, jitter_strategy=full_jitter, rng=rng1)
    result2 = calculate_delay(3, BASE_CONFIG, jitter_strategy=full_jitter, rng=rng2)
    assert result1 == result2


def test_calculate_delay_result_never_negative_or_above_max_delay(): #hangi jitter stratejisi kullanılırsa kullanılsın, sonuç her zaman [0, max_delay] aralığında kalmalı.
    rng = random.Random(7)
    strategies = [no_jitter, full_jitter, equal_jitter, decorrelated_jitter]

    for strategy in strategies:
        for attempt in range(8):
            delay = calculate_delay(attempt, BASE_CONFIG, jitter_strategy=strategy, rng=rng)
            assert 0.0 <= delay <= BASE_CONFIG.max_delay


def test_calculate_delay_uses_default_rng_when_none_given(): #rng parametresi verilmezse fonksiyon kendi random.Random() örneğini oluşturup çalışmaya devam edebilmeli.
    delay = calculate_delay(2, BASE_CONFIG)
    assert 0.0 <= delay <= BASE_CONFIG.max_delay


#Jitter stratejileri - her biri kendi matematiksel kuralına uymalı

def test_no_jitter_returns_delay_unchanged():
    rng = random.Random(0)
    assert no_jitter(10.0, BASE_CONFIG, rng) == 10.0
    assert no_jitter(0.0, BASE_CONFIG, rng) == 0.0


def test_full_jitter_stays_within_jitter_range_bounds(): #full_jitter, delay * factor hesaplar; factor jitter_range içinden
    #seçildiği için sonuç her zaman [delay * min_factor, delay * max_factor] aralığında olmalı.
    config = RetryConfig(jitter_range=(0.2, 0.8))
    rng = random.Random(42)
    delay = 10.0

    for _ in range(200):
        result = full_jitter(delay, config, rng)
        assert 2.0 <= result <= 8.0


def test_full_jitter_deterministic_with_seed():
    delay = 10.0
    result1 = full_jitter(delay, BASE_CONFIG, random.Random(99))
    result2 = full_jitter(delay, BASE_CONFIG, random.Random(99))
    assert result1 == result2


def test_full_jitter_with_fixed_range_is_exact(): #jitter_range=(0.5, 0.5) gibi tek noktalı bir aralık verilirse,
    # rng.uniform hep aynı sabit değeri döndürür ve sonuç kesin olarak hesaplanabilir hale gelir.
    config = RetryConfig(jitter_range=(0.5, 0.5))
    rng = random.Random(0)
    assert full_jitter(10.0, config, rng) == 5.0


def test_equal_jitter_stays_within_expected_bounds(): #equal_jitter: sonuç = half + half * factor, factor jitter_range içinden geldiği için
    # sonuç [half, half + half*max_factor] aralığında olmalı
    rng = random.Random(1)
    delay = 10.0
    half = delay / 2

    for _ in range(200):
        result = equal_jitter(delay, BASE_CONFIG, rng)
        assert half <= result <= delay


def test_equal_jitter_with_fixed_range_is_exact():
    config = RetryConfig(jitter_range=(1.0, 1.0))
    rng = random.Random(0)
    # half=5.0, extra = 5.0 * 1.0 = 5.0 -> toplam 10.0 - delay
    assert equal_jitter(10.0, config, rng) == 10.0


def test_decorrelated_jitter_stays_within_expected_bounds(): #decorrelated_jitter: sonuç, [base_delay, max(base_delay, delay*3)] aralığında rastgele bir değer olmalı.
    rng = random.Random(2)
    delay = 5.0

    for _ in range(200):
        result = decorrelated_jitter(delay, BASE_CONFIG, rng)
        upper_bound = max(BASE_CONFIG.base_delay, delay * 3)
        assert BASE_CONFIG.base_delay <= result <= upper_bound


def test_decorrelated_jitter_never_goes_below_base_delay(): #delay çok küçük olsa bile sonuç her zaman en az base_delay kadar olmalı
    rng = random.Random(3)
    result = decorrelated_jitter(0.0, BASE_CONFIG, rng)
    assert result >= BASE_CONFIG.base_delay



#get_jitter_strategy() -- isimden fonksiyona eşleme

@pytest.mark.parametrize(
    "name, expected_function",
    [
        ("none", no_jitter),
        ("full", full_jitter),
        ("equal", equal_jitter),
        ("decorrelated", decorrelated_jitter),
    ],
)
def test_get_jitter_strategy_returns_correct_function(name, expected_function):
    assert get_jitter_strategy(name) is expected_function


def test_get_jitter_strategy_unknown_name_raises():
    with pytest.raises(ValueError, match="Bilinmeyen jitter stratejisi"):
        get_jitter_strategy("bilinmeyen_strateji")


def test_get_jitter_strategy_error_message_lists_valid_options(): #Hata mesajının, geçerli tüm strateji isimlerini kullanıcıya göstermesi
    with pytest.raises(ValueError, match="none, full, equal, decorrelated"):
        get_jitter_strategy("yanlis")