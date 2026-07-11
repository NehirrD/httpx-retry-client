# httpx-retry-client

`httpx` için jitter'lı exponential backoff, `Retry-After` desteği ve idempotent
retry mantığı sunan güvenilir bir HTTP istemci sarmalayıcısı.

## Kurulum

```bash
pip install -e ".[dev]"
```

Sadece kütüphaneyi kullanmak (test bağımlılıkları olmadan) için:

```bash
pip install -e .
```

## Hızlı Başlangıç

```python
from retry_client import RetryClient, RetryConfig

config = RetryConfig(max_retries=3, base_delay=1.0, max_delay=30.0)

with RetryClient(base_url="https://api.example.com", config=config) as client:
    response = client.get("/users/42")
    print(response.status_code)
```

### Async kullanım

Aynı `RetryClient` örneği hem sync hem async çalışır; async istekler için
`a` ön ekli metotlar kullanılır (`aget`, `apost`, `aput`, `adelete`, `ahead`,
`aoptions`, `arequest`):

```python
import asyncio
from retry_client import RetryClient

async def main() -> None:
    async with RetryClient(base_url="https://api.example.com") as client:
        response = await client.aget("/users/42")
        print(response.status_code)

asyncio.run(main())
```

### Idempotent POST retry

`GET`, `HEAD`, `OPTIONS`, `PUT`, `DELETE` her zaman güvenli kabul edilip retry
edilir. `POST` yalnızca `Idempotency-Key` header'ı verildiğinde retry edilir:

```python
response = client.post(
    "/orders",
    json={"item": "book"},
    headers={"Idempotency-Key": "order-42"},
)
```

`Idempotency-Key` verilmeden yapılan bir POST, sunucu 429/503 dönse bile
**tekrar denenmez** — çünkü sunucu tarafında aynı işlemin iki kez
uygulanmadığından emin olunamaz.

### Circuit breaker (opsiyonel)

Circuit breaker varsayılan olarak kapalıdır. Art arda hatalarda devreyi kısa
süreliğine kesmek isterseniz kendi `CircuitBreaker` nesnenizi verin:

```python
from retry_client import CircuitBreaker, RetryClient

breaker = CircuitBreaker(failure_threshold=5, recovery_timeout=30.0)
client = RetryClient(base_url="https://api.example.com", circuit_breaker=breaker)
```

Devre açıkken yapılan istekler ağa hiç çıkmadan `CircuitBreakerOpenError`
fırlatır.

## Yapılandırma

Tüm retry/backoff/timeout ayarları `RetryConfig` ile kontrol edilir
(`retry_client/config.py`):

| Alan | Açıklama | Varsayılan |
|---|---|---|
| `max_retries` | İlk deneme hariç en fazla retry sayısı | `3` |
| `base_delay` | İlk retry öncesi taban gecikme (sn) | `1.0` |
| `max_delay` | Backoff'un ulaşabileceği üst sınır (sn) | `30.0` |
| `multiplier` | Her denemede gecikmenin çarpanı | `2.0` |
| `jitter_range` | Jitter için çarpan aralığı | `(0.0, 1.0)` |
| `connect_timeout` / `read_timeout` / `write_timeout` / `pool_timeout` | httpx timeout aşamaları (sn) | `5.0` / `10.0` / `10.0` / `5.0` |

Ortam değişkeninden de oluşturulabilir:

```python
config = RetryConfig.from_env()  # RETRY_MAX_RETRIES, RETRY_BASE_DELAY, ...
```

Jitter stratejisi (`none`, `full`, `equal`, `decorrelated`) `jitter_strategy`
parametresiyle değiştirilebilir:

```python
from retry_client.backoff import get_jitter_strategy

client = RetryClient(jitter_strategy=get_jitter_strategy("equal"))
```

## Timeout Yönetimi

Her istek için `RetryConfig` üzerinden ayrı ayrı `connect`/`read`/`write`/`pool`
zaman aşımı tanımlanır ve `httpx.Timeout` nesnesine dönüştürülür
(`retry_client/timeouts.py`). Bu, tek bir isteğin en kötü ihtimalle ne kadar
sürebileceğine üst sınır koyar; ancak **retry döngüsünün tamamı için** ayrı
bir üst zaman sınırı yoktur (bkz. "Bu istemci sarmalayıcı neyi garanti
etmez?"). `timeouts.total_worst_case_timeout(config)` fonksiyonu, tüm retry
döngüsünün en kötü senaryoda ne kadar sürebileceğini tahmini olarak hesaplar.

## Retry Edilen Durumlar

- Ağ hataları: `ConnectError`, `ConnectTimeout`, `ReadTimeout`, `WriteTimeout`, `PoolTimeout`
- HTTP durum kodları: `429`, `502`, `503`, `504`
- `Retry-After` header'ı varsa (saniye veya HTTP-date formatında) o süre beklenir; yoksa exponential backoff + jitter uygulanır.

## URL Maskeleme

Loglarda gerçek istek URL'sinin sorgu parametreleri (query string) ve
fragment'ı **hiçbir zaman görünmez**. `logging_utils.mask_url` yalnızca şema,
host ve path'i loglar — örneğin `https://api.example.com/users?token=secret`
loglarda `https://api.example.com/users` olarak görünür.

## Test Çalıştırma

```bash
python -m pytest
```

Testler gerçek bir ağ bağlantısı kurmaz; `respx` kütüphanesi ile httpx'in
taşıma katmanı taklit edilir. Örnek URL'ler her zaman RFC 6761'de test için
ayrılmış `example.test` alan adını kullanır.

## Bu istemci sarmalayıcı neyi garanti etmez?

- **Kesin teslim süresi garantisi vermez.** Retry döngüsü boyunca toplam
  bekleme süresi `Retry-After` header'ına, backoff ayarlarına ve ağ
  koşullarına bağlı olarak değişir; sabit bir üst sınır yoktur. Kesin bir üst
  sınır isteniyorsa çağıran taraf kendi `asyncio.wait_for` / `signal` tabanlı
  bir zaman aşımı eklemelidir.
- **Sunucunun döndürdüğü her hatada yeniden deneme yapmaz.** Yalnızca
  `429/502/503/504` ve tanımlı ağ hataları retry edilir; `4xx` (400, 401, 403,
  404, 422 vb.) ve `500` gibi durumlar kalıcı hata sayılıp hiç retry edilmez.
- **`POST` (ve diğer idempotent olmayan istekler) `Idempotency-Key` yoksa asla
  retry edilmez** — sunucu tarafında işlemin iki kez uygulanmayacağından emin
  olunamayan hiçbir istek tekrarlanmaz. Bu yüzden bazı geçici hatalarda
  kullanıcı manuel olarak tekrar denemek zorunda kalabilir.
- **Circuit breaker varsayılan olarak kapalıdır** ve verilmediği sürece art
  arda hatalarda herhangi bir koruma sağlanmaz; devreye alınması çağıran
  tarafın sorumluluğundadır.
- **Sunucu tarafında gerçekleşen ama yanıtı istemciye ulaşmadan kaybolan
  isteklerde ("bağlantı koptu ama sunucu işlemi tamamladı" senaryosu)
  sonucun ne olduğunu bilemez** — bu durumda idempotent olmayan bir istek
  tekrar edilirse işlemin iki kez uygulanma riski, tamamen sunucunun
  idempotency garantisine bağlıdır.
