# ADR 0071 — Resmî üretici zafiyet kaynağı kapısı

**Durum:** Kabul edildi  
**Tarih:** 30 Ekim 2026

## Bağlam

Yeni kaynak eklemek yalnız HTTP adaptörü yazmak değildir. Ücretsiz kişisel profil; gizli anahtar, büyük ve sürekli tam veri indirmesi veya belirsiz yeniden kullanım koşulu gerektiren bir bağlantıyı sürdürülebilir biçimde işletemez. Kaynak seçimi belgelenmezse her yeni sağlayıcı farklı ve görünmez ölçütlerle çekirdeğe girebilir.

## Karar

`official-vendor-source-gate-v1` şu zorunlu ölçütleri kullanır:

1. veri ürün/dağıtım üreticisinin resmî kanalından gelmeli;
2. kişisel profilde ücretsiz ve kimlik doğrulamasız erişilebilmeli;
3. yapılandırılmış, doğrulanabilir makine biçimi olmalı;
4. tek kayıt veya küçük yanıtla sınırlandırılabilmeli;
5. ürün, paket, sürüm veya yayın bağlamı taşımalı;
6. yeniden kullanım koşulu açıkça kaydedilebilmeli.

Bakım riski ve engeller ayrıca gösterilir; sayısal puan zorunlu kapının yerini almaz. `vuln source-evaluation` sabit değerlendirme tarihi, profil sürümü, kanıt açıklamaları ve resmî bağlantıları ağsız gösterir. Çalışma sırasında kaynak durumunu ölçtüğü iddia edilmez.

30 Ekim 2026 değerlendirmesi:

- **Canonical Ubuntu OSV — seçildi.** Ubuntu Security Team, desteklenen yayınlar için yapılandırılmış OSV verisini metadata, bireysel dosyalı resmî GitHub deposu ve merkezi OSV API kanallarında yayımlıyor. Depo CC-BY-SA-4.0 lisanslıdır. Ekosistem, kaynak paket, sürümler ve düzeltme olayları bulunur. [Ubuntu OSV belgesi](https://documentation.ubuntu.com/security/security-updates/osv/), [Canonical veri deposu](https://github.com/canonical/ubuntu-security-notices).
- **Microsoft MSRC CVRF — ertelendi.** MSRC anahtar zorunluluğunu kaldırmıştır fakat bu dilimde tek-CVE küçük yanıt yolu ve yeniden kullanım koşulu sabitlenmemiştir. [MSRC API duyurusu](https://www.microsoft.com/en-us/msrc/blog/2021/02/continuing-to-listen-good-news-about-the-security-update-guide-api), [Security Update Guide](https://msrc.microsoft.com/update-guide/).
- **Debian Security Tracker — ertelendi.** Resmî ve açık JSON ürün/yayın bağlamı sağlar fakat belgelenen makine arayüzü toplu veri kümesidir; kişisel profil için boyut/değişiklik politikası ve yeniden kullanım koşulu tamamlanmalıdır. [Debian Security Tracker](https://security-tracker.debian.org/tracker/).
- **Cisco openVuln — ücretsiz profil için reddedildi.** Resmî API tek CVE erişimi sunar ancak uygulama kaydı, istemci sırrı ve her istek için OAuth belirteci gerektirir. [Cisco kimlik doğrulama belgesi](https://developer.cisco.com/docs/psirt/authentication/).

## Sonuçlar

- Yalnız Ubuntu OSV için küçük, yazmasız tek-kayıt önizleme adaptörü sıradaki uygulamadır.
- Ertelenen kaynaklar yeni kanıtla aynı profil sürümünün sonraki revizyonunda yeniden değerlendirilebilir.
- Kimlik bilgisi isteyen kaynaklar ileride ayrı sır yönetimi ve kullanıcı onayı olmadan çekirdeğe eklenmez.
- Seçilmek verinin eksiksiz, her Ubuntu paketi için geçerli veya yerel varlıkta maruziyet kanıtı olduğu anlamına gelmez.
