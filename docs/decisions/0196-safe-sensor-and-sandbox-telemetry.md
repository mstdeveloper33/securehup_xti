# 0196 — Güvenli sensör ve tamamlanmış sandbox telemetrisi

Tarih: 23 Kasım 2026 · Durum: kabul edildi · Paket: P12 · Şema: 98.

## Bağlam

A05 honeypot/sinkhole telemetrisi ile A06 malware sandbox sonucu XTI'da yoktu.
Ham Cowrie ve CAPE verisi ise parola, komut, zararlı dosya, PCAP ve bellek
dökümü gibi yüksek riskli içerik taşıyabilir. XTI'nın ana görevi bunları
çalıştırmak veya ham arşiv olmak değil; kuruluş kapsamlı, kaynağı belli ve
insan incelemeli güvenli kanıt sağlamaktır.

## Karar

- XTI kendi kesin `xti-sensor-v1`, Cowrie JSONL ve tamamlanmış CAPE
  `report.json` için üç ayrı adaptör sunar.
- Cowrie ve CAPE kurulmaz, vendored edilmez ve XTI sürecinden çalıştırılmaz.
- Yalnız allowlist alanlar normalize edilir. Kullanıcı adı, parola, ham komut,
  mesaj, örnek dosya, PCAP, bellek dökümü ve ham rapor kalıcı alana girmez.
- Dosya önce yazmasız ve sınırlandırılmış önizlenir; içerik SHA-256 onayı,
  kaynak sürümü ve idempotency anahtarı olmadan uygulanmaz.
- Kaynak, çalışma, kayıt sürümü ve insan incelemesi eklemeli geçmişle tutulur.
  Değişmiş kanıt önceki kararı silmez fakat yeniden inceleme gerektirir.
- Ortak global arama, `record.get`, vaka kanıtı ve P07 izleme yeniden
  kullanılır; ikinci bir alarm/vaka sistemi kurulmaz.
- Engine yalnız okur. Firma platformu dosya yolu değil, en çok 1.000 kesin
  normalize kayıt kabul eder. Yerel dosya terminal işletim sınırındadır.
- XTI hiçbir telemetri sonucundan otomatik saldırı, malware veya atıf hükmü
  üretmez.

## Seçilen dış bileşenler

- [Cowrie](https://github.com/cowrie/cowrie) ayrı çalışabilen SSH/Telnet
  honeypot adayıdır; XTI yalnız resmî JSON olay biçiminin seçilmiş alt
  kümesini okur. Kök lisansı BSD koşulları taşır.
- [CAPEv2](https://github.com/kevoreilly/CAPEv2) ayrı malware sandbox adayıdır;
  XTI yalnız tamamlanmış rapor dosyasını okur. Kök LICENSE GPLv3'tür; CAPE
  XTI'ya gömülmez veya bu teslimle dağıtılmaz.

Araç lisansı, sensör verisinin veya analiz edilen örneğin saklama ve müşteri
gösterim hakkı değildir. Gerçek işletim ve ticari dağıtım ayrı karardır.

## Sonuçlar

Şema98 dokuz kuruluş kapsamlı telemetri tablosu ve `telemetry` vaka kanıtı
türünü ekler. Şema97 geçişi önce yedek alır, eski vaka rowid'lerini korur ve
yeni tabloları boş başlatır. Kaynak bozulması, sayaç/hash/olay zinciri
uyuşmazlığı ve kesilmiş çalışma güvenli biçimde durur.

Normalize kanıtlar 0.192.0/şema99 ile P08 retention kapsamına alınmıştır;
hold, aktif vaka koruması, çok kuşaklı arşiv, saydam okuma, restore, migration
ve kapasite kabulü [ADR0197](0197-telemetry-retention-generations.md) ile
tamamlanmıştır. Gerçek Cowrie/CAPE kurulumu bulunmadığından adaptörlerin canlı
kabulü açık dış gereksinimdir; kontrollü fixture canlı sağlayıcı kanıtı
değildir ve Cowrie/CAPE bu aşamada kurulmaz.
