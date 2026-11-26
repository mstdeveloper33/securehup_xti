# P06 abuse iletişim rotası teslim kartı

**Sürüm:** 0.195.0 · **Şema:** 101 · **Tarih:** 25 Kasım 2026
**A–K gereksinimleri:** G01 takedown, J01 provenance, J03 insan incelemesi,
I03 veri minimizasyonu.

## Kullanıcı sonucu

Analist, etkin vaka kanıtındaki kesin domain veya genel IP için resmî abuse
iletişim adaylarını bulabilir; adayın nereden geldiğini ve güncelliğini görür,
insan kararı verir ve yalnız güncel onaylı adayı gönderilmeyen takedown
taslağına bağlar. Kaynak hatası eski başarılı kanıtı silmez. Motor dışarıya
başvuru göndermez.

## Bileşen kararı

| Bileşen | Rol | Durum |
|---|---|---|
| IANA RDAP bootstrap + resmî domain RDAP | Registrar abuse rolünü bulma | Seçildi ve kodlandı |
| IANA RDAP bootstrap + resmî RIR RDAP | IP ağ abuse rolünü bulma | Seçildi ve kodlandı |
| RFC 9116 `security.txt` | Yardımcı güvenlik iletişimi | Seçildi ve kodlandı; düşük güven |
| Yerel WHOIS | RDAP boşsa sıkı allowlist fallback | İsteğe bağlı; araç/koşul bekleyebilir |
| AbuseIPDB | IP itibar/iletişim API'si | Seçilmedi; paket amacı için gereksiz hesap bağımlılığı |
| SOAR/OpenCTI eklentisi | Haricî workflow | Seçilmedi; XTI kendi kanıt/karar kaynağıdır |

Yeni Python paketi veya ücretli API eklenmedi. Ağ ve alt süreç sınırları XTI
içinde uygulanır; kaynak metni shell'e veya terminal markup'a aktarılmaz.

## Uçtan uca teslim edilen akış

1. Vaka kanıtına bağlı ağsız plan ve sürümlü watch oluşturma.
2. Domain/IP RDAP, domain `security.txt` ve koşullu WHOIS toplama.
3. Kaynak bazlı tam/boş/atlandı/gereksinim eksik/hata makbuzu.
4. Aday dedup, değişme/kaybolma/yeniden görünme geçmişi ve provenance.
5. İnsan approved/rejected/uncertain kararı; kanıt değişince bayat karar.
6. Zamanı gelen işler, sayfalı geçmiş, bounded monitor ve kesinti recovery.
7. Güncel onaylı adayı aynı vaka/kanıt takedown taslağına bağlama.
8. Takedown approve/submit öncesinde aday bağını yeniden doğrulama.
9. Salt okunur engine ve workspace çitli firma platformu işlemleri.
10. Şema 100→101 açık yedekli migration ve boş alana restore uyumu.

## Doğrulama kanıtı

Hedefli test aileleri:

- saf RDAP/security.txt/WHOIS parser ve sınır doğrulamaları;
- sabitlenmiş HTTPS, redirect, boyut/süre ve WHOIS fallback adaptörü;
- kalıcı lifecycle, kaynak hatasında eski kanıt, recovery ve idempotency;
- insan kararı ile takedown bağının değişiklikte bayatlaması;
- engine/platform contract, workspace izolasyonu ve bilinmeyen alan reddi;
- şema 100→101 migration, backup/restore ve ham gövde saklamama;
- 250 değişmeyen yenilemede tek aday ve 50'lik sayfalama kapasitesi;
- kaynak manifesti ve mevcut actionability geriye uyumluluğu.

Yerel geliştirme kabulünde hedefli testlerin tamamı geçmiştir. 250 tur
kapasite testi 31,240 saniyede tamamlanmış; 250 çalışma geçmişi korunurken
aday sayısı bir kalmıştır. Bu ölçüm üretim SLO'su değildir. Canlı pasif
kabulte `securehup.com` domain RDAP iki, `1.1.1.1` IP RDAP bir ve
`www.apple.com` security.txt bir aday üretmiştir. SecureHup security.txt
dosyasındaki göreli `Canonical` RFC 9116 URI şartını karşılamadığı için
fail-closed reddedilmiş; ikinci kontrolde bir istek, 156 bayt, son URL ve
içerik hash'i hata kanıtında korunmuştur. 26 Kasım 2026 yerel macOS/Python
3.13 sonucunda hızlı kapı 2.385 testi 2.777,756 saniyede, tam kapı 3.730
testi 3.533,545 saniyede sıfır hatayla tamamlamıştır; her iki turda yalnız
Linux çalışma zamanı isteyen dört test beklendiği gibi atlanmıştır. Bu
sonuçlar [STATUS](../STATUS.md) ve `NOTES.md` N-058 içinde kayıtlıdır; temiz
Linux kabulü değildir.

## Bilinçli sınırlar ve açık kanıtlar

- Otomatik e-posta/portal/takedown gönderimi yoktur.
- WHOIS normal kurulumun zorunlu parçası değildir ve düşük güvenlidir.
- Müşteriye ticari saklama/gösterim ve her RDAP/RIR/WHOIS kaynağının koşulları
  hukuk/ürün incelemesinde açık kalır.
- Koşullu WHOIS fallback canlı yolu ve temiz Linux tam kapısı fixture ile
  kapatılmaz; sonuçlar `NOTES.md` N-058 altında tutulur.
- Tüketici backend gerçek scheduler, kullanıcı kimliği, RBAC ve dış başvuru
  yetkisini sağlar; motor kanıt, karar ve tekrar güvenli workflow'u sağlar.

Kullanım: [Abuse iletişim rehberi](../ABUSE_CONTACTS.md).
Mimari karar: [ADR 0200](../decisions/0200-reviewed-abuse-contact-routing.md).
