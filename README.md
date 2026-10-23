# Tahmin Ligi

**Vercel üzerinde yayınlamak için:** [VERCEL_KURULUM.md](VERCEL_KURULUM.md) dosyasındaki adımları uygulayın.

Arkadaş grubu için Avrupa futbolu tahmin ligi. Herkesin tarayıcıdan salt okunur
olarak takip ettiği tek sayfalık bir site; tahminler yönetim panelinden girilir,
sonuçlar otomatik güncellenir.

Site yalnızca dört Türk takımının Avrupa maçlarını gösterir:

| Takım | Turnuva |
| --- | --- |
| Fenerbahçe | UEFA Şampiyonlar Ligi |
| Galatasaray | UEFA Şampiyonlar Ligi |
| Beşiktaş | UEFA Avrupa Ligi |
| Trabzonspor | UEFA Konferans Ligi |

Şampiyonlar Ligi maçları
[football-data.org](https://www.football-data.org/), Avrupa Ligi ve Konferans
Ligi maçları ise ESPN'in herkese açık soccer API'sinden alınır. Diğer takımların
ve liglerin maçları veritabanına yazılmaz.

## Özellikler

- Maçkolik benzeri fikstür: tarih sekmeleri, canlı, bitmiş, geçmiş ve tahminler.
- Mobil uyumlu, koyu temalı, tek sayfa arayüz.
- Maç başlayana kadar tahminler gizli; maç başlayınca herkes görebilir.
- Otomatik puan tablosu ve maç bazlı puan dökümü.
- Joker (×2) desteği ve yapılandırılabilir puanlama.
- Yönetim paneli: tahmin girişi, oyuncu yönetimi, puanlama ve senkronizasyon.
- Sadece dört takımın maçları: takip dışı maçlar ve turnuvalar her senkronizasyonda
  temizlenir.
- Hibrit canlı veri: Şampiyonlar Ligi için football-data.org, Avrupa Ligi ve
  Konferans Ligi için ESPN (180 sn senkron).
- Kaynaklardan biri geçici olarak hata verirse mevcut maçlar korunur.
- Demo modu: internet/token olmadan örnek fikstür ve tahminlerle çalışır.

## Hızlı başlangıç (Windows)

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
py -m pip install -r requirements.txt
Copy-Item .env.example .env
# .env içinde ADMIN_PASSWORD, SECRET_KEY ve FOOTBALL_DATA_TOKEN değerlerini düzenleyin
py manage.py init
py app.py
```

- Site: <http://127.0.0.1:5000>
- Yönetim: <http://127.0.0.1:5000/admin>
- Sağlık kontrolü: <http://127.0.0.1:5000/api/health>

`py app.py` geliştirme sunucusudur. Yerel ağda paylaşmak veya üretim benzeri
çalıştırmak için:

```powershell
py manage.py serve --host 0.0.0.0 --port 8000
```

Bu komut Windows'ta `waitress`, diğer platformlarda Flask sunucusunu kullanır.

## Yapılandırma

Tüm ayarlar `.env` dosyasından okunur. `.env` **asla** paylaşılmamalı veya
sürüm kontrolüne eklenmemelidir.

| Değişken | Açıklama | Varsayılan |
| --- | --- | --- |
| `ADMIN_PASSWORD` | Yönetim paneli şifresi | `admin123` (mutlaka değiştirin) |
| `SECRET_KEY` | Oturum çerezlerini imzalayan rastgele anahtar | geliştirme anahtarı |
| `DATA_PROVIDER` | `tracked`, `demo`, `football-data` veya boş (otomatik) | otomatik |
| `FOOTBALL_DATA_TOKEN` | football-data.org API anahtarı | boş |
| `FOOTBALL_DATA_COMPETITIONS` | Takip edilen turnuva kodları | `CL,EL,UECL` |
| `SYNC_INTERVAL_SECONDS` | Senkronizasyon aralığı (sn, en az 60) | `180` |
| `SYNC_PAST_DAYS` / `SYNC_FUTURE_DAYS` | Çekilecek geçmiş/gelecek gün sayısı | `21` / `21` |
| `LEAGUE_NAME` | Sayfa başlığı | `Tahmin Ligi` |
| `APP_TIMEZONE` | Gösterim saat dilimi | `Europe/Istanbul` |
| `SESSION_COOKIE_SECURE` | HTTPS arkasında `true` yapın | `false` |
| `DATABASE_PATH` | SQLite dosyası | `data/league.db` |
| `DISABLE_SCHEDULER` | Arka plan senkronizasyonunu kapatır (`1`) | `0` |
| `HOST` / `PORT` | `py app.py` için bağlanma adresi | `127.0.0.1` / `5000` |

Rastgele anahtar üretmek için:

```powershell
py -c "import secrets; print(secrets.token_hex(32))"
```

### Veri kaynağı notları

- football-data.org ücretsiz planında Şampiyonlar Ligi (`CL`) erişilebilir;
  Avrupa Ligi (`EL`) `403`, Konferans Ligi ise `404` döndürür. Bu yüzden bu iki
  turnuva ESPN'den okunur.
- ESPN tarafında turnuva slug'ları `uefa.champions`, `uefa.europa` ve
  `uefa.europa.conf` şeklindedir. Sezon, `season.year` alanına göre filtrelenir.
- Takım eşleştirmesi Türkçe karakterler normalize edilerek yapılır; örneğin
  `Fenerbahçe`, `Fenerbahce` ve `Beşiktaş`/`Besiktas` aynı takım sayılır.
- football-data.org ücretsiz planında dakikada 10 istek sınırı vardır. Uygulama
  Şampiyonlar Ligi sezonunu tek istekte çeker, 429 yanıtında bekleyip yeniden
  dener.
- Maç verisi 3 dakikada bir tazelenir; canlı skorlar bu nedenle en fazla ~3
  dakika gecikebilir.
- Senkronizasyon sırasında kaynaklardan biri hata verirse (`complete=false`)
  veritabanındaki eski maçlar silinmez; tüm kaynaklar düzelince takip dışı
  kayıtlar temizlenir.

## Yönetim paneli

1. `/admin` adresine gidin ve `ADMIN_PASSWORD` ile giriş yapın.
2. **Tahminler** sekmesinden oyuncu seçip maç skorlarını girin. Joker işaretlemek
   o maçın puanını `joker_multiplier` ile çarpar.
3. Maç başladıktan sonra tahmin değiştirilemez (API `409` döndürür).
4. **Puanlama** sekmesinden kuralları güncelleyin. Varsayılan geçici puanlama:
   - Tam skor: `5`
   - Doğru sonuç: `3`
   - Doğru averaj bonusu: `+1`
   - Joker çarpanı: `×2`
   - Kural seti "geçici" olarak işaretlidir; kesinleşince `status=final` yapın.
5. **Veri** sekmesinden manuel senkronizasyon tetikleyebilirsiniz.

Yönetim API'sindeki tüm değişiklik istekleri `X-CSRF-Token` başlığı gerektirir.
Token, `/admin` sayfasındaki `csrf-token` meta etiketinden veya
`/admin/api/bootstrap` yanıtından alınır.

## Canlı veriye geçiş

Demo verisiyle başladıysanız, gerçek fikstüre geçerken demo maçlarını temizleyin.
Oyuncular korunur; demo maçlarına ait tahminler silinir.

```powershell
# .env içinde DATA_PROVIDER=tracked ve FOOTBALL_DATA_TOKEN tanımlı olmalı
py manage.py clear-demo --sync
py app.py
```

İlk senkronizasyondan sonra veritabanında yalnızca dört takımın maçları kalır;
demo maçları ve takip dışı turnuvalar otomatik silinir. Oyuncular ve onların
geçerli tahminleri korunur.

Doğrulama:

```powershell
Invoke-RestMethod http://127.0.0.1:5000/api/health
```

Yanıtta `"demo": false`, `matches > 0` ve `last_sync` dolu olmalıdır.

## Komutlar

```powershell
py manage.py init                 # Veritabanını hazırla (demo modunda örnek veri)
py manage.py sync                 # Tek seferlik senkronizasyon
py manage.py player "Ali" --color "#5ce1e6"
py manage.py clear-demo --sync    # Demo maçlarını sil + canlı veriyi çek
py manage.py reset-demo --yes     # Demo verisini sıfırla (canlı modda --force)
py manage.py serve --host 0.0.0.0 --port 8000
```

## API

| Yöntem | Yol | Açıklama |
| --- | --- | --- |
| `GET` | `/api/league` | Herkese açık tüm lig verisi |
| `GET` | `/api/health` | Sağlık ve senkronizasyon özeti |
| `GET` | `/healthz` | Basit canlılık kontrolü |
| `GET` | `/admin` | Yönetim paneli (oturum gerekli) |
| `POST` | `/admin/login` | Şifre ile giriş |
| `GET` | `/admin/api/bootstrap` | Panel verisi + CSRF token |
| `POST` | `/admin/api/sync` | Manuel senkronizasyon |
| `PUT` | `/admin/api/predictions` | Tahmin kaydet/sil |
| `POST` | `/admin/api/players` | Oyuncu ekle |
| `PATCH` | `/admin/api/players/<id>` | Oyuncu güncelle |
| `PUT` | `/admin/api/scoring` | Puanlama kurallarını güncelle |

## Testler

```powershell
py -m unittest discover -s tests -v
```

Testler; puanlama kurallarını, tahmin gizliliğini, herkese açık API'yi, yönetim
girişini, CSRF korumasını, maç kilidini, dört takım filtresini ve ESPN maç
normalizasyonunu kapsar. Testler geçici SQLite veritabanı kullanır.

## Docker

```powershell
docker build -t tahmin-ligi .
docker run -d --name tahmin-ligi -p 8000:8000 `
  -e ADMIN_PASSWORD="guclu-bir-sifre" `
  -e SECRET_KEY="rastgele-uzun-anahtar" `
  -e FOOTBALL_DATA_TOKEN="token" `
  -v tahmin-ligi-data:/app/data `
  tahmin-ligi
```

İmaj tek Gunicorn worker'ı ile çalışır; zamanlayıcı bu nedenle tek süreçte kalır.
Yatay ölçekleme yaparsanız `DISABLE_SCHEDULER=1` verip senkronizasyonu ayrı bir
cron/worker sürecine taşıyın.

## Üretim kontrol listesi

- [ ] `ADMIN_PASSWORD` güçlü ve benzersiz.
- [ ] `SECRET_KEY` rastgele ve gizli.
- [ ] HTTPS arkasında `SESSION_COOKIE_SECURE=true`.
- [ ] `.env` ve `data/league.db` yedekleniyor, sürüm kontrolüne girmiyor.
- [ ] Tek worker çalışıyor veya scheduler ayrı süreçte.
- [ ] `/api/health` izleniyor; `sync.error` boş kalıyor.
- [ ] Puanlama kesinleşince panelden `status=final` yapıldı.

## Proje yapısı

```text
app.py                     Flask rotaları, oturum/CSRF, güvenlik başlıkları
manage.py                  CLI komutları
league/
  config.py                .env okuma ve yapılandırma
  db.py                    SQLite şeması
  repository.py            Veri erişimi
  scoring.py               Puanlama kuralları
  service.py               Herkese açık/yönetim verisi ve puan tablosu
  sync.py                  Senkronizasyon + zamanlayıcı
  targets.py               Takip edilen takımlar ve turnuva etiketleri
  providers/               demo, football-data, ESPN ve birleşik tracked sağlayıcı
static/                    CSS/JS
templates/                 Jinja şablonları
tests/                     unittest testleri
data/league.db             Yerel veritabanı (git'e eklenmez)
```
"# iddia_kanali" 
"# iddia_kanali" 
