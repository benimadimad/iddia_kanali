# Vercel + Firebase (Firestore) Yayın Planı

Bu plan, mevcut Flask + SQLite uygulamasını **Vercel üzerinde serverless** ve
**Firebase Firestore** veritabanıyla çalıştırmak için gereken mimariyi ve iş
paketlerini tanımlar.

---

## 1. Mimari kararlar

| Konu | Mevcut | Yeni |
| --- | --- | --- |
| Uygulama | Flask, tek süreç | Flask, Vercel Python function (`api/index.py`) |
| Veritabanı | SQLite (`data/league.db`) | Firestore (Native mode) |
| Arka plan senkronizasyonu | `SyncScheduler` thread | Vercel Cron / harici cron → `/api/cron/sync` |
| Statik dosyalar | Flask `static/` | `public/` (Vercel CDN) |
| Oturum | Flask imzalı çerez | Aynı (serverless uyumlu) |
| Bölge | — | Vercel `fra1` + Firestore `europe-west3` (Frankfurt) |

**Neden Flask kalıyor:** Site zaten Flask + Jinja + vanilya JS. Next.js'e geçmek
tüm arayüzü yeniden yazmak demek; Vercel Python runtime ile mevcut kod korunur.

**Kritik sınırlar:**
- Vercel'de kalıcı disk yok; SQLite kullanılamaz.
- Function'lar arası paylaşılan bellek yok; thread/scheduler güvenilir değil.
- Vercel Hobby cron günde 1 kez çalışır; canlı skor için harici cron veya Pro gerekir.
- Firestore ücretsiz kota: günde ~50.000 okuma / 20.000 yazma (güncel dokümana bakın).

---

## 2. Firestore veri modeli

Mevcut alan adları korunur; `service.py` neredeyse hiç değişmez.

```
players/{id}                 -> { id, name, slug, color, active, bonus_points, created_at }
competitions/{code}          -> { code, name, country, emblem, sort_order }
matches/{id}                 -> { id, provider, external_id, competition_code, season, matchday,
                                  stage, kickoff_utc, status, minute,
                                  home: { name, short, tla, crest },
                                  away: { name, short, tla, crest },
                                  score: { home, away }, last_updated, created_at, updated_at }
predictions/{playerId}_{matchId} -> { player_id, match_id, outcome, joker, created_at, updated_at }
settings/{key}               -> { key, value }            // scoring
sync_state/current           -> { provider, last_attempt_at, last_success_at, last_error,
                                  matches_seen, changed }
meta/counters                -> { player: n, match: n }   // yeni kayıtlar için transaction
```

- `predictions` doküman kimliği deterministik olduğu için upsert doğal olarak tekildir.
- Maçlar numeric id'yi string doküman kimliği olarak korur; mevcut linkler/tahminler bozulmaz.
- Yeni maçlar için `meta/counters` transaction ile id üretilir; `(provider, external_id)`
  eşleşmesi önce sorgulanır.
- Firestore'da cascade yok: maç silinince ilgili `predictions` kayıtları da toplu silinir.
- Batch limiti 500; silme işlemleri 400'lük parçalara bölünür.
- Gerekli indeksler: `predictions.match_id`, `matches.kickoff_utc`,
  `matches(provider, external_id)`.

**Okuma stratejisi:** Mevcut `public_payload()` tüm maçları (30) ve tahminleri (180)
okuyup bellekte hesaplıyor. Bu ölçekte Firestore için sorunsuz; yine de:
- `/api/league` yanıtına `Cache-Control: public, s-maxage=30, stale-while-revalidate=120`
  eklenir (mevcut `no-store` bu route için kaldırılır).
- İleride gerekirse `snapshots/league` dokümanında hazır JSON tutulup tek okumayla
  servis edilir (1 MB doküman limiti kontrol edilmeli).

---

## 3. Kod değişiklikleri

### 3.1 Veri katmanı soyutlaması

```
league/store/__init__.py      -> get_store(config)  (backend seçimi)
league/store/sqlite_store.py  -> mevcut repository.py'nin sarmalayıcısı
league/store/firestore_store.py -> yeni Firestore uygulaması
```

Ortak arayüz (mevcut fonksiyonlarla birebir):

```
init_db, ensure_ready
list_players, get_player, create_player, update_player
list_competitions, upsert_competition, delete_competitions_except
list_matches, get_match, upsert_matches, delete_demo_matches, delete_matches_not_in
list_predictions, upsert_prediction, delete_prediction
get_setting, set_setting, get_scoring, set_scoring
get_sync_state, update_sync_state
```

`league/service.py`, `league/sync.py`, `app.py`, `manage.py` ve testler bu arayüzü
kullanacak şekilde güncellenir. `Config`'e eklenecek:

```
DATA_BACKEND=sqlite|firestore
FIREBASE_PROJECT_ID=...
FIREBASE_SERVICE_ACCOUNT=<base64 veya tek satır JSON>
```

Firestore istemcisi her function instance'ında **bir kez** (lazy singleton) kurulur:

```python
from google.cloud import firestore
from google.oauth2 import service_account
```

`firebase-admin` yerine yalnızca `google-cloud-firestore` kullanılması paket
boyutunu ve cold start süresini azaltır.

### 3.2 Uygulama girişi

`app.py` sonundaki `app = create_app()` aynı kalır. Vercel için:

```python
# api/index.py
from app import app  # WSGI callable
```

`bootstrap()` her cold start'ta çalışacağı için `ensure_ready()` idempotent ve
hafif olmalı (dolu koleksiyonda yazma yapmamalı).

### 3.3 Scheduler yerine cron

- `DISABLE_SCHEDULER=1` (Vercel'de zorunlu).
- Yeni endpoint: `GET /api/cron/sync`
  - `Authorization: Bearer <CRON_SECRET>` doğrulaması
  - `sync_service.sync()` çağırır, JSON sonuç döner
- `vercel.json` cron tanımı (Pro) veya harici cron (Hobby):

```
crons: [{ "path": "/api/cron/sync", "schedule": "*/10 * * * *" }]
```

Hobby planda günde 1 cron sınırı olduğu için canlı skorlar için
**cron-job.org / GitHub Actions** ile 10 dakikada bir çağrı önerilir.
football-data.org ücretsiz planı dakikada 10 istek; 10 dk aralık güvenli.

### 3.4 Statik dosyalar ve şablonlar

- `static/` → `public/static/` taşınır; Flask'ta
  `Flask(__name__, static_folder="public/static", static_url_path="/static")`.
- `templates/` function paketine dahil edilir (`includeFiles`).
- Vercel `public/` içeriğini CDN'den servis eder; cache-busting `?v=` zaten var.

---

## 4. Vercel yapılandırması

```json
{
  "builds": [
    { "src": "api/index.py", "use": "@vercel/python", "config": { "runtime": "python3.12" } }
  ],
  "routes": [{ "src": "/(.*)", "dest": "/api/index.py" }],
  "functions": {
    "api/index.py": {
      "maxDuration": 60,
      "memory": 1024,
      "includeFiles": ["templates/**", "league/**"]
    }
  },
  "regions": ["fra1"],
  "crons": [{ "path": "/api/cron/sync", "schedule": "0 * * * *" }]
}
```

> `public/` altındaki dosyalar route'tan önce statik olarak servis edilir.
> `/admin` ve `/api/*` function'a düşer.

### Ortam değişkenleri (Vercel → Production/Preview)

```
LEAGUE_NAME=Tahmin Ligi
DATA_BACKEND=firestore
FIREBASE_PROJECT_ID=<proje-id>
FIREBASE_SERVICE_ACCOUNT=<service-account-json-base64>
DATA_PROVIDER=tracked
FOOTBALL_DATA_TOKEN=<token>
FOOTBALL_DATA_COMPETITIONS=CL,EL,UECL
APP_TIMEZONE=Europe/Istanbul
ADMIN_PASSWORD=<güçlü-şifre>
SECRET_KEY=<rastgele-64-hex>
SESSION_COOKIE_SECURE=true
DISABLE_SCHEDULER=1
SHOW_DEMO_BANNER=false
CRON_SECRET=<rastgele>
```

`FIREBASE_SERVICE_ACCOUNT` base64 olarak saklanır (newline sorununu önler).
Service account yalnızca Firestore erişimi olan ayrı bir kullanıcı olsun.

### Firebase tarafı

1. Firebase projesi → Firestore Native mode, konum **europe-west3**.
2. Service account oluştur, JSON anahtarını indir (repoya koyma).
3. Güvenlik kuralları: istemciden erişim yok.

```
rules_version = '2';
service cloud.firestore {
  match /databases/{database}/documents {
    match /{document=**} { allow read, write: if false; }
  }
}
```

4. Bütçe uyarısı + günlük Firestore export (opsiyonel, Blaze gerekir).

---

## 5. Veri taşıma (SQLite → Firestore)

`tools/migrate_to_firestore.py`:

1. `data/league.db`'yi salt okunur açar.
2. `players`, `competitions`, `matches`, `predictions`, `settings`, `sync_state`
   tablolarını okur.
3. Firestore'a batch (400'lük) upsert yazar; `meta/counters` değerlerini
   `max(id)` ile başlatır.
4. Kuru çalışma modu (`--dry-run`) ve doğrulama raporu (`--verify`) içerir:
   - oyuncu/maç/tahmin sayıları birebir eşleşmeli (6/30/180)
   - puan tablosu SQLite ve Firestore'da aynı olmalı
   - Ogün'ün 30 tahmini ve Batıkan Abi +1 bonusu kontrol edilir
5. Idempotent: tekrar çalıştırılabilir; mevcut dokümanları günceller.

Önce **ayrı bir staging Firebase projesinde** çalıştırılıp doğrulanmalı, sonra
prod'a.

---

## 6. Güvenlik

- Firestore kuralları istemci erişimini tamamen kapatır; tüm erişim service account ile.
- `.env`, service account JSON ve `data/league.db` repoya girmez (`.gitignore` kontrol).
- Admin şifresi güçlü; `SECRET_KEY` deploy'lar arasında sabit.
- Cron endpoint'i `CRON_SECRET` olmadan 401 döner.
- Admin girişine basit hız sınırı (Firestore sayaç veya Vercel Firewall) eklenebilir.
- `SESSION_COOKIE_SECURE=true`, HTTPS zorunlu.
- Hata mesajlarında token/credential sızdırılmaz.

---

## 7. Test ve doğrulama

- Mevcut 36 SQLite testi aynen korunur.
- Firestore için **Firebase Emulator** ile repository testleri:
  `FIRESTORE_EMULATOR_HOST=127.0.0.1:8080`.
- Preview deployment kontrol listesi:
  - [ ] `/` ana sayfa + mobil görünüm
  - [ ] `/api/league` durum 200, tahminler açık, sıralama doğru
  - [ ] `/api/health` `last_sync` dolu
  - [ ] `/api/cron/sync` doğru secret ile 200, yanlış secret ile 401
  - [ ] `/admin` giriş, tahmin kaydetme (Firestore'a yazıyor)
  - [ ] Puan tablosu: Gökhan 7, Ogün 6, Anıl 5, Batıkan 5, Enes 4, Batu 3
  - [ ] Statik dosyalar CDN'den 200, konsol hatasız
  - [ ] Yeni deploy sonrası veriler korunuyor (kalıcılık testi)

---

## 8. İş paketleri (önerilen sıra)

| # | İş | Tahmini süre |
| --- | --- | --- |
| 1 | Firebase projesi, Firestore, service account, güvenlik kuralları | 30 dk |
| 2 | Store soyutlaması + SQLite store'un taşınması, testlerin yeşil kalması | 2-3 saat |
| 3 | Firestore store implementasyonu + emulator testleri | 3-4 saat |
| 4 | Migration script + staging doğrulaması | 1-2 saat |
| 5 | `api/index.py`, `vercel.json`, statik dosya taşıma, env ayarları | 1-2 saat |
| 6 | Cron endpoint + harici cron/Vercel cron | 1 saat |
| 7 | Vercel preview deploy, uçtan uca test, prod deploy | 1-2 saat |
| 8 | Domain, izleme, yedekleme | 1 saat |

Toplam: **1-2 gün** (tek kişi, testler dahil).

---

## 9. Riskler ve geri dönüş

- **Vercel Python runtime** nadir kullanılan bir yol; function boyutu/cold start
  sorun çıkarırsa aynı kod **Google Cloud Run**'a neredeyse değişmeden taşınır
  (Dockerfile zaten var). Firestore aynı kalır.
- **Hobby cron sınırı**: canlı skor gecikirse harici cron devreye alınır.
- **Firestore maliyeti**: trafik artarsa snapshot + edge cache ile okumalar düşürülür.
- **Geri dönüş**: SQLite store ve `data/league.db` silinmez; `DATA_BACKEND=sqlite`
  ile eski düzene anında dönülebilir.

---

## 10. Bu planın dışında bırakılanlar

- Next.js'e tam yeniden yazım (gerekmiyor).
- Firebase Authentication (admin girişi mevcut şifre + imzalı çerezle kalıyor).
- Realtime Database (Firestore bu kullanım için daha uygun).
- Çoklu instance/yatay ölçekleme (tek instance + cron yeterli).
