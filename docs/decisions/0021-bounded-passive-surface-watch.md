# ADR-0021 — Sınırlı pasif alt alan adı izleme

**Tarih:** 29 Ekim 2026 · **Durum:** 0.21.0'da uygulandı.

## Karar

`surface watch KÖK`, mevcut pasif `surface discover` kullanım senaryosunu terminal açık kaldığı sürece tekrarlar. Kullanıcı en fazla turu, tamamlanan turlar arasındaki beklemeyi ve yeni tur başlatılabilecek toplam süreyi açıkça sınırlar. Varsayılanlar 3 tur, 3600 saniye bekleme ve 86400 saniye süredir. Kabul edilen sınırlar sırasıyla 1–1000, 300–86400 ve 1–604800'dür.

Zaman bütçesi monotonic saatle ölçülür. Süre dolduktan sonra yeni tur başlatılmaz; daha önce başlamış crt.sh çağrısı kendi ağ sınırlarıyla tamamlanabilir ve toplam süre bütçeyi aşabilir. Saat geri giderse izleme güvenli hatayla durur. Kaynak çağrısının başarısız veya kısmi olması döngüyü tek başına durdurmaz; sonuç kendi turuna yazılır ve bütçe varsa sonraki tur denenir.

Her tur mevcut `SurfaceDiscoveryService` üzerinden yürür. Aday, kaynak kanıtı, ilk yerel bildirim ve çalışma özeti mevcut atomik yazma yolunu kullanır. Aynı aday veya aynı sertifika kanıtı tekrar üretmez; her tur ise sonucu ne olursa olsun ayrı `surface_discovery_runs` kaydıdır. Yeni bir izleme oturumu tablosu eklenmez. Final özet yalnız o terminal çağrısının tamamlanan turlarını küçük sayaçlar ve çalışma kimlikleriyle taşır.

Terminal bütün döngü ve bekleme boyunca mevcut yerel çalıştırıcı kilidini tutar. Böylece aynı kayıt alanında ikinci internet araması, hedef kontrolü veya bakım çalışması başlamaz. Ağ beklerken ya da turlar arasında SQLite yazma işlemi açık tutulmaz; salt okuma ve kısa kullanıcı kararları ayrı çalışabilir.

`Ctrl+C` üst terminal katmanında çıkış 130 üretir. Daha önce tamamlanan turlar kalıcıdır ve `surface runs KÖK` ile açılır. O anda henüz tamamlanmamış kaynak çağrısı için sahte başarısız/yarım çalışma kaydı oluşturulmaz. Zorla süreç kapanışında da tamamlanmış transaction'lar korunur; yeniden açılış yarım döngüyü otomatik sürdürmez.

## Güvenlik ve kapsam

İzleme yalnız kamuya açık crt.sh arşivini sorgular. Bulunan alt alan adlarına DNS, TLS veya HTTPS bağlantısı göndermez; otomatik varlık, sahiplik veya aktif kapsam kararı oluşturmaz. Aktif kontrol için adayın ayrıca kaydedilmesi ve `surface approve` ile açık yetki beyanı gerekir.

Geçersiz sınırlar ve bilinmeyen kök kaynak nesnesi kullanılmadan önce reddedilir. Kaynak hata metni mevcut görünür-karakter ve uzunluk sınırlarından geçer. İnsan terminal çıktısı dinamik metni güvenli biçimde kaçırır; JSON standart `ok/data` zarfını kullanır.

## Sınırlar ve sonuçlar

Bu bir daemon, işletim sistemi zamanlayıcısı veya sürekli CT akışı değildir. Bilgisayar ya da terminal kapalıyken çalışmaz; kaçırılan dönem için kaynak kapsamı uydurmaz. Yalnız crt.sh'nin sorgu anında sunduğu arşiv görünümünü örnekler. Pasif DNS, tam subdomain envanteri, port/servis keşfi ve dış bildirim teslimi ayrı iş paketleridir.

Şema 12 değişmez. 0.20.0 kayıt alanı migration olmadan kullanılabilir; yedek/restore tamamlanan tur kayıtlarını, adayları, kanıtları ve bildirimleri mevcut kurallarla taşır.
