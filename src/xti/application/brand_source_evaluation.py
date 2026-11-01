"""Reproducible, offline gate for optional brand-OSINT tools."""

from xti.domain.brand_source_evaluation import (
    BrandSourceCandidate,
    BrandSourceCriterion,
    BrandSourceEvaluationReport,
)


PROFILE_VERSION = "free-brand-osint-tool-gate-v2"
EVALUATED_AT = "2026-10-31"
REQUIRED = (
    "verified_upstream",
    "maintained",
    "free_without_account",
    "stable_json_results",
    "bounded_operation",
    "clear_code_license",
    "no_recovery_enumeration",
    "current_scope_fit",
)


def _criterion(
    key: str, label: str, passed: bool, evidence: str,
) -> BrandSourceCriterion:
    return BrandSourceCriterion(
        key=key,
        label=label,
        required=key in REQUIRED,
        passed=passed,
        evidence=evidence,
    )


class BrandSourceEvaluationService:
    def report(self) -> BrandSourceEvaluationReport:
        maigret = BrandSourceCandidate(
            identifier="maigret-limited-cli",
            label="Maigret sınırlı CLI adaptörü",
            decision="selected_for_adapter",
            purpose=(
                "Kullanıcının açıkça verdiği marka kullanıcı adlarını seçili "
                "sitelerde arama"
            ),
            integration_mode=(
                "Resmî depodaki sabit commit'ten ayrı süreç; yalnız NDJSON sonucunu "
                "doğrulayan XTI adaptörü"
            ),
            maintenance_risk="medium",
            criteria=(
                _criterion(
                    "verified_upstream", "Doğrulanmış ana depo", True,
                    "Ana proje ve kullanım belgeleri soxoj/maigret deposunda yayımlanıyor.",
                ),
                _criterion(
                    "maintained", "Etkin bakım", True,
                    "Açık depo değerlendirme tarihinde etkin bir sürüm ve site "
                    "veritabanı taşıyor.",
                ),
                _criterion(
                    "free_without_account", "Ücretsiz ve araç hesabı gerektirmiyor", True,
                    "Yerel açık kaynak CLI temel profil kontrolleri için ücretli "
                    "API istemiyor.",
                ),
                _criterion(
                    "stable_json_results", "Sonuç için düzenli JSON/NDJSON", True,
                    "CLI simple JSON ve satır bazlı NDJSON sonuç seçeneklerini belgeliyor.",
                ),
                _criterion(
                    "bounded_operation", "Site ve süre sınırı konabiliyor", True,
                    "Çalışma seçili sitelerle ve süre sınırlarıyla daraltılabiliyor.",
                ),
                _criterion(
                    "clear_code_license", "Açık kod lisansı", True,
                    "Ana depo MIT lisansını yayımlıyor.",
                ),
                _criterion(
                    "no_recovery_enumeration", "Hesap kurtarma mekanizması kullanmıyor", True,
                    "Seçilen kullanım yalnız herkese açık profil varlığına bakacak; "
                    "parola sıfırlama yok.",
                ),
                _criterion(
                    "current_scope_fit", "Mevcut marka kapsamına uyuyor", True,
                    "Sosyal kullanıcı adı adayı üretimi CAP-068'in ilk dar dilimidir.",
                ),
            ),
            blockers=(),
            reference_urls=(
                "https://github.com/soxoj/maigret",
            ),
        )
        sherlock = BrandSourceCandidate(
            identifier="sherlock-cli",
            label="Sherlock CLI",
            decision="deferred_duplicate",
            purpose="Aynı kullanıcı adını çok sayıda sosyal ve web sitesinde arama",
            integration_mode=(
                "İsteğe bağlı ayrı süreç; ilk adaptörün yerine geçebilen yedek"
            ),
            maintenance_risk="medium",
            criteria=(
                _criterion(
                    "verified_upstream", "Doğrulanmış ana depo", True,
                    "Ana proje sherlock-project/sherlock deposunda yayımlanıyor.",
                ),
                _criterion(
                    "maintained", "Etkin bakım", True,
                    "Açık depo ve site tanımları değerlendirme tarihinde etkin.",
                ),
                _criterion(
                    "free_without_account", "Ücretsiz ve araç hesabı gerektirmiyor", True,
                    "Yerel açık kaynak CLI temel arama için ücretli araç hesabı istemiyor.",
                ),
                _criterion(
                    "stable_json_results", "Sonuç için düzenli JSON/NDJSON", False,
                    "Mevcut --json seçeneği sonuç dışa aktarmak yerine site "
                    "veritabanı yükler; "
                    "tablo çıktısı olsa da seçilen JSON sözleşmesini karşılamaz.",
                ),
                _criterion(
                    "bounded_operation", "Site ve süre sınırı konabiliyor", True,
                    "Belirli siteler seçilebiliyor ve ağ zaman aşımı "
                    "sınırlandırılabiliyor.",
                ),
                _criterion(
                    "clear_code_license", "Açık kod lisansı", True,
                    "Ana depo MIT lisansını yayımlıyor.",
                ),
                _criterion(
                    "no_recovery_enumeration", "Hesap kurtarma mekanizması kullanmıyor", True,
                    "Genel profil adreslerinin varlık işaretlerini kontrol ediyor; "
                    "parola sıfırlama yok.",
                ),
                _criterion(
                    "current_scope_fit", "Mevcut marka kapsamına uyuyor", True,
                    "Kullanıcı adı araması marka taklidi incelemesine uyar.",
                ),
            ),
            blockers=(
                "Maigret ile aynı sitelere ikinci kez istek gönderip yinelenen "
                "sonuç üretebilir.",
                "İlk adaptör için gereken kararlı sonuç JSON sözleşmesi yok.",
            ),
            reference_urls=(
                "https://github.com/sherlock-project/sherlock",
            ),
        )
        theharvester = BrandSourceCandidate(
            identifier="theharvester-passive-only",
            label="theHarvester yalnız pasif kaynak profili",
            decision="selected_for_adapter",
            purpose="Common Crawl ve Wayback Archive üzerinden alt alan adı keşfi",
            integration_mode=(
                "Resmî depodaki sabit commit'ten ayrı süreç; yalnız iki P0 arşiv "
                "kaynağının doğrulanan JSONL sonucu"
            ),
            maintenance_risk="medium",
            criteria=(
                _criterion(
                    "verified_upstream", "Doğrulanmış ana depo", True,
                    "Ana proje laramies/theHarvester deposunda yayımlanıyor.",
                ),
                _criterion(
                    "maintained", "Etkin bakım", True,
                    "Açık depo değerlendirme tarihinde etkin geliştirme ve belge taşıyor.",
                ),
                _criterion(
                    "free_without_account", "Ücretsiz ve araç hesabı gerektirmiyor", True,
                    "Seçilen Common Crawl ve Wayback Archive kaynakları XTI "
                    "profilinde API anahtarı istemiyor.",
                ),
                _criterion(
                    "stable_json_results", "Sonuç için düzenli JSON/NDJSON", True,
                    "Güncel mimari satır bazlı JSON kanıt çıktısını belgeliyor.",
                ),
                _criterion(
                    "bounded_operation", "Site ve süre sınırı konabiliyor", True,
                    "Kaynaklar ve etkinlik sınıfı açıkça seçilebiliyor; P0 profili "
                    "ayrılabiliyor.",
                ),
                _criterion(
                    "clear_code_license", "Açık kod lisansı", True,
                    "Ana depo GPL-2.0-only lisansını yayımlıyor.",
                ),
                _criterion(
                    "no_recovery_enumeration", "Hesap kurtarma mekanizması kullanmıyor", True,
                    "Seçilecek P0 kaynak profili hesap kurtarma akışı kullanmaz.",
                ),
                _criterion(
                    "current_scope_fit", "Mevcut marka kapsamına uyuyor", True,
                    "Arşiv kaynakları mevcut sertifika kaynağından farklı pasif "
                    "alt alan adı kanıtı sağlayabilir.",
                ),
            ),
            blockers=(),
            reference_urls=(
                "https://github.com/laramies/theHarvester",
            ),
        )
        web_check = BrandSourceCandidate(
            identifier="web-check-whole-application",
            label="Web-Check uygulamasının tamamı",
            decision="rejected_overlap",
            purpose="Domain için geniş web, DNS, TLS, başlık ve ağ kontrolleri",
            integration_mode=(
                "Tam uygulama eklenmeyecek; yalnız eksik pasif fikirler ayrı "
                "incelenebilir"
            ),
            maintenance_risk="medium",
            criteria=(
                _criterion(
                    "verified_upstream", "Doğrulanmış ana depo", True,
                    "Ana proje Lissy93/web-check deposunda yayımlanıyor.",
                ),
                _criterion(
                    "maintained", "Etkin bakım", True,
                    "Açık depo değerlendirme tarihinde etkin.",
                ),
                _criterion(
                    "free_without_account", "Ücretsiz ve araç hesabı gerektirmiyor", True,
                    "Uygulama MIT lisansıyla yerel çalıştırılabiliyor; bazı dış "
                    "servisler ayrıca koşulludur.",
                ),
                _criterion(
                    "stable_json_results", "Sonuç için düzenli JSON/NDJSON", False,
                    "Ana teslim biçimi bir web uygulaması; XTI için dar, sürümlü "
                    "kayıt sözleşmesi değil.",
                ),
                _criterion(
                    "bounded_operation", "Site ve süre sınırı konabiliyor", False,
                    "Toplu görünüm port, rota, ekran görüntüsü ve dış servis "
                    "kontrollerini birleştiriyor.",
                ),
                _criterion(
                    "clear_code_license", "Açık kod lisansı", True,
                    "Ana depo MIT lisansını yayımlıyor.",
                ),
                _criterion(
                    "no_recovery_enumeration", "Hesap kurtarma mekanizması kullanmıyor", True,
                    "Hesap kurtarma aracı değildir; ancak bazı kontroller hedefe "
                    "doğrudan trafik üretir.",
                ),
                _criterion(
                    "current_scope_fit", "Mevcut marka kapsamına uyuyor", False,
                    "DNS, TLS ve web kanıtı XTI'da vardır; sosyal kullanıcı adı "
                    "kaynağı değildir.",
                ),
            ),
            blockers=(
                "Mevcut dış yüzey özelliklerini tekrarlar ve kullanıcı tarafından "
                "ertelenen web panelini getirir.",
                "Aktif kontroller XTI'ın açık yetki sınırlarından ayrı tutulmalıdır.",
            ),
            reference_urls=(
                "https://github.com/Lissy93/web-check",
            ),
        )
        holehe = BrandSourceCandidate(
            identifier="holehe-account-recovery",
            label="Holehe",
            decision="rejected_method",
            purpose=(
                "E-posta adresinin üçüncü taraf hizmetlerde kayıtlı olup "
                "olmadığını yoklama"
            ),
            integration_mode="Mevcut pasif OSINT profiline alınmayacak",
            maintenance_risk="high",
            criteria=(
                _criterion(
                    "verified_upstream", "Doğrulanmış ana depo", True,
                    "Ana proje megadose/holehe deposunda yayımlanıyor.",
                ),
                _criterion(
                    "maintained", "Etkin bakım", True,
                    "Depo erişilebilir; hizmet akışları sık değişebileceği için "
                    "bakım riski yüksektir.",
                ),
                _criterion(
                    "free_without_account", "Ücretsiz ve araç hesabı gerektirmiyor", True,
                    "Araç GPL-3.0 ile yerel çalıştırılabiliyor.",
                ),
                _criterion(
                    "stable_json_results", "Sonuç için düzenli JSON/NDJSON", False,
                    "XTI için sürümlü ve asgari bir sonuç sözleşmesi belgelenmiş "
                    "değildir.",
                ),
                _criterion(
                    "bounded_operation", "Site ve süre sınırı konabiliyor", False,
                    "Çok sayıda üçüncü taraf hesap akışını yoklayan davranış bu "
                    "dilime uygun değildir.",
                ),
                _criterion(
                    "clear_code_license", "Açık kod lisansı", True,
                    "Ana depo GPL-3.0 lisansını yayımlıyor.",
                ),
                _criterion(
                    "no_recovery_enumeration", "Hesap kurtarma mekanizması kullanmıyor", False,
                    "Temel yöntem üçüncü tarafların parola/hesap kurtarma "
                    "davranışlarından yararlanır.",
                ),
                _criterion(
                    "current_scope_fit", "Mevcut marka kapsamına uyuyor", False,
                    "E-posta hesap varlığı, sosyal marka kullanıcı adı taklidi değildir.",
                ),
            ),
            blockers=(
                "Bildirim, oran sınırı, hizmet koşulu ve kişisel veri etkisi doğurabilir.",
                "Otomatik veya toplu pasif marka izlemesi olarak sınıflandırılamaz.",
            ),
            reference_urls=(
                "https://github.com/megadose/holehe",
            ),
        )
        ignorant = BrandSourceCandidate(
            identifier="ignorant-phone-recovery",
            label="Ignorant (kastedilmiş olabilecek telefon aracı)",
            decision="rejected_method",
            purpose="Telefon numarasının üçüncü taraf hizmetlerde kullanımını yoklama",
            integration_mode=(
                "Kullanıcının söylediği Ignis doğrulanamadı; bu araç da "
                "eklenmeyecek"
            ),
            maintenance_risk="high",
            criteria=(
                _criterion(
                    "verified_upstream", "Doğrulanmış ana depo", True,
                    "Ignorant projesi megadose/ignorant deposunda yayımlanıyor; "
                    "Ignis ile aynı ad değildir.",
                ),
                _criterion(
                    "maintained", "Etkin bakım", False,
                    "Bu dilimde güncel ve kararlı bir entegrasyon sözleşmesi kanıtlanmadı.",
                ),
                _criterion(
                    "free_without_account", "Ücretsiz ve araç hesabı gerektirmiyor", True,
                    "Açık kaynak CLI yerel çalıştırılabiliyor.",
                ),
                _criterion(
                    "stable_json_results", "Sonuç için düzenli JSON/NDJSON", False,
                    "XTI için sürümlü ve asgari sonuç sözleşmesi sabitlenmedi.",
                ),
                _criterion(
                    "bounded_operation", "Site ve süre sınırı konabiliyor", False,
                    "Üçüncü taraf hesap akışlarını kullanan yöntem mevcut kapsam "
                    "için uygun değil.",
                ),
                _criterion(
                    "clear_code_license", "Açık kod lisansı", True,
                    "Ana depo GPL-3.0 lisansını yayımlıyor.",
                ),
                _criterion(
                    "no_recovery_enumeration", "Hesap kurtarma mekanizması kullanmıyor", False,
                    "Telefon hesabı varlığını hizmetlerin hesap/kurtarma "
                    "davranışlarıyla yoklar.",
                ),
                _criterion(
                    "current_scope_fit", "Mevcut marka kapsamına uyuyor", False,
                    "Telefon numarası istihbaratı CAP-068 sosyal marka dilimi değildir.",
                ),
            ),
            blockers=(
                "Ignis adıyla verilen kesin upstream adresi doğrulanmadı.",
                "Telefon numarası kişisel veridir ve yöntem pasif profil araması değildir.",
            ),
            reference_urls=(
                "https://github.com/megadose/ignorant",
            ),
        )
        return BrandSourceEvaluationReport(
            profile_version=PROFILE_VERSION,
            evaluated_at=EVALUATED_AT,
            required_criteria=REQUIRED,
            selected_identifier=maigret.identifier,
            selected_next_step=(
                "Seçili Maigret ve pasif theHarvester adaptörlerini mevcut yerel "
                "izleme akışlarında sınırlandırılmış biçimde işletme."
            ),
            candidates=(maigret, sherlock, theharvester, web_check, holehe, ignorant),
            notes=(
                "Bu rapor çalışma anında internete bağlanmaz, araç kurmaz ve veri "
                "klasörü oluşturmaz.",
                "Maigret seçimi aracın kodunu XTI'a kopyalamak değildir; ayrı ve "
                "isteğe bağlı adaptördür.",
                "theHarvester seçimi yalnız Common Crawl ve Wayback Archive hostname "
                "kanıtıdır; e-posta, DNS çözümleme ve aktif işlemler alınmaz.",
                "Tor/I2P, proxy, Cloudflare aşma, yapay zekâ, özyinelemeli kişi "
                "profilleme ve NSFW arama kapalı kalır.",
                "Aynı kullanıcı adına sahip profil, aynı kişi veya marka olduğuna "
                "kanıt değildir.",
                "Canlı adaptör yalnız kullanıcının açıkça verdiği marka kullanıcı "
                "adlarıyla ve insan incelemesi için çalışır.",
            ),
        )
