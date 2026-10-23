## Hızlı düzeltme (Veriler yüklenemedi)

Bu sürüm Vercel üzerinde SQLite seçiliyse (`DATA_BACKEND=sqlite` veya tanımlı değilse), paketle gelen `data/league.db` dosyasını ilk istekte `/tmp/tahmin-ligi/league.db` konumuna kopyalar. Böylece ilk kurulumda maçlar ve puanlar görüntülenebilir. **Bu geçici çözümdür:** Vercel fonksiyonu yeniden oluşturulduğunda `/tmp` değişiklikleri kaybolur; kullanıcı tahminleri kalıcı değildir. Üretimde `DATA_BACKEND=firestore` + doğru Firebase anahtarları kullanılmalıdır. Firestore seçildiğinde SQLite yedeği otomatik devreye girmez.

Tanılama: `https://iddiakanalisitesi1.vercel.app/api/test` basit Flask erişimini test eder. `/api/league` 500 dönüyorsa Vercel → Logs üzerinden Python traceback'ini kontrol edin; 404 dönüyorsa proje kökü / Flask deploy ayarlarını kontrol edin. Güncellemeden sonra Redeploy gerekir. 

# Tahmin Ligi — Vercel'e yayınlama

Bu paket Flask uygulamasının Vercel üzerinde çalışabilmesi için hazırlanmıştır. `app.py` otomatik tespit edilir; `vercel.json` Python fonksiyonunu Frankfurt bölgesinde çalıştırır ve Hobby plana uygun günlük veri senkronizasyonu tanımlar.

**Önemli:** Vercel'e yayınlama işlemi, Vercel hesabında giriş ve Firebase'e erişim gerektirir. Pakette **hiçbir parola, `.env` dosyası, Firebase servis hesabı veya diğer özel anahtarlar bulunmaz**. Bunları GitHub'a yüklemeyin. Vercel'deki ortam değişkenlerini hesabınızın ayarlarından tanımlayın.

## 1. Firebase Firestore'u hazırla

1. [Firebase Console](https://console.firebase.google.com/) üzerinden proje oluşturun/var olan projeyi açın, Firestore Database'i *Native Mode* ile etkinleştirin (Avrupa'da bölge seçebilirsiniz).
2. Firebase projesine bağlı bir Google Cloud hizmet hesabının Firestore erişimi olduğundan emin olun. Özel servis hesabı JSON'unu **yalnızca kendi bilgisayarınızda** saklayın.
3. Elinizdeki servis hesabı JSON'unu Vercel'e tek satır `base64` olarak aktarabilirsiniz. Windows PowerShell'de (JSON dosyası kendi bilgisayarınızdayken):

```powershell
[Convert]::ToBase64String([IO.File]::ReadAllBytes('secrets/firebase-service-account.json'))
```

Çıktıyı **sadece Vercel'in** `FIREBASE_SERVICE_ACCOUNT` ortam değişkenine yapıştırın. Gizli anahtarları GitHub'a veya herkese açık depolara yüklemeyin.

## 2. Vercel ortam değişkenleri

[Vercel Dashboard](https://vercel.com/dashboard) → Proje → **Settings → Environment Variables** ekranında şu değişkenleri tanımlayın (Production için):

| Değişken | Değer |
|---|---|
| `DATA_BACKEND` | `firestore` |
| `FIREBASE_PROJECT_ID` | Firebase projenizin gerçek proje kimliği |
| `FIREBASE_SERVICE_ACCOUNT` | Servis hesabı JSON'unun base64 çıktısı (gizli) |
| `ADMIN_PASSWORD` | Tahmin yönetim paneli için **güçlü yeni şifre** (gizli) |
| `SECRET_KEY` | Uzun rastgele bir oturum anahtarı (gizli) |
| `CRON_SECRET` | Uzun rastgele cron erişim anahtarı (gizli) |
| `DATA_PROVIDER` | `tracked` (gerçek maçlar); `demo` yalnızca örnek görünüm |
| `FOOTBALL_DATA_TOKEN` | football-data.org API anahtarı (gizli) |
| `DISABLE_SCHEDULER` | `1` |
| `SESSION_COOKIE_SECURE` | `true` |
| `APP_TIMEZONE` | `Europe/Istanbul` |

PowerShell'de iki ayrı yeni rastgele gizli değer üretmek için şu komutu iki kez çalıştırabilirsiniz:

```powershell
py -c "import secrets; print(secrets.token_urlsafe(48))"
```

Ortam değişkenleri eklendikten sonra uygulamayı **redeploy** edin. Proje API hatası verirse ilk olarak Vercel **Runtime Logs** ve Firebase erişim yetkilerini kontrol edin.

## 3. Vercel'e yayınla

### Yöntem A — GitHub'dan (önerilir)

1. Bu klasörü bilgisayarınıza indirin ve açın.
2. Projeyi GitHub'da **private** bir repoya yükleyin. `.env`, `secrets/` ve `data/*.db` dosyalarının repoda olmadığını kontrol edin; `.gitignore` hazırdır.
3. [vercel.com/new](https://vercel.com/new) adresine gidip GitHub reposunu seçin.
4. Framework'ün **Flask / Python** olarak algılandığını kontrol edin. Root Directory proje kökü olmalıdır. Build Command ve Output Directory'yi boş bırakın.
5. Yukarıdaki ortam değişkenlerini ekleyin, ardından **Deploy** deyin. Size `<proje-adı>.vercel.app` biçiminde gerçek bir URL oluşturulur.

### Yöntem B — Vercel CLI

```powershell
npm install -g vercel
vercel login
cd "proje-klasorunuz"
vercel
```

Önce Vercel Dashboard'dan ortam değişkenlerinizi ekleyin, sonra üretime almak için:

```powershell
vercel --prod
```

CLI, `.vercelignore` dosyası sayesinde veritabanı, yerel `.env` ve `secrets` klasörünü Vercel'e göndermez.

## 4. Mevcut oyuncuları, maçları ve tahminleri kaybetme

Arşivdeki eski `data/league.db` yerel SQLite veritabanıdır. Bu dosya Vercel üzerinde kalıcı veri kaynağı olarak kullanılamaz. Mevcut puanlar için **bir kez Firestore'a taşınmalıdır**.

1. Orijinal RAR'daki `data/league.db` dosyasını indirdiğiniz bu projenin `data/league.db` yoluna koyun (pakette mevcut olabilir).
2. Firebase servis hesabı JSON'unu bilgisayarınızda `secrets/firebase-service-account.json` yoluna koyun, ancak **Git'e eklemeyin**.
3. Yerel `.env` dosyasında `DATA_BACKEND=firestore` ve `FIREBASE_PROJECT_ID` tanımlayın. Alternatif olarak PowerShell'de `$env:DATA_BACKEND='firestore'` kullanın.
4. Proje klasöründe çalıştırın:

```powershell
py -m pip install -r requirements.txt
py tools/migrate_to_firestore.py --dry-run
py tools/migrate_to_firestore.py
py tools/migrate_to_firestore.py --verify
```

Veriler Firestore'a aktarılmadan önce sayfa boş görünebilir. Transferi **aynı Firestore projesi** üzerinde yaptığınızdan emin olun.

## 5. Kontrol adresleri

- `https://<proje-adı>.vercel.app/` — ana sayfa
- `https://<proje-adı>.vercel.app/api/health` — sağlık kontrolü (Firestore da çalışıyorsa HTTP 200)
- `https://<proje-adı>.vercel.app/admin` — yönetim paneli
- `https://<proje-adı>.vercel.app/api/cron/sync` — sadece `Authorization: Bearer <CRON_SECRET>` başlığıyla çalışır

`vercel.json` her gün **03:00 UTC / 06:00 Türkiye saati** senkronizasyonu planlar. Vercel'in ücretsiz Hobby planında cron bir günde birden fazla çalıştırılamaz; daha sık maç güncellemesi isteniyorsa Pro planda cron ifadesi değiştirilebilir veya güvenli bir harici cron kullanılabilir. Yönetim panelinde de manuel senkronizasyon vardır.

## Sorun giderme

- `500` ve Firebase hatası: Firestore veri tabanının açıldığını, servis hesabı projesini, yetkilerini ve `FIREBASE_SERVICE_ACCOUNT` base64 metnini kontrol edin.
- `401` cron endpoint'i: `CRON_SECRET` eksik/yanlış.
- Admin girişinde tekrar giriş istenmesi: `SECRET_KEY` değerinin her deploy'da aynı kaldığını ve `SESSION_COOKIE_SECURE=true` olduğunu doğrulayın.
- Sayfa açılıyor ancak puanlar yok: önce eski SQLite veritabanının Firestore'a taşındığını ve aynı projeye bağlandığını kontrol edin.
- `api/health` 200, `matches=0`: ilk canlı senkronizasyonu yönetim panelinden başlatın.

**Güvenlik notu:** Eski RAR dosyasında özel anahtarlar bulunduğundan onu kamuya açık biçimde paylaşmayın. Daha önce herhangi bir yerde açığa çıktıysa Firebase servis hesabının anahtarını, yönetici parolasını ve diğer API anahtarlarını yenileyin.
