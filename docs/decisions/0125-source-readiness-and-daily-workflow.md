# 0125 — Birleşik kaynak durumu ve günlük kullanım

Durum: Kabul edildi

Sürüm: 0.127.0 · Tarih: 13 Kasım 2026

## Karar

`sources status` kayıtlı kaynakları kısa terminal tablosunda gösterir;
`--details` kapsam ve kanıtı açar. Mevcut `sources` kataloğu korunur.
Kurulum, son çalışma sonucu ve son başarılı kaydın yaşı ayrı alanlardır.
Kaynak hatası eski başarılı kaydı veya diğer kaynakların sonuçlarını örtmez.

Ekran tarama (crt.sh/urlscan), pasif keşif (crt.sh/theHarvester), sosyal
izleme (Maigret/Sherlock), iki IOC, iki ransomware ve ATT&CK akışını kapsar.
Domain filtresi yalnız tarama ve keşfe uygulanır. Global görünümde son
çalışma bütün varlıkların sağlıklı olduğu anlamına gelmez.

Yerel kurulum kontrolü incelenmiş paket/commit/katalog kanıtını kullanır.
Veri yaşının eşiği varsayılan 24 saattir; `--stale-after-hours` ile seçilir.
Kayıtlı kaynak beklemeleri gösterilir. Komutlar önerilir, çalıştırılmaz.

ATT&CK mevcut depolamada ayrı başarısız senkron geçmişi tutmaz. Bu nedenle
son deneme bilinmiyor kalır; doğrulanmış son başarı kanıtı ayrıca gösterilir.
Yeni tablo/migration eklenmez. Eksik veritabanı `./setup` önerir; bozuk
veri boş veya başarılı sonuç olarak sunulmaz.

Günlük kullanım rehberi ilk kayıt, açık veri toplama, inceleme, gerçek adayın
vakaya bağlanması ve tekrar çalıştırmayı örnekler. Gerçek aday olmadığında
vaka/inceleme kararı uydurulmaz; vaka zinciri sentetik testle doğrulanır.

## Doğrulama

Kurulum eksikliği, hiç çalışma olmaması, sıfır sonuç, kaynak hatası ve önceki
başarılı veri ayrı test edilir. Salt-okunur görünüm, domain filtresi,
gelecek/geçersiz saat, kaynak beklemesi ve terminal kaçışları denetlenir.
Bütünleşik günlük kullanım testleri tekrar toplamada bulgu/vaka kimliği ve
geçmişin korunduğunu, kaynak hatasından sonra sosyal karşılaştırmanın son
başarılı kaydı kullandığını doğrular.
