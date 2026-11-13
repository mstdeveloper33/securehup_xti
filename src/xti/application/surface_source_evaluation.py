"""Reproducible offline gate for passive surface-discovery adapters."""

from xti.domain.surface import SURFACE_DISCOVERY_PROVIDERS
from xti.domain.surface_source_evaluation import (
    SurfaceSourceCandidate,
    SurfaceSourceCriterion,
    SurfaceSourceEvaluationReport,
)


PROFILE_VERSION = "passive-surface-source-gate-v4"
EVALUATED_AT = "2026-11-13"
REQUIRED = (
    "verified_upstream",
    "reviewed_access_or_license",
    "free_selected_profile",
    "passive_no_target_contact",
    "bounded_execution",
    "strict_machine_contract",
    "source_outcome_separation",
    "independent_coverage",
    "maintainable_installation",
)


def _criterion(
    key: str, label: str, passed: bool, evidence: str,
) -> SurfaceSourceCriterion:
    return SurfaceSourceCriterion(
        key=key,
        label=label,
        required=key in REQUIRED,
        passed=passed,
        evidence=evidence,
    )


def _validate_candidates(candidates: tuple[SurfaceSourceCandidate, ...]) -> None:
    """Fail closed when a source decision omits or duplicates a gate."""
    required = set(REQUIRED)
    for candidate in candidates:
        keys = tuple(criterion.key for criterion in candidate.criteria)
        if len(keys) != len(set(keys)):
            raise ValueError(
                f"{candidate.identifier} kaynak değerlendirmesinde yinelenen ölçüt var."
            )
        if set(keys) != required:
            raise ValueError(
                f"{candidate.identifier} kaynak değerlendirmesi zorunlu ölçütlerle uyuşmuyor."
            )
        if any(not criterion.required for criterion in candidate.criteria):
            raise ValueError(
                f"{candidate.identifier} zorunlu ölçütü isteğe bağlı işaretlenmiş."
            )
        if candidate.decision == "active" and any(
            not criterion.passed for criterion in candidate.criteria
        ):
            raise ValueError(
                f"{candidate.identifier} tüm zorunlu ölçütleri geçmeden etkinleştirilemez."
            )


class SurfaceSourceEvaluationService:
    def report(self) -> SurfaceSourceEvaluationReport:
        crtsh = SurfaceSourceCandidate(
            identifier="crt.sh",
            label="crt.sh doğrudan adaptörü",
            decision="active",
            purpose="Sertifika Şeffaflığı kayıtlarından alt alan adı adayı bulmak.",
            integration_mode=(
                "XTI içindeki sınırlı HTTPS istemcisi; haricî süreç veya indirilen kod yok."
            ),
            upstream_version="public-json-contract-2026-11-13",
            maintenance_risk="low",
            criteria=(
                _criterion(
                    "verified_upstream", "Doğrulanmış kaynak", True,
                    "Doğrudan crt.sh JSON araması kullanılıyor.",
                ),
                _criterion(
                    "reviewed_access_or_license", "Erişim veya dağıtım koşulu incelendi", True,
                    "XTI hizmeti sorguluyor; üçüncü taraf kaynak kodunu dağıtmıyor.",
                ),
                _criterion(
                    "free_selected_profile", "Seçilen profil ücretsiz", True,
                    "Kişisel profil API anahtarı veya ücretli hesap istemiyor.",
                ),
                _criterion(
                    "passive_no_target_contact", "İzlenen hedefe bağlanmıyor", True,
                    "Yalnız yayımlanmış sertifika arşivi sorgulanıyor.",
                ),
                _criterion(
                    "bounded_execution", "Süre ve yanıt sınırları var", True,
                    "İstek süresi, yanıt boyutu ve kayıt sayısı XTI tarafından sınırlandırılıyor.",
                ),
                _criterion(
                    "strict_machine_contract", "Katı makine sözleşmesi var", True,
                    "JSON alanları ve domain kapsamı kabul edilmeden önce doğrulanıyor.",
                ),
                _criterion(
                    "source_outcome_separation", "Tamamlanma ve hata ayrılıyor", True,
                    "Tek kaynak HTTP/ayrıştırma hatası boş sonuç olarak kaydedilmiyor.",
                ),
                _criterion(
                    "independent_coverage", "Ayrı veri katkısı var", True,
                    "Sertifika kayıtları pasif keşfin temel ve ayrı kanıt ailesidir.",
                ),
                _criterion(
                    "maintainable_installation", "Kurulum sürdürülebilir", True,
                    "Çekirdek Python adaptörü dışında haricî araç kurulumu gerekmiyor.",
                ),
            ),
            blockers=(),
            reference_urls=("https://crt.sh/",),
        )
        theharvester = SurfaceSourceCandidate(
            identifier="theharvester",
            label="theHarvester sınırlı arşiv adaptörü",
            decision="active",
            purpose="Common Crawl ve Wayback Archive kayıtlarından alt alan adı adayı bulmak.",
            integration_mode=(
                "Tam commit'e sabit ayrı ortam; upstream ayrıştırma yardımcıları, "
                "XTI arşiv v3 bağlantı işçisi ve doğrulanan JSONL."
            ),
            upstream_version="commit 6790b147f52309e4eee22ed941db1d285ab2ec23",
            maintenance_risk="medium",
            criteria=(
                _criterion(
                    "verified_upstream", "Doğrulanmış kaynak", True,
                    "Resmî laramies/theHarvester deposundaki tam commit sabitlenmiştir.",
                ),
                _criterion(
                    "reviewed_access_or_license", "Erişim veya dağıtım koşulu incelendi", True,
                    "GPL-2.0-only araç ayrı ortamda tutulur; kodu XTI çekirdeğine kopyalanmaz.",
                ),
                _criterion(
                    "free_selected_profile", "Seçilen profil ücretsiz", True,
                    "Common Crawl ve Wayback Archive P0 profili hesap veya ücretli anahtar istemez.",
                ),
                _criterion(
                    "passive_no_target_contact", "İzlenen hedefe bağlanmıyor", True,
                    "DNS, e-posta, screenshot, takeover ve aktif hedef işlemleri kapalıdır.",
                ),
                _criterion(
                    "bounded_execution", "Süre ve yanıt sınırları var", True,
                    "İki sabit sağlayıcı seri çalışır; Common Crawl 150, Wayback 90 saniye; "
                    "kaynak başına 30 istek, 250 hostname sınırı ve kısmi kapsam "
                    "bildirimi kullanılır.",
                ),
                _criterion(
                    "strict_machine_contract", "Katı makine sözleşmesi var", True,
                    "Alan kümesi, tür, sayaç, UTC zaman ve kök kapsamı doğrulanır.",
                ),
                _criterion(
                    "source_outcome_separation", "Tamamlanma ve hata ayrılıyor", True,
                    "İki arşivin durum ve sayaçları JSONL raporunda ayrı taşınır.",
                ),
                _criterion(
                    "independent_coverage", "Ayrı veri katkısı var", True,
                    "Geçmiş web arşivleri crt.sh sertifika ailesinden farklı kanıt sağlar.",
                ),
                _criterion(
                    "maintainable_installation", "Kurulum sürdürülebilir", True,
                    "Commit sabit ayrı kurulum ve doğrulama betiği çekirdekten yalıtılmıştır.",
                ),
            ),
            blockers=(),
            reference_urls=(
                "https://github.com/laramies/theHarvester",
                "https://github.com/laramies/theHarvester/tree/6790b147f52309e4eee22ed941db1d285ab2ec23",
            ),
        )
        subfinder = SurfaceSourceCandidate(
            identifier="subfinder-cli-v2.17.0",
            label="ProjectDiscovery Subfinder CLI v2.17.0",
            decision="deferred_contract",
            purpose="Birden fazla pasif sağlayıcıdan alt alan adı adayı toplamak.",
            integration_mode=(
                "Normal CLI entegrasyonu ertelendi; gerekirse typed Go bridge ayrı "
                "bir kararla değerlendirilecek."
            ),
            upstream_version="v2.17.0 / c97f25802892093060f0fc424bfc3f39e273693a",
            maintenance_risk="medium",
            criteria=(
                _criterion(
                    "verified_upstream", "Doğrulanmış kaynak", True,
                    "Resmî ProjectDiscovery sürümü ve commit'i incelendi.",
                ),
                _criterion(
                    "reviewed_access_or_license", "Erişim veya dağıtım koşulu incelendi", True,
                    "Kod MIT lisanslıdır; her veri sağlayıcısının koşulu ayrıca incelenmelidir.",
                ),
                _criterion(
                    "free_selected_profile", "Seçilen profil ücretsiz", False,
                    "Yeni kapsam sağlayan, koşulları incelenmiş sabit anahtarsız profil seçilmedi.",
                ),
                _criterion(
                    "passive_no_target_contact", "İzlenen hedefe bağlanmıyor", True,
                    "Aktif çözümleme bayrakları kapatılarak pasif kullanım mümkündür.",
                ),
                _criterion(
                    "bounded_execution", "Süre ve yanıt sınırları var", True,
                    "CLI süre, sonuç, okuma boyutu ve hız sınırları sunar.",
                ),
                _criterion(
                    "strict_machine_contract", "Katı makine sözleşmesi var", False,
                    "JSONL yalnız bulunan hostları taşır; kaynak tamamlanma ve hata kaydı içermez.",
                ),
                _criterion(
                    "source_outcome_separation", "Tamamlanma ve hata ayrılıyor", False,
                    "Kaynak hataları warning'e çevrilip süreç başarılı bitebildiği için boş sonuç "
                    "ile kaynak hatası güvenilir biçimde ayrılamaz.",
                ),
                _criterion(
                    "independent_coverage", "Ayrı veri katkısı var", False,
                    "Anahtarsız anlamlı profil mevcut crt.sh ve Common Crawl/Wayback kapsamından "
                    "bağımsız katkı göstermedi.",
                ),
                _criterion(
                    "maintainable_installation", "Kurulum sürdürülebilir", True,
                    "Sürüm ve platforma sabit resmî binary dağıtımı teknik olarak mümkündür.",
                ),
            ),
            blockers=(
                "Normal CLI, kaynak hatasını makine-okunur sonuç akışında korumuyor.",
                "Mevcut ücretsiz kaynaklara göre yeni ve ölçülmüş kapsam katkısı yok.",
            ),
            reference_urls=(
                "https://github.com/projectdiscovery/subfinder/releases/tag/v2.17.0",
                "https://github.com/projectdiscovery/subfinder/blob/v2.17.0/pkg/runner/enumerate.go",
                "https://github.com/projectdiscovery/subfinder/blob/v2.17.0/pkg/runner/outputter.go",
                "https://github.com/projectdiscovery/subfinder/blob/v2.17.0/LICENSE.md",
                "https://github.com/projectdiscovery/subfinder/blob/v2.17.0/DISCLAIMER.md",
            ),
        )
        candidates = (crtsh, theharvester, subfinder)
        _validate_candidates(candidates)
        active = tuple(item.identifier for item in candidates if item.decision == "active")
        if active != SURFACE_DISCOVERY_PROVIDERS:
            raise ValueError("Aktif pasif kaynak kapısı çalışma sağlayıcılarıyla uyuşmuyor.")
        return SurfaceSourceEvaluationReport(
            profile_version=PROFILE_VERSION,
            evaluated_at=EVALUATED_AT,
            required_criteria=REQUIRED,
            active_identifiers=active,
            next_step=(
                "Gerçek kullanımda sağlayıcı bazlı kapsam ve hata durumunu ölç; yeni araç ancak "
                "bağımsız katkı ve katı hata sözleşmesi kanıtıyla eklenebilir."
            ),
            candidates=candidates,
            notes=(
                "Bu rapor sürümlü kabul kararıdır; kaynakların şu an erişilebilir olduğunu ölçmez.",
                "Ücretsiz olmak tek başına kabul nedeni değildir.",
                "Ertelenen araç kurulmaz, çalıştırılmaz ve XTI ile dağıtılmaz.",
            ),
        )
