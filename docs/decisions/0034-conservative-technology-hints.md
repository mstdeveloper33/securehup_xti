# 0034 — Teknoloji ipucunu ürün ve sürüm kanıtından ayır

**Durum:** Kabul edildi · **Tarih:** 29 Ekim 2026 · **Sürüm:** 0.34.0

## Bağlam

Sınırlı servis kontrolü, yalnız kullanıcının açıkça yetkilendirdiği kesin genel IP üzerinde sabit on TCP portuna bağlantı kurulup kurulamadığını kanıtlıyor. Port numarası yaygın bir protokol kullanımını çağrıştırabilir; çalışan yazılımın üreticisini, ürününü veya sürümünü doğrulamaz. Port ipucunu ürün gerçeği kabul etmek, sonraki CVE eşleştirmesinde çok sayıda yanlış alarm üretir.

## Karar

- `surface technologies DOMAIN`, yalnız son kayıtlı servis kanıtını salt okunur değerlendirir.
- Yalnız `open` görülen portlar ipucu olur; kapalı veya belirsiz porttan teknoloji yokluğu çıkarılmaz.
- Her kayıt `confidence=hint` ve `detection_method=tcp_connect_only` taşır.
- `vendor`, `product` ve `version` alanları bilinmiyorsa açıkça `null` kalır.
- Port ipuçları `cve_match_eligible=false` taşır; ürün ve sürüm kanıtı eklenmeden CVE ile ilişkilendirilmez.
- Kanıt kimliği, kayıt zamanı ve güncellik her ipucunda korunur.
- Kontrol edilmemiş, başarısız, kısmi, eski ve zamanı tutarsız kanıt ayrı durumlar olarak gösterilir.
- Komut ağ isteği, banner okuma, protokol konuşması, oturum açma, kayıt yazma veya zafiyet taraması yapmaz.

## Sonuçlar

Bir kullanıcı hangi uç noktaların hangi yaygın kullanımları çağrıştırdığını görebilir; fakat platform bunu doğrulanmış ürün gibi sunmaz. CVE katmanı için gerekli doğruluk sınırı kod ve JSON sözleşmesinde görünür hâle gelir. Ürün/sürüm doğrulama kaynağı ve sürüm aralığı eşleştirmesi sonraki ayrı teslimlerdir.

## Veri ve geri dönüş

Yeni tablo veya migration yoktur; şema 16 değişmez. Görünüm mevcut son servis kanıtından her çalıştırmada yeniden üretilir. Eski uygulamaya dönüş veri dönüşümü gerektirmez.

## Doğrulama

Testler kanıt yokluğunu, açık port ipuçlarını, boş üretici/ürün/sürüm alanlarını, kapalı CVE uygunluğunu, kısmi/başarısız/eski/zamanı tutarsız kanıtı, geçersiz eşiği ve salt okunur terminal/JSON akışını doğrular. Gerçek ağ bağlantısı kullanılmaz.
