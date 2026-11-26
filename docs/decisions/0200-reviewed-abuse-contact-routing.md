# ADR 0200 — İncelenmiş abuse iletişim rotası

- **Durum:** Kabul edildi
- **Tarih:** 25 Kasım 2026
- **Kapsam:** P06 / G01, J01, J03 ve I03

## Bağlam

Takedown taslağı daha önce alıcıyı operatörün elle yazmasına izin veriyordu.
Bu güvenli bir temel olsa da registrar, ağ işletmecisi veya güvenlik ekibinin
güncel abuse adresini bulma, kaynağını açıklama ve değiştiğinde eski kararı
geçersiz kılma yaşam döngüsü yoktu. Serbest WHOIS metnini veya üçüncü taraf
bir “abuse adresi” API sonucunu doğrudan taslağa aktarmak; yanlış kişi verisi,
eski rota, gizli tekrar istekleri ve kanıtsız otomasyon riski doğururdu.

## Karar

1. Domain ve genel IP hedefi yalnız etkin, donmuş vaka kanıtıyla aynıysa
   izlenebilir.
2. Domain/IP RDAP ana kaynaktır; IANA bootstrap üzerinden doğru resmî hizmet
   seçilir ve yalnız açık `abuse` rolü kabul edilir.
3. `security.txt` yardımcı ve düşük güvenli kaynaktır. Yerel WHOIS yalnız
   RDAP iletişim üretmediğinde isteğe bağlı düşük güvenli fallback'tir.
4. Registrant/kişi alanları, ham kaynak gövdeleri ve serbest WHOIS metni
   saklanmaz. Yalnız küçültülmüş iletişim ve provenance makbuzu kalıcıdır.
5. Her kaynak tam, boş, atlandı, gereksinim eksik veya başarısız olarak ayrı
   kaydedilir. Başarısız yenileme son başarılı adayı silmez.
6. Kaynak sonucu önce adaydır. Takedown bağında kullanılabilmesi için güncel
   gözlem üzerinde açık insan `approved` kararı gerekir.
7. Aday değişirse veya kaybolursa önceki karar bayat olur. Taslak onayı ve
   dış başvuru kaydı sırasında bağ yeniden doğrulanır.
8. Motor hiçbir e-posta, portal başvurusu veya otomatik takedown göndermez.
   `submitted` yalnız insanın dışarıda yaptığı işlemin referans kaydıdır.
9. Engine okumaları ağsızdır; firma yazmaları workspace, revision ve
   idempotency çitlidir. Yalnız `action.contact.refresh` ağ kullanır.

## Seçilmeyenler

- AbuseIPDB bu pakette seçilmedi: amaç IP itibar sorgusu değil, kanıta bağlı
  resmî iletişim rotasıdır; yeni hesap/anahtar ve veri hakkı bağımlılığı
  gereksizdir.
- SOAR/OpenCTI takedown eklentileri seçilmedi: XTI tek motor kaynağı olarak
  kendi vaka, inceleme ve provenance yaşam döngüsünü korur.
- Ham RDAP/WHOIS saklama seçilmedi: gerekli iletişim rotasına göre aşırı veri
  toplar ve kişi verisi riskini büyütür.
- Otomatik gönderim seçilmedi: hukuk, marka yetkisi, yanlış hedef ve sağlayıcı
  koşulları insan onayı gerektirir.

## Sonuçlar

Olumlu olarak kullanıcı elle adres aramak zorunda kalmaz, adresin kaynağını
ve güncelliğini görebilir, değişen adres eski onayla kullanılamaz ve kaynak
kesintisi eski kanıtı yok etmez. Maliyet olarak şema 101 ile ayrı izleme,
çalışma, aday, inceleme ve takedown bağ tabloları; periyodik platform
zamanlaması ve ticari kaynak koşulu incelemesi gerekir. WHOIS aracı normal
kurulum için zorunlu değildir.

## Kabul

Saf parser, sınırlı kaynak adaptörü, kalıcılık/recovery, firma izolasyonu,
takedown yeniden doğrulaması, şema 100→101 geçişi ve birikimli değişmeyen
çalışmalar otomatik testlerle doğrulanır. Canlı pasif domain/IP ve temiz Linux
kabulü ile ticari kullanım koşulları [NOTES.md](../../NOTES.md) içinde açık
kanıt olarak izlenir; fixture canlı kaynak kabulü yerine geçmez.
