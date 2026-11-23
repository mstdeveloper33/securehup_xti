# ADR0190 — XposedOrNot credential kaynağı ve parola gizlilik sınırı

**Tarih:** 22 Kasım 2026
**Durum:** Kabul edildi; P05 için ADR0189'un HIBP verified-domain seçimini değiştirir.

## Karar

Yeni credential-domain çalışmaları `xposedornot_domain` kaynağını kullanır.
HIBP verified-domain yeni profil seçeneği, yapılandırma komutu veya ağ adaptörü
olarak sunulmaz. Şema93'te oluşmuş HIBP geçmişi veri kaybını önlemek için
salt okunur kalır; böyle bir profil `source_retired` olur ve kaynakları
güncellenmeden yeni tur çalıştıramaz.

XposedOrNot domain çağrısı yalnız XTI kuruluşuna açıkça bağlı ve sağlayıcı
hesabında önceden doğrulanmış kesin domain için yapılır. Sağlayıcı tek yanıtta
anahtara bağlı birden fazla domain döndürse bile adaptör yalnız istenen kesin
domaini kabul eder. Ham e-posta adresi yalnız kaynak adaptörü ile bellek içi
maskeleme arasındaki dar sınırda bulunur. SQLite ve dış yanıt yalnız maskeli
adres, kuruluşa özel HMAC kimliği, domain ve ihlal adlarını taşır.

Parola kontrolü terminalde gizli girişle başlar. Parola yerelde legacy
Keccak-512 ile özetlenir ve yalnız ilk 10 hexadecimal karakter sağlayıcıya
gönderilir. Parola, tam hash, gönderilen önek ve sağlayıcının parola
uzunluğu/karakter bileşimi alanı saklanmaz veya sonuçta gösterilmez. Önek
tamamen bilgisiz değildir; olası parola kümesini daraltan sınırlı bilgi
taşır. “Kayıt bulunamadı” sonucu güvenli parola hükmü değildir.

## Teknik ve işletim sınırları

- Domain endpoint'i sabit `https://api.xposedornot.com/v1/domain-breaches/`
  adresidir. Sondaki `/` zorunludur; yönlendirme izlenmez.
- Domain çağrısı API anahtarı ve sağlayıcıda domain doğrulaması ister.
- Kişisel/düşük hacimli ücretsiz sınır ile ticari ürün hakkı aynı değildir.
  Müşteri hizmetinde güncel XposedOrNot ticari planı ve şartları yeniden
  doğrulanır.
- Parola kontrolü kalıcı veya zamanlanmış iş değildir. Kullanıcının açık
  işlemi başına bir kez çalışır.
- Sağlayıcı sonucu aktif hesap, geçerli parola veya doğrulanmış incident
  anlamına gelmez; insan incelemesi korunur.

## Neden resmi SDK doğrudan alınmadı?

Çekirdek motorun sıfır zorunlu bağımlılık sınırı korunur. Resmi Python SDK'nın
HTTP ve kriptografi bağımlılıklarını çekmek yerine yalnız gereken iki sabit
uç nokta için küçük, sınırlandırılmış adaptör yazıldı. Keccak uygulaması resmi
test vektörleriyle doğrulanır; bu kod genel amaçlı kriptografi için kullanılmaz.

## Sonuç

Yeni kaynak doğru provenance ile saklanır; eski kayıtlar silinmez veya yeni
kaynakmış gibi yeniden etiketlenmez. Parola özelliği UI/backend'e bağlanırken
de plaintext motor JSON'una konmamalı; önek istemci veya güvenilen backend
sınırında yerelde hesaplanmalıdır.
