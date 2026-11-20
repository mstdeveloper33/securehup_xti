# 0184 — Etkin kuyruk ile kalıcı geçmiş; açık kaynak iddiası uyuşmazlığı

20 Kasım 2026. Durum: uygulandı, yerel ve Linux teslim kabulü tamamlandı.

Kuyruk3 bütün saklı işlere 10.000 sınırı uyguluyor ve platform kabulünde
bütün olayları yeniden oynatıyordu. Kuyruk4 özgün tabloları korur;
`engine_job_catalog` tür/durum/sıra indeksini ve değişiklik korumasını
ekler. Terminal durum atomik olarak `archive` alanına ayrılır. Kapasite
yalnız queued/running iş sayısına uygulanır; anahtar/sonuç/retry özgün
kayıttan seçilerek doğrulanır. Sorgular SQL'de sayfalanır ve kesit sürümünü
kontrol eder. Tam SQLite/olay denetimi audit/yedek/geçiş bakımındadır.
İndeks tek başına kanıt olmaz; seçilen kayıtla karşılaştırılır. Koruma
kirliyse sessiz yeniden kurma yoktur. Yeni tetikleyicilerin tam tanımı
şema denetiminde doğrulanır.

3→4 özgün satır/rowid/JSON/hash korur, önce doğrulanmış eski kuyruk
yedeği alır. Eski kod yeni şemayı reddeder. Kişisel/firma yönetim kilidi
ve ortak worker korunur. Fiziksel gövde silme, sıkıştırma veya ayrı arşiv
dosyasına taşıma yoktur; tek dosyalı atomiklik ve mevcut backup/restore
sözleşmesi korunur. Disk/bakım maliyeti birikimle büyümeye devam eder.

Kaynak uyuşmazlığı saf `source_conflicts` kurallarıyla mevcut araştırma
kesitinden türetilir. Mevcut `source-comparison-v1` tarihî sözleşmesi
değişmez; yeni read işlemi `research.conflicts` sürümlü açıklama üretir.
Tam profil adresi, farklı kaynak, güncel kanıt ve en fazla bir saatlik
gözlem farkı karşıt varlık iddiasını inceleme adayı yapar. Erişim hatası,
eski/geçersiz/farklı zamanlı kanıt, profil kimlik uyuşmazlığı ve CTI yaşam
döngüsü ayrı kalır. İnsan kararı kaynak iddiasına çevrilmez; bağımsızlık
veya doğruluk oylanmaz. İnceleme önceliği v10 yeni gerekçe ekler; eski
donmuş v9 JSON/hash ve vakalar aynen okunur. Çekirdek88, dış JSONv1 ve
kaynak işi7 bu nedenle değişmez.

[Kabul kapsamı](../roadmap/JOB_HISTORY_CONFLICT_DELIVERY.md).
