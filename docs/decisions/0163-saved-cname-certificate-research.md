# 0163 — Kayıtlı CNAME ve TLS kanıtlarını ortak araştırmada kullanma

18 Kasım 2026 · 0.159.0 · Uygulandı.

## İhtiyaç

CNAME ve sertifika geçmişi `surface relations` içinde zaten vardı, fakat
ortak `research`, inceleme sırası ve kayıtlı inceleme yollarında görünmüyordu.
Aynı kayıtları tekrar toplamak veya ayrı bir graph deposuna kopyalamak
gerekmiyor. Motorun işi özgün kanıtı tüketen platforma tutarlı sunmaktır.

## Karar

- Mevcut `surface_cname_checks` ve `surface_checks` kayıtları araştırmanın
  aynı salt okuma transaction'ında alınır. Mevcut decoder, hash ve varlık
  kapsam denetimleri kullanılır. Yeni ağ, bağımlılık, tablo veya worker yoktur.
- Saf `domain.research_surface` dönüşümleri CNAME'in her adımını, yalnız
  son hedefin IP'sini ve gerçekten sunulan sertifikayı ayrı bağlantı yapar.
  `cname_alias`, `cname_target_address`, `certificate_presented` mevcut
  varlık ilişkisi sözlüğüyle uyumludur. Kanıt kimliği/tarih/kaynak korunur.
- Sertifika düğümü `certificate` + DER SHA-256 ile tanımlanır. Dosya
  `sha256` IOC'siyle eşleşmez, CIRCL sorgusu doğurmaz. SAN/wildcard adı
  gözlenmiş host olmaz. Aynı sertifika veya dış CNAME hedefi sahiplik,
  aktör veya tehdit kararı yaratmaz.
- Son kontrol durumu düğümde, tarihî olumlu gözlem bağlantıda kalır.
  `surface_cname_check` ile `surface_cname_observation` ayrıdır; kısmi hedef
  hatası gözlenmiş alias'ı silmez veya son IP'yi uydurmaz. TLS kontrolü
  `surface_tls_check`, sertifika gözlemi `surface_certificate` türündedir.
  `source_reference` özgün kontrol domainidir. `current=null` korunur.
- Ters CNAME araması en yeni 1.000 CNAME kaydını inceler. CNAME istekte
  en fazla 1.000 farklı kayıt/16 MiB; web DNS/TLS birlikte aynı 1.000
  kayıt/16 MiB bütçesini kullanır. Düğüm başına aile başına 200 bağlantı,
  bağlantı/sertifika başına 50 kanıt sınırı vardır. Eski kök kanıtı ters
  pencere dışında kalsa da önceden doğrulanan kaydı kaybolmaz. Eksik okuma
  kapsam kodlarıyla görünürdür; okunamayan son kayıt yerine eskisi konmaz.
- İnceleme kayıt modelinin 52 kanıt sınırı korunur. Domainin son DNS,
  TLS ve CNAME kontrolü önce; ardından sığan IOC iddiaları gösterilir.
  Kesilen iddiaların toplamı ve `evidence_truncated` gerekçesi korunur.
- Kural v2 son CNAME/TLS hatasını ve sertifikanın geçerlilik tarihlerini
  doğrulama gerekçesi yapar. Geçerlilik süresi dolmuş tarihî sertifikanın
  bugün hâlâ sunulduğu söylenmez. V1 incelemeler korunur, v2 ilk inceleme
  yeni politika başlangıcı olur. Model 1, çekirdek 75, kuyruk 2 aynı kalır.

## Sınırlar ve kabul

Araştırma hâlâ en fazla iki adım/100 düğüm/200 bağlantıdır; ters pencere
bütün envanter değildir. Tedarikçi kararları, pasif adaylar, sertifika kökü
ile yeni sorgu türü, genel çıkarım ve kimlik birleştirme bu dilime dahil
değildir. Analist kararı, alarm veya kaynak işi davranışı değiştirilmez.

Kontrollü testler özgün kimlikler, tek okuma kesiti, şirket izolasyonu,
hiç ağ/alt süreç açmama, bozuk kanıt reddi, sayfa işareti, sınırlar,
sertifika/dosya ayrımı, eski inceleme ve yedek korunmasını doğrular.
Sonuçlar [kabul kaydında](../ACCEPTANCE_REVIEW.md) ayrı tutulur; bu kayıt
Tavily/Nmap canlı kabulü veya bütün üretim kapasitesinin onayı değildir.
