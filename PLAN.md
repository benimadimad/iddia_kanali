# PLAN

## Amaç

Arkadaş grubunun ortak izleyebileceği, mobil uyumlu bir Avrupa futbolu tahmin
ligi sitesi. Herkes salt okunur takip eder; tahminler yönetici tarafından girilir
ve sonuçlar otomatik güncellenir.

Site yalnızca dört Türk takımının Avrupa maçlarını gösterir: Fenerbahçe ve
Galatasaray (Şampiyonlar Ligi), Beşiktaş (Avrupa Ligi), Trabzonspor (Konferans
Ligi). Şampiyonlar Ligi football-data.org'dan, Avrupa Ligi ve Konferans Ligi
ESPN'den alınır.

## Tamamlananlar

- [x] Flask + SQLite iskeleti ve katmanlı yapı (config / db / repository /
      scoring / service / sync / providers).
- [x] Maçkolik tarzı herkese açık arayüz: tarih sekmeleri, canlı, bitmiş,
      geçmiş, tahminler, puan tablosu.
- [x] Mobil uyumlu tasarım ve canlı maç detay paneli.
- [x] Tahminlerin maç başlayana kadar gizlenmesi.
- [x] Puanlama motoru: tam skor, doğru sonuç, averaj bonusu, joker çarpanı.
- [x] Yönetim paneli: giriş, tahmin düzenleme, oyuncu yönetimi, puanlama,
      manuel senkronizasyon.
- [x] Oturum güvenliği: HttpOnly/SameSite çerez, CSRF koruması, güvenlik
      başlıkları ve CSP.
- [x] football-data.org canlı entegrasyonu (sezonluk Şampiyonlar Ligi çekimi,
      429 tekrar denemesi, canlı dakika bilgisi).
- [x] ESPN entegrasyonu (Avrupa Ligi + Konferans Ligi, sezon/durum/skor
      normalizasyonu).
- [x] Dört takım filtresi ve takip dışı maç/turnuva temizliği.
- [x] Hibrit `tracked` sağlayıcı: CL için football-data.org, EL/UECL için ESPN.
- [x] Public arayüzden "Kurallar" sekmesi ve puanlama tanıtım kartı kaldırıldı.
- [x] Demo sağlayıcısı ve canlıya geçiş komutu (`clear-demo --sync`).
- [x] CLI komutları (`init`, `sync`, `player`, `clear-demo`, `reset-demo`,
      `serve`).
- [x] README, `.env.example`, Docker dosyaları.
- [x] unittest testleri (puanlama, gizlilik, public API, admin/CSRF/maç kilidi,
      dört takım filtresi, ESPN normalizasyonu).

## Canlıya geçiş durumu

- [x] `.env` içine football-data.org token'ı tanımlandı ve `DATA_PROVIDER=tracked`
      yapıldı.
- [x] Demo maçları temizlendi; yalnızca dört takımın maçları kaldı
      (30 maç: CL 16, EL 8, UECL 6; `demo: false`).
- [x] Eski demo liglerinin (EL/TSL) veritabanında kalması engellendi.
- [x] Public ve admin arayüzü canlı veriyle kontrol edildi.
- [ ] Gerçek grupta tahmin girişlerinin başlatılması.
- [ ] `ADMIN_PASSWORD` değerinin güçlü bir şifreyle değiştirilmesi.

## Puanlama (geçici)

| Kural | Puan |
| --- | --- |
| Tam skor | 5 |
| Doğru sonuç | 3 |
| Doğru averaj bonusu (doğru sonuçla birlikte) | +1 |
| Joker çarpanı | ×2 |

Kurallar panelden değiştirilebilir ve `status=final` yapılana kadar geçicidir.
Puan tablosu her istekte mevcut kurallara göre yeniden hesaplanır.

## Sonraki adımlar (opsiyonel)

- [ ] Canlı skor yenileme sıklığını maç saatlerine göre dinamikleştirme.
- [ ] Sezon arşivi / geçmiş sezon puan tablosu.
- [ ] Tahmin girişini oyuncuların kendisinin yapabildiği opsiyonel mod.
- [ ] Bildirimler (maç başladı, tahmin açıldı).
- [ ] Yedekleme betiği ve otomatik veritabanı yedeği.
- [ ] Üretimde izleme/uyarı (senkronizasyon hatası, 429, 403).

## Bilinen kısıtlar

- football-data.org ücretsiz planında Avrupa Ligi (`403`) ve Konferans Ligi
  (`404`) yoktur; bu iki turnuva ESPN'e bağımlıdır.
- Canlı skorlar 180 saniyelik senkron aralığı kadar gecikebilir.
- Uygulama tek worker varsayar; çoklu worker'da `DISABLE_SCHEDULER=1` kullanıp
  zamanlayıcıyı ayrı sürece taşıyın.
