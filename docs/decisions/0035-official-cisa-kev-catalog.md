# 0035 — Resmî CISA KEV kataloğunu kaynak hatasından ve varlık maruziyetinden ayır

**Durum:** Kabul edildi · **Tarih:** 29 Ekim 2026 · **Sürüm:** 0.35.0

## Bağlam

Zafiyet katmanının ilk adımı, gerçek saldırılarda istismar edildiği bilinen CVE kayıtlarını güvenilir bir kaynaktan sürümlü saklamaktır. Kaynak kesintisini “kayıt yok” diye yorumlamak önceki bilgiyi sessizce silebilir. KEV kaydını izlenen varlıkta zafiyet kanıtı saymak da ürün ve sürüm bilinmeden yanlış alarm üretir.

Birincil kaynaklar [CISA KEV kataloğu](https://www.cisa.gov/known-exploited-vulnerabilities-catalog) ve CISA'nın bu sayfadan yayımladığı sabit JSON akışıdır.

## Karar

- Ağ bağlantısı yalnız kullanıcının açık `vuln sync --source kev` komutuyla kurulur.
- Adaptör yalnız sabit resmî HTTPS adresine gider; yönlendirme izlemez, sıkıştırma kabul etmez ve 30 saniye/16 MiB/10.000 kayıt sınırı uygular.
- JSON yinelenen anahtar, beklenmeyen yapı, tutarsız toplam, yinelenen CVE, bozuk tarih veya sınır dışı metin taşırsa bütün anlık görüntü reddedilir.
- Geçerli tam katalog tek transaction'da uygulanır. Kayıtlar `added`, `updated`, `deactivated` veya `reactivated` olayıyla eklemeli geçmişe girer; aynı kayıt yeniden yazılmaz.
- Katalogda artık bulunmayan CVE silinmez; `active=false` olur. Böylece geçmiş ve kaynak geri çekmesi korunur.
- Kaynak başarısızlığı ayrı bir başarısız çalışmadır. Önceki geçerli katalog değiştirilmez.
- `status`, `list` ve `show` yalnız yerel kaydı okur; ağ, onarım veya gizli güncelleme yapmaz.
- KEV kaydı, varlık maruziyeti değildir. Bu sürüm ürün/sürüm eşleştirmesi, CVSS, EPSS veya otomatik risk kararı üretmez.

## Sonuçlar

Kullanıcı CISA'nın güncel kataloğunu dosya hazırlamadan terminalden alabilir, kaynağın son başarı/başarısızlığını ve her CVE'nin katalog yaşam döngüsünü inceleyebilir. NVD CVE/CVSS ve FIRST EPSS ayrı adaptörler olarak eklenecek; kaynakların tarih ve anlamları birbirine karıştırılmayacaktır.

## Veri ve geri dönüş

Şema 17, `vulnerability_source_runs`, `kev_entries` ve `kev_entry_events` tablolarını ekler. Şema 16→17 geçişi önce doğrulanabilir yedek alır, tabloları tek transaction'da boş oluşturur ve bütünlük kontrollerinden sonra sürümü yükseltir. Hata ana veritabanını şema 16'da bırakır. Eski kayıtlardan KEV veya maruziyet uydurulmaz. Eski uygulamaya dönüş için geçiş öncesi yedek kullanılır.

## Doğrulama

Testler sınırlı taşıma ve katı ayrıştırmayı; ekleme, aynı kalma, değişme, katalogdan çıkma ve yeniden girişi; kaynak hatasında eski kataloğun korunmasını; bozuk saklı kayıtta güvenli durmayı; kilit, terminal, yedek/restore ve şema 16→17 geçiş/geri alma yollarını doğrular. Otomatik testlerde gerçek ağ kullanılmaz.
