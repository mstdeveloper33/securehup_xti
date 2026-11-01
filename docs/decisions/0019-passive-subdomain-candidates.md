# 0019 — Pasif sertifika kayıtlarından alt alan adı adayları

**Tarih:** 29 Ekim 2026 · **Durum:** 0.19.0'da uygulandı.

> 0.20.0'da çalışma geçmişi ve ilk aday için yerel bildirim eklendi; [0020](0020-passive-discovery-history-and-notices.md) bu ek katmanı tanımlar. Buradaki pasiflik, sahiplik ve aktif kapsam ayrımı değişmedi.

## Sorun

Yalnız kök domainin DNS/TLS temel kaydı kurumun sertifikalarda görünen `vpn`, `api` veya `portal` gibi alt alan adlarını göstermez. Bu adları bulmak için doğrudan hedefleri taramak gereksiz yetki ve güvenlik riski oluşturur. Certificate Transparency kayıtları pasif bir başlangıç kaynağıdır; ancak sertifikada bir adın görülmesi o adın hâlâ çalıştığını veya kullanıcıya ait olduğunu kanıtlamaz.

Keşif sonucu doğrudan aktif kapsam yapılırsa yanlış veya üçüncü tarafa ait bir adrese bağlantı gönderilebilir. Kaynak tekrarları ve yeni sertifikalar da adayları ya da kullanıcı kararlarını çoğaltmamalıdır.

## Karar

`surface discover KÖK`, yalnız önceden kayıtlı kök için crt.sh üzerinde `%.KÖK` sorgusu yapar. Bu kaynak arşivi sorgusudur; bulunan ada DNS, TLS, HTTP veya port isteği göndermez. Yanıttan yalnız kökün kesin altındaki kanonik adlar kabul edilir. Kökün kendisi ve aynı sertifikadaki ilgisiz SAN adları yok sayılır. Joker kök somut alt alan adı sayılmaz; daha derin joker kaydın sabit tabanı aday olabilir.

Her aday `pending`, `owned` veya `rejected` durumundadır. İlk kayıt `pending` başlar. `surface candidate decide`, gerekçeyle durumu değiştirir; ilk keşif ve bütün karar değişiklikleri eklemeli geçmişte kalır. Yeniden keşif kullanıcı kararını sıfırlamaz.

Sertifika kaynağı URL, SHA-256 kimliği, ham ad, CT giriş zamanı ve yerel kayıt zamanıyla saklanır. Adayın ilk/son görülme zamanı CT zamanı varsa ondan, yoksa yerel kayıt zamanından türetilir. Aynı aday + kaynak özeti tekrar yazılmaz; yeni sertifika mevcut adayın kanıt sayısını ve görülme aralığını günceller. Tek bir keşif kümesi tamamen doğrulanmadan yazılmaz ve kayıt transaction'ı atomiktir.

`owned` yalnız insan sınıflandırmasıdır. Adayı `assets` tablosuna eklemez, `surface_scopes` kapsamı oluşturmaz ve `surface check` başlatmaz. Aktif kontrol için kullanıcı ayrıca tam adresi kaydeder ve gerekçeli `surface approve` verir.

## Veri geçişi

Şema 11; `surface_candidates`, `surface_candidate_sources` ve `surface_candidate_events` tablolarını ekler. Şema 10 ve önceki düzenler açık `migrate` komutuyla, yazma kilidi altında önce özgün sürüm yedeği alınarak yükseltilir. Hata bütün DDL'i geri alır ve ana veritabanını eski sürümde bırakır. Eski arama gözlemlerinden geriye dönük aday veya sahiplik kararı üretilmez; yeni tablolar boş başlar.

## Sınırlar

- crt.sh indeks ve hizmet sınırları nedeniyle sonuç bütün alt alan adlarını kapsamaz.
- Sürekli CT akışı, otomatik zamanlama, keşif işi geçmişi ve yeni aday bildirimi henüz yoktur.
- DNS geçmişi, pasif DNS kaynağı, servis/port envanteri ve zafiyet kararı yoktur.
- İlk/son görülme çalışma süresi veya sahiplik dönemi değildir; kaynaktaki gözlem aralığıdır.
- Kaynakta görülme, adın canlı, güvenli, kuruma ait veya kötü amaçlı olduğunu kanıtlamaz.
