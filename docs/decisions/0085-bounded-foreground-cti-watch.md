# 0085 — Sınırlı ön plan CTI arama zamanlaması

**Durum:** Kabul edildi · **Tarih:** 30 Ekim 2026 · **Sürüm:** 0.85.0

## Bağlam

Kayıtlı arama açık komutla tek kez çalışıyordu. Kişisel ve ücretsiz kullanımda değişimi düzenli izlemek yararlıdır; buna karşılık sessiz bir daemon veya işletim sistemi görevi kurmak yaşam döngüsü, kilit, kurtarma ve kullanıcı beklentisi yükü getirir.

## Karar

- `cti watch-monitor`, tek etkin kayıtlı aramayı yalnız terminal açıkken tekrarlar.
- Tur sayısı 1–1000, aralık 300–86400 saniye ve yeni tur başlatma bütçesi 1–604800 saniyedir. Sonuç görünümü 1–500 öğeyle sınırlıdır; tam çalışma anlık görüntüsü kesilmez.
- Süre duvar saatiyle değil monoton saatle ölçülür. Saat geriler veya sonlu olmayan değer verirse izleme durur.
- Her tur mevcut `watch-run` yolunu kullanır; fark, sessiz başlangıç ve yerel bildirim kuralları çoğaltılmaz.
- Bekleme en fazla bir saniyelik parçalarla yapılır. `Ctrl+C` üst katmana iletilir; tamamlanmış turlar kalıcı kalır.
- CLI izleme boyunca ortak yerel çalışma kilidini tutar. Daemon, açılış görevi, dış ağ veya yeni şema yoktur.

## Sonuçlar

Kullanıcı ek altyapı ve ücret olmadan CTI aramasını görünür biçimde düzenli çalıştırabilir. Terminal kapanınca izleme biter. Kalıcı işletim sistemi zamanlaması ileride açık kurulum/kaldırma, sağlık ve kurtarma sözleşmeleriyle ayrı ele alınmalıdır.
