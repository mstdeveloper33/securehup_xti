# ADR 0079 — Kaynakları birbirinden ayıran yerel IOC yaşam döngüsü

**Durum:** Kabul edildi  
**Tarih:** 30 Ekim 2026

## Bağlam

CTI katmanının ilk kalıcı nesnesi domain, IP, URL ve hash göstergesidir. Aynı göstergeyi birden çok kaynak farklı güven, zaman ve geçerlilik bilgisiyle bildirebilir. Tek satırda son gelen kaynağı tutmak kökeni ve çelişkiyi siler; yalnız değer listesi tutmak da kaynağın kaydı geri çekmesi ile bağlantı kesintisini ayıramaz. İlk kişisel sürümde ücretli veya geniş bir internet beslemesine bağlanmadan önce güvenilir yerel veri sözleşmesi gerekir.

## Karar

`cti_indicators`, tür ve kanonik değerden oluşan tekil kimliği tutar. Desteklenen türler domain, IPv4, IPv6, HTTP(S) URL, MD5, SHA-1 ve SHA-256'dır. URL kullanıcı bilgisi, fragment, kontrol karakteri, geçersiz yüzde kodlaması ve HTTP(S) dışı şema kabul etmez; ağ isteği yapılmaz.

`cti_indicator_assertions`, aynı IOC için `source_name + source_reference` kimliğiyle bağımsız kaynak iddialarını tutar. Her iddia 0–100 kaynak güveni, açıklama, isteğe bağlı geçerlilik aralığı, ilk/son gözlem ve etkinlik taşır. Güven puanı zararlılık veya varlık etkisi kararı değildir.

`cti_indicator_assertion_events`, `added/observed/updated/reactivated/revoked` geçmişini eklemeli saklar. Aynı kaynak, aynı gözlem ve aynı içerikle tekrar işlendiğinde olay çoğalmaz. Yeni gözlem ilk/son görülme aralığını genişletir. Geri çekme yalnız kaynak iddiasını etkisizleştirir; ana IOC ve geçmiş silinmez.

`ioc list` varsayılan olarak sorgu anında geçerliliği süren en az bir etkin iddiası olan göstergeleri getirir; `--all` tarihsel kayıtları da gösterir. `show` ve `lookup` seçili IOC'nin görünüm sınırı arkasındaki kaynak/geçmiş kayıtlarını da güvenli üst sınıra kadar doğrular. Bozuk veya eksik bağda kısmi sonuç verilmez.

## Sonuçlar

- Yerel manuel kayıt, sonraki ücretsiz feed adaptörleri için ortak ve kaynaklı hedef modele dönüşür.
- Bir kaynağın değişikliği başka kaynağın güvenini, geçerliliğini veya geri çekme durumunu ezmez.
- Bu sürüm otomatik feed alma, kaynak çalışması/kesinti kaydı, yanlış pozitif kararı, IOC-varlık ilişkisi, aktör/kampanya/malware grafiği, STIX veya engelleme aksiyonu eklemez.
- Şema 33 üç tabloyu boş ekler. Şema 1–32 önce doğrulanmış yedek yayımlar; geçiş tek transaction'da tamamlanır veya sürüm ve DDL geri alınır. Eski veriden IOC uydurulmaz.
