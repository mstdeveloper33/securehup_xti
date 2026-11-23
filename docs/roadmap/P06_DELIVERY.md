# P06 — Aksiyon ve paylaşım teslim kartı

22 Kasım 2026. **Durum: kullanıcının seçtiği yerel motor kapsamı uygulandı;
G01, G03, G04 ve G05'in aşağıdaki sınırları yerel kabulden geçti. Haricî
SIEM/SOAR/ticket bağlantıları kullanıcı kararıyla kapsam dışı. Hızlı ve tam
yerel repo kapıları geçti; gerçek Linux CI kabulü ayrıca açık.**

## Kullanıcı sonucu ve gereksinimler

- **G01:** Phishing, sosyal, uygulama, kod deposu ve arama hedefi için
  gönderilmeyen taslak; insan onayı; dış başvuru referansı ve sonuç takibi.
- **G03:** Vaka/kanıt türüne uygun, sürümlü, deterministik runbook; atomik
  ve tekrar güvenli görev üretimi.
- **G04:** Aynı donmuş vaka görünümünden teknik JSON, yönetici HTML,
  kanıt CSV'si, isteğe bağlı PDF ve doğrulanabilir manifest; IOC için
  CSV/JSON/STIX çıktı.
- **G05:** CSV/JSON/STIX IOC önizleme, kesin doğrulama, atomik toplu içe
  alma, makbuz ve dışa aktarma.
- **G02 desteği:** Var olan vaka, görev, kanıt ve zaman çizelgesi yeniden
  kullanılmaktadır. Ekip atama, SLA, kullanıcı rolü ve UI platform ekibindedir.

Kullanıcının “5. madde olmasın” kararı gereği dış SIEM/SOAR/ticket
bağlayıcıları bu teslimin parçası değildir. Geniş STIX/TAXII, e-posta/SMS,
otomatik engelleme ve LLM ertelemeleri korunur.

## Bileşen kararı

Yeni repo, veri sağlayıcısı, ücretli API veya Python paketi eklenmedi.

| Bileşen | Durum | Rol |
|---|---|---|
| XTI vaka/IOC kayıtları | Seçili ve entegre | Tek kanıt, görev ve IOC ana kaydı |
| SQLite şema 95 | Seçili ve entegre | Runbook, takedown olay zinciri ve IOC import makbuzu |
| Playwright 1.65.2 / Chromium 1255 | Önceden sabit, P06'da yeniden kullanıldı | İsteğe bağlı, ağsız yönetici PDF'i |
| Haricî takedown/abuse API | Seçilmedi | Motor başvuru göndermez |
| SIEM/SOAR/Jira/ServiceNow | Kullanıcı kararıyla hariç | Bu teslimde bağlayıcı yok |

## Uygulanan yaşam döngüsü

1. Vaka görünümü tek SQLite okuma transaction'ında dondurulur.
2. Runbook planı vaka/etkin kanıt hash'ine bağlanır; güncel özetle vaka
   görevleri tek transaction'da oluşturulur.
3. Paket yeni dizine 0700/0600 izinle yazılır; yarım yayında dizin kaldırılır;
   manifest tüm dosyaları doğrular.
4. Takedown yalnız uygun etkin kanıttan taslak olur; katı durum geçişi ve
   optimistic revision ile ilerler; motor ağ işlemi yapmaz.
5. IOC dosyası en fazla 32 MiB/50.000 kayıt olarak tamamen doğrulanır;
   bütün satırlar tek transaction'da işlenir ve tekrar makbuzu saklanır.
6. Engine okuma işlemleri ağsızdır. Firma yazmaları `expected_workspace_id`
   çiti ve yerel execution lock kullanır. Keyfî dosya yolu platform JSON'una
   açılmaz.
7. Şema94→95 geçişi önce yedek üretir; geri dönüş eski yedeğin yeni alana
   restore edilmesiyle yapılır.

## Güvenlik ve doğruluk sınırları

- Runbook öneri ve görevdir; eylemin gerçekleştiği hükmü değildir.
- Takedown `submitted` yalnız insanın verdiği dış referansla kaydedilir;
  otomatik gönderim yoktur.
- Kaynakta görülen aday doğrulanmış phishing/ihlal değildir.
- Paket manifesti bütünlük sağlar, kimlik doğrulayan dijital imza değildir.
- IOC kaynak iddiaları birbirini ezmez; IOC varlığı otomatik zararlılık veya
  engelleme kararı değildir.
- CSV formül hücreleri güvenli ve geri döndürülebilir kodlanır; dosya/symlink
  değişimleri ve mevcut hedef üzerine yazma reddedilir.

## Yerel kabul sonucu

| Alan | Sonuç |
|---|---|
| P06 hedefli testler | 20 test geçti: davranış, CLI, engine/platform, migration, symlink/TOCTOU ve IOC |
| Yakın regresyon | Vaka, IOC, engine, platform ve storage ile toplam 79 test geçti |
| Şema geçişi | 94→95 yedekli/atomik; eski asset korundu; yedekten restore ve tekrar geçiş geçti |
| Firma sınırı | Başka firma kaydı `not_found`; yanlış workspace yazması reddedildi |
| Bozuk kayıt | Takedown geçiş zinciri, runbook kaydı ve paket dosya bütünlüğü fail-closed |
| PDF | Mock kabulü ve gerçek yerel Chromium ile `%PDF-1.4` çıktı; ağ isteği 0 |
| Kapasite | 5.000 eski görev + 5.001 olay; 20.000 IOC; tekrar yazımı 0 |
| Kapasite süreleri | geçmiş 0,144 sn; paket+doğrulama 0,194 sn; IOC import+replay 3,034 sn; STIX 0,804 sn |
| Kapasite bellek/disk | tepe RSS 175,52 MiB; DB 37.601.280 bayt; paket 4.269.331 bayt |
| Kapasite ağı | 0 ağ isteği |
| Hızlı repo kapısı | `./scripts/check-fast`: 2.281 test, 1.654,541 sn, hata yok, macOS'ta 4 beklenen Linux atlaması |
| Tam repo kapısı | `./scripts/check`: 3.622 test, 2.466,813 sn, hata yok, macOS'ta 4 beklenen Linux atlaması |

Kapasite komutu:

```sh
PYTHONPYCACHEPREFIX=/tmp/xti-pyc ./scripts/python \
  scripts/check-actionability-delivery.py
```

Bu kontrollü ölçüm 7/24 hizmet seviyesi, bütün olası dosyalar veya haricî
sağlayıcı kabulü değildir.

## Açık doğrulamalar

1. Push sonrasında gerçek Linux CI/yükseltme sonucu ayrı kaydedilecek; yerel
   macOS sonucu Linux hizmet çalıştırma kabulü sayılmaz.
2. Gerçek takedown sağlayıcı portalı motorun otomatik fonksiyonu değildir;
   hukuk/marka yetkisi ve insan başvurusu işletme prosedürüdür.
3. Haricî bağlayıcılar kullanıcı kararıyla hariçtir; ileride istenirse her
   gerçek alıcı için ayrı kimlik, alan eşleme, tekrar ve teslim kabulü gerekir.

Kullanım: [ACTIONABILITY](../ACTIONABILITY.md). Mimari karar:
[ADR0191](../decisions/0191-human-approved-actionability.md).
