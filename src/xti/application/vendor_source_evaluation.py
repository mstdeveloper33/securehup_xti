"""Reproducible, offline gate for the next official producer source."""

from xti.domain.vendor_source_evaluation import (
    VendorSourceCandidate,
    VendorSourceCriterion,
    VendorSourceEvaluationReport,
)


PROFILE_VERSION = "official-vendor-source-gate-v1"
EVALUATED_AT = "2026-10-30"
REQUIRED = (
    "official_producer",
    "unauthenticated_free",
    "structured_format",
    "bounded_record_access",
    "product_release_context",
    "clear_reuse_terms",
)


def _criterion(key: str, label: str, passed: bool, evidence: str) -> VendorSourceCriterion:
    return VendorSourceCriterion(
        key=key, label=label, required=key in REQUIRED, passed=passed, evidence=evidence,
    )


class VendorSourceEvaluationService:
    def report(self) -> VendorSourceEvaluationReport:
        ubuntu = VendorSourceCandidate(
            identifier="canonical-ubuntu-osv",
            label="Canonical Ubuntu OSV",
            decision="selected",
            data_format="OSV JSON",
            access="Anahtarsız; bireysel dosya veya merkezi OSV API",
            granularity="UBUNTU-CVE kimliğiyle tek zafiyet kaydı",
            maintenance_risk="low",
            criteria=(
                _criterion("official_producer", "Üreticinin resmî verisi", True,
                           "Ubuntu Security Team veriyi Canonical kanallarında yayımlıyor."),
                _criterion("unauthenticated_free", "Ücretsiz ve kimlik doğrulamasız", True,
                           "Resmî belgede metadata, GitHub ve merkezi OSV erişimleri açık."),
                _criterion("structured_format", "Sürümlü makine biçimi", True,
                           "OSV JSON; Ubuntu alanlarının anlamı resmî belgede açıklanıyor."),
                _criterion("bounded_record_access", "Tek kayıtla sınırlı erişim", True,
                           "Depoda her UBUNTU-CVE için bireysel OSV dosyası bulunuyor."),
                _criterion("product_release_context", "Ürün ve sürüm bağlamı", True,
                           "Ubuntu ekosistemi, kaynak paket, sürüm ve düzeltme olayı taşınıyor."),
                _criterion("clear_reuse_terms", "Açık yeniden kullanım koşulu", True,
                           "Resmî veri deposu CC-BY-SA-4.0 lisansını yayımlıyor."),
            ),
            blockers=(),
            reference_urls=(
                "https://documentation.ubuntu.com/security/security-updates/osv/",
                "https://github.com/canonical/ubuntu-security-notices",
            ),
        )
        microsoft = VendorSourceCandidate(
            identifier="microsoft-msrc-cvrf",
            label="Microsoft MSRC Security Update Guide CVRF",
            decision="deferred",
            data_format="CVRF JSON",
            access="Anahtarsız resmî API",
            granularity="Yayın/dönem belgesi; tek CVE için ek seçim gerekiyor",
            maintenance_risk="medium",
            criteria=(
                _criterion("official_producer", "Üreticinin resmî verisi", True,
                           "MSRC, Security Update Guide verisini yayımlıyor."),
                _criterion("unauthenticated_free", "Ücretsiz ve kimlik doğrulamasız", True,
                           "MSRC, CVRF API anahtar zorunluluğunu kaldırdığını bildiriyor."),
                _criterion("structured_format", "Sürümlü makine biçimi", True,
                           "Security Update Guide CVRF biçimi kullanıyor."),
                _criterion("bounded_record_access", "Tek kayıtla sınırlı erişim", False,
                           "Temel veri birimi yayın belgesi; tek CVE çağrısı henüz kanıtlanmadı."),
                _criterion("product_release_context", "Ürün ve sürüm bağlamı", True,
                           "Etkilenen Microsoft ürün ve düzeltme bağları yayımlanıyor."),
                _criterion("clear_reuse_terms", "Açık yeniden kullanım koşulu", False,
                           "Bu dilimde makine verisinin yeniden kullanım koşulu sabitlenmedi."),
            ),
            blockers=(
                "Tek-CVE ve küçük yanıt yolu doğrulanmalı.",
                "Yeniden kullanım ve saklama koşulları karar kaydına sabitlenmeli.",
            ),
            reference_urls=(
                "https://www.microsoft.com/en-us/msrc/blog/2021/02/continuing-to-listen-good-news-about-the-security-update-guide-api",
                "https://msrc.microsoft.com/update-guide/",
            ),
        )
        debian = VendorSourceCandidate(
            identifier="debian-security-tracker",
            label="Debian Security Tracker",
            decision="deferred",
            data_format="Debian JSON",
            access="Anahtarsız resmî toplu JSON",
            granularity="Toplu veri; web araması tek CVE fakat makine JSON'u toplu",
            maintenance_risk="medium",
            criteria=(
                _criterion("official_producer", "Üreticinin resmî verisi", True,
                           "Veri Debian Security Team veritabanından türetiliyor."),
                _criterion("unauthenticated_free", "Ücretsiz ve kimlik doğrulamasız", True,
                           "Tracker ve JSON dış arayüzü açık erişilebilir."),
                _criterion("structured_format", "Sürümlü makine biçimi", True,
                           "Tracker bütün bilgiyi JSON olarak sunuyor."),
                _criterion("bounded_record_access", "Tek kayıtla sınırlı erişim", False,
                           "Belgelenen makine arayüzü bütün veri kümesini sunuyor."),
                _criterion("product_release_context", "Ürün ve sürüm bağlamı", True,
                           "Debian paketleri, yayınlar ve durumlar izleniyor."),
                _criterion("clear_reuse_terms", "Açık yeniden kullanım koşulu", False,
                           "Bu dilimde JSON yeniden kullanım koşulu sabitlenmedi."),
            ),
            blockers=(
                "Kişisel kullanım için toplu dosya boyutu ve değişiklik alma politikası ölçülmeli.",
                "Tek-CVE makine erişimi veya güvenli yerel indeks planı gerekli.",
            ),
            reference_urls=("https://security-tracker.debian.org/tracker/",),
        )
        cisco = VendorSourceCandidate(
            identifier="cisco-openvuln",
            label="Cisco PSIRT openVuln API",
            decision="rejected_for_free_profile",
            data_format="REST JSON",
            access="Cisco hesabı, uygulama kaydı, istemci sırrı ve OAuth belirteci",
            granularity="Tek CVE/advisory uç noktaları",
            maintenance_risk="medium",
            criteria=(
                _criterion("official_producer", "Üreticinin resmî verisi", True,
                           "Cisco PSIRT resmî openVuln API'sidir."),
                _criterion("unauthenticated_free", "Ücretsiz ve kimlik doğrulamasız", False,
                           "Her istek erişim belirteci; uygulama kaydı ve istemci sırrı istiyor."),
                _criterion("structured_format", "Sürümlü makine biçimi", True,
                           "Sürümlü REST/OpenAPI biçimi yayımlanıyor."),
                _criterion("bounded_record_access", "Tek kayıtla sınırlı erişim", True,
                           "CVE ve advisory uç noktaları mevcut."),
                _criterion("product_release_context", "Ürün ve sürüm bağlamı", True,
                           "Cisco advisory ve ürün adları sağlanıyor."),
                _criterion("clear_reuse_terms", "Açık yeniden kullanım koşulu", True,
                           "API şartları resmî belgede bağlantılıdır."),
            ),
            blockers=("Ücretsiz kişisel profil kimlik bilgisi ve sır yönetimi kabul etmiyor.",),
            reference_urls=(
                "https://developer.cisco.com/docs/psirt/authentication/",
                "https://developer.cisco.com/docs/psirt/overview/",
            ),
        )
        return VendorSourceEvaluationReport(
            profile_version=PROFILE_VERSION,
            evaluated_at=EVALUATED_AT,
            required_criteria=REQUIRED,
            selected_identifier=ubuntu.identifier,
            selected_next_step=(
                "Canonical Ubuntu OSV için tek UBUNTU-CVE kaydını alan, yazmayan ve "
                "sınırları doğrulanan önizleme adaptörü."
            ),
            candidates=(ubuntu, microsoft, debian, cisco),
            notes=(
                "Bu rapor çalışma anında internete bağlanmaz; kanıt bağlantıları sürümlü kararı açıklar.",
                "Seçilmek kaynak eşdeğerliği veya yerel Ubuntu maruziyeti anlamına gelmez.",
                "Kimlik bilgisi isteyen kaynaklar ücretsiz-anahtarsız kişisel profile eklenmez.",
            ),
        )
