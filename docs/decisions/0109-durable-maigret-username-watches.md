# 0109 — Kalıcı Maigret kullanıcı adı izlemeleri

**Tarih:** 31 Ekim 2026  
**Durum:** Kabul edildi  
**Sürüm:** 0.111.0

## Bağlam

0108 numaralı karar seçili platformlarda güvenli ve yazmasız Maigret
önizlemesini ekledi. Kullanıcı her sonucu elle karşılaştırmak zorunda kalıyordu;
kaynak kesintisi ile profilin raporlanmaması da kalıcı geçmiş olmadan güvenle
ayrılamıyordu.

## Karar

Kullanıcı, yerel bir ad, tek açık kullanıcı adı ve en fazla on izinli platformla
kalıcı izleme tanımlar. Tanımın ekleme, güncelleme, yeniden etkinleştirme ve geri
çekme olayları silinmez. Tanım değiştiğinde sonraki başarılı çalışma yeni sessiz
başlangıç olur.

İlk başarılı çalışma `baseline_found` ve `baseline_unreported` durumlarını
saklar fakat dikkat adayı üretmez. Sonraki başarılı çalışma yalnız aynı tanımın
son başarılı çalışmasıyla karşılaştırılır. `newly_found`, `changed`,
`unchanged_found`, `no_longer_reported` ve `unchanged_unreported` ayrımları
platform başına kaydedilir.

Maigret kaynak hatası ayrı `failed` çalışmadır. Sonuç öğesi taşımaz ve son
başarılı çalışma zincirini değiştirmez. Böylece hata “hesap yok” veya “hesap
kaldırıldı” şeklinde yorumlanmaz. `no_longer_reported` de yalnız kaynağın bu
turda profil raporlamadığını anlatır.

Kalıcı sonuç yalnız platform, `found_unverified`/`unreported` durumu, izinli
HTTPS profil adresi, fark eylemi ve SHA-256 bütünlük özeti taşır. Ham HTTP,
Maigret ham sonucu ve çıkarılmış profil alanları saklanmaz. Liste, ayrıntı ve
çalışma gösterimi ağsızdır; canlı ağ yalnız açık `watch-run` komutunda kullanılır.

Şema 47 dört tablo ekler: izleme tanımı, yaşam döngüsü olayı, çalışma ve çalışma
öğesi. Şema 46 geçişi önce doğrulanmış yedek alır, tabloları boş oluşturur ve
hata halinde geri alınır. Önceki yazmasız önizlemelerden geçmiş türetilmez.

## Sonuçlar

- Kullanıcı aynı kullanıcı adını tekrar tekrar elle karşılaştırmak zorunda kalmaz.
- Kaynak kesintisi ile platformun profil raporlamaması birbirine karışmaz.
- Bulunan profil otomatik sahiplik veya taklit alarmına dönüşmez.
- Ortak gelen kutusu ve analist kararı eklenmeden önce güvenilir fark geçmişi hazırdır.
- Otomatik zamanlayıcı, daemon, e-posta, web paneli ve yapay zekâ eklenmez.

## Canlı kabul

31 Ekim 2026'da geçici şema 47 veritabanında yalnız GitHub seçilerek herkese
açık `octocat` hesabı iki kez çalıştırıldı. İlk çalışma sessiz başlangıç, ikinci
çalışma `unchanged_found` oldu. Kullanıcının ana veritabanı değiştirilmedi.
