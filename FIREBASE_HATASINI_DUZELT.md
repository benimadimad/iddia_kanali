# Vercel `File name too long` Firebase hatası — güvenli düzeltme

`/api/league` endpoint'inin verdiği `File name too long` hatası, `FIREBASE_SERVICE_ACCOUNT` değişkenindeki **Base64 olarak kodlanmış Firebase servis hesabı JSON'unun** yanlışlıkla dosya yolu olarak okunmasından kaynaklanır. Bu sürümde `league/firestore_repository.py` kodu uzun Base64 bilgileri doğrudan çözer; `app.py` ise sunucu hatalarında hassas verileri API yanıtında göstermez.

## ACİL: Eski Firebase anahtarını iptal edin

Hata mesajında Firebase servis hesabı özel anahtarı Base64 içinde internette paylaşılmış oldu. Base64 şifreleme değil kodlamadır. **Yayımlanan eski anahtar tehlikeye girmiş kabul edilmelidir.**

1. Google Cloud Console → IAM ve Yönetici → Hizmet Hesapları bölümüne gidin.
2. Firebase için kullanılan hizmet hesabını bulun; **Anahtarlar** sekmesinden eski anahtarı **silin**. Başka hizmetler aynı anahtarı kullanıyorsa önce onların bağlantısını da yeni anahtara aktarın.
3. **Yeni anahtar oluştur → JSON** ile yeni servis hesabı JSON dosyasını yalnızca kendi bilgisayarınıza indirin.
4. Base64 değerini kendi bilgisayarınızda üretin (Windows PowerShell):

   ```powershell
   [Convert]::ToBase64String([System.IO.File]::ReadAllBytes('C:\gizli\yeni-firebase-anahtari.json'))
   ```

5. Vercel Dashboard → mevcut proje → **Settings → Environment Variables** → `FIREBASE_SERVICE_ACCOUNT` alanını yeni Base64 metniyle güncelleyin. Değeri **Production** ortamına tanımlayın. `DATA_BACKEND=firestore` ve `FIREBASE_PROJECT_ID` değerlerini kontrol edin.
6. Bu ZIP'ten **tüm proje kodunu** eski GitHub projenize güncelleyin. Sadece Vercel ortam değişkenini değiştirmek, eski kodun hatasını düzeltmez.
7. Kod değişikliğini GitHub'a gönderin ve Vercel'de yeni **Production Deployment** başlatın. (Ortam değişkeni güncellemesinin yayına alınması için de yeni deploy gerekir.)
8. `https://iddiakanalisitesi1.vercel.app/api/league` adresini test edin. Hata varsa Vercel → **Logs** bölümünden hata türünü kontrol edin, ama özel anahtar, tam `FIREBASE_SERVICE_ACCOUNT` metni veya loglarda görünen anahtar değerlerini kimseyle paylaşmayın.

**Not:** Firestore'a önceden veri aktarılmadıysa düzeltme sonrasında bağlantı açılmasına rağmen maçlar boş görünebilir; `VERCEL_KURULUM.md` içinde SQLite → Firestore taşıma işlemi yer alır.

### Sorun sürüyorsa

- `403 PERMISSION_DENIED`: Servis hesabının Firestore erişim yetkisini ve ilgili Google Cloud projesini kontrol edin.
- `404` / `NOT_FOUND`: Firestore veritabanının oluşturulduğunu ve `FIREBASE_PROJECT_ID` değerinin doğru olduğunu kontrol edin.
- `401` / `invalid_grant`: Silinen eski anahtar yerine yenisiyle deploy yapıldığını kontrol edin.
- `200` ve boş listeler: Veritabanı henüz boş olabilir; Firestore'a kayıt aktarın.

Eski özel anahtarı GitHub geçmişinden veya herkese açık loglardan da kaldırmaya çalışın; anahtarı silmiş olmak onu geçersiz kılar. Yeni anahtarı hiçbir sohbet, ekran görüntüsü veya kod deposunda paylaşmayın.
