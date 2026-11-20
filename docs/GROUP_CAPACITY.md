# Biriken grup geçmişiyle çalışma

0.178.0 · çekirdek88 · grup olay/durum biçimi2; eski biçim1 okunur.
Grup türetme kuralı1, dış JSONv1, kaynak işi7 ve kuyruk3 korunur.

Güncel grubu açmak artık bütün kontrol geçmişini yeniden işlemez. Aynı
kanıt tekrar görülürse yeni kontrolün zamanı ve isteği kaydedilir; kanıt
gövdesi tekrar kopyalanmaz. Gerçek değişiklikte yeni kanıt ve önceki/sonraki
bildirim saklanır. İnsan kararı kendiliğinden değişmez.

## Güncel sonuç ve geçmiş

```sh
./xti groups list --limit 20
./xti groups current GRUP
./xti groups history GRUP --limit 20
./xti groups changes GRUP --limit 20
./xti groups notifications --limit 20
./xti groups notification-show BILDIRIM
```

`GRUP` kayıtlı 64 haneli kimliktir. Sayfa yanıtındaki `next_offset` ve
`snapshot_id`, sonraki istekte `--offset` ve `--expected-snapshot` olarak
verilir. Arada kayıt veya bildirim durumu değişirse eski sayfa belirteci
reddedilir; ilk sayfadan başlanır. Bu, firmalar arası bir ortak önbellek değildir.

`current` son kanıtı, kararı, sürümü ve kontrol durumunu gösterir.
`history` bütün kontrolleri/kararları sırasıyla sayfalar. Olay biçimi2'de
`snapshot.same_as_previous` önceki kanıtın kanonik JSON SHA-256 başvurusudur;
silinmiş veya bilinmeyen sonuç anlamına gelmez. `changes` yalnız gerçek
değişiklikleri donmuş önceki/sonraki kanıtıyla sayfalar.

Eski `groups show` tam geçmiş davranışını korur. Bir grubun geçmişi 1000
olay veya 4 MiB'ı aşarsa `history_requires_pagination` döndürür; sonuç
eksiltilerek tam gösterilmez. Bu, saklama sınırı değildir. Büyük geçmişte
`current/history/changes` kullanılır.

Terminal yazmaları ve yönetilen kontrol işleri güncel sonuç döndürür.
Eski tam yanıt gerekirse `--response-mode full` seçilebilir. JSON yazma
isteğinde `response_mode` belirtilmezse eski `full` davranışı korunur;
uzun süreli kullanımda `"response_mode":"current"` gönderilmelidir.
Bu alan işlemin tekrar kimliğini değiştirmez. Eski tekrar anahtarı ilk
işlem sonucunu verir; yeni kontrol veya yeni bildirim oluşturmaz.

## Doğrulama ve yeniden kurma

```sh
./xti groups audit
./xti groups rebuild
```

Normal okuma seçilen kanıtı ve son durum bağını doğrular. `audit` bütün
grup olaylarını, karar geçişlerini, türetilen durumları ve bildirimleri
akış halinde kontrol eder. Hacme göre sürebilen açık bakım işlemidir;
her listelemede çalışmaz ve veri değiştirmez.

Olağan işlem dışında veritabanına SQL ile müdahale edilirse güncel durum
geçersiz sayılır ve normal okuma durur. `rebuild` önce ayrı yedek alır,
özgün günlükten güncel durum tablolarını yeniden kurar. Eski kanıtı,
kararı, bildirim kimliğini veya okunma durumunu değiştirmez. Özgün günlük
de bozuksa onarım başarı sayılmaz; transaction geri alınır ve yedek korunur.

Bu komutlar firma JSON yüzeyinde de vardır. `groups.rebuild` yazmadır;
güncel `expected_workspace_id` ve mevcut firma yazıcı kilidi gerekir.
Oturum/rol yetkisini bağlayan platform sağlar.

## Saklama ve çalışma sınırları

Eski 1000 olay/grup, 10000 olay/alan ve toplam 64 MiB günlük sınırları
yeni olayları durdurmaz. Tek olay 2 MiB, grup kanıtı 192 KiB, sayfa 20
kayıtla sınırlıdır. Sürüm ve offset desteklenen 32-bit pozitif tamsayı
aralığındadır. Araştırmanın düğüm/kaynak/kanıt kapsam sınırları değişmez.

Her kontrolün zamanı ve tekrar anahtarı hâlâ saklanır; disk büyür.
Kontrol aralığı ve disk izleme buna göre seçilir. Otomatik geçmiş silme
yoktur. `journals` eski gövdeleri kayıpsız sıkıştırabilir; işlem yedekleri
ayrıca alan kullanır. SQL sayımı, derin offset, arşiv planı ve tam denetim
hacimden etkilenir. Bu sürüm sınırsız saklama veya bütün motor için sabit
gecikme taahhüdü vermez.

## Yükseltme

```sh
git pull --ff-only
./xti migrate
./xti doctor
./xti groups audit
```

87→88 geçişi eski tabloların satır/rowid/JSON/hash değerlerini korur,
koruma tetikleyicileri ve türetilen tablolar ekler. Önce eski şemanın
yedeği alınır. Eski motor yeni şemayı reddeder; geri dönüş gerektiğinde
geçiş öncesi yedek eski kodla yeni/boş veri alanına açılır. Geçişten sonra
oluşan kayıtlar eski yedekte bulunmaz.

[Kabul ölçümleri ve sınırlar](roadmap/GROUP_CAPACITY_DELIVERY.md).
