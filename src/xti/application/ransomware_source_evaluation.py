"""Reproducible, offline gate for an additional public ransomware source."""

from xti.domain.ransomware_source_evaluation import (
    RansomwareSourceCandidate,
    RansomwareSourceCriterion,
    RansomwareSourceEvaluationReport,
)


PROFILE_VERSION = "public-ransomware-source-gate-v1"
EVALUATED_AT = "2026-10-30"
REQUIRED = (
    "maintained",
    "unauthenticated_free",
    "structured_bounded",
    "clear_reuse_terms",
    "independent_collection",
    "safe_minimal_content",
)


def _criterion(
    key: str, label: str, passed: bool, evidence: str,
) -> RansomwareSourceCriterion:
    return RansomwareSourceCriterion(
        key=key, label=label, required=key in REQUIRED, passed=passed,
        evidence=evidence,
    )


class RansomwareSourceEvaluationService:
    def report(self) -> RansomwareSourceEvaluationReport:
        ransomlook = RansomwareSourceCandidate(
            identifier="ransomlook-public-posts",
            label="RansomLook public posts API",
            decision="selected",
            data_format="Sınırlı bir gönderi listesi içeren JSON nesnesi",
            access="Açık HTTPS okuma uç noktası; son gönderiler için anahtar yok",
            collection=(
                "Açık kaynak tarayıcı ve gruba özel ayrıştırıcılar ransomware grup "
                "sitelerini izliyor"
            ),
            maintenance_risk="medium",
            criteria=(
                _criterion(
                    "maintained", "Etkin bakım", True,
                    "Açık depo ve 2.x sürüm hattı değerlendirme tarihinde etkindi.",
                ),
                _criterion(
                    "unauthenticated_free", "Ücretsiz ve anahtarsız okuma", True,
                    "Resmî belgeye göre okuma uç noktalarının çoğu açık; yalnız toplu "
                    "dışa aktarma anahtar istiyor.",
                ),
                _criterion(
                    "structured_bounded", "Yapılandırılmış ve dar çağrı", True,
                    "Sabit gönderi uç noktası yedi günlük pencere kabul ediyor ve asgari "
                    "JSON kayıtları döndürüyor.",
                ),
                _criterion(
                    "clear_reuse_terms", "Açık yeniden kullanım koşulu", True,
                    "Resmî belge web sitesi, API yanıtları ve veri kümelerini CC BY 4.0 "
                    "ile lisanslıyor.",
                ),
                _criterion(
                    "independent_collection", "Bağımsız toplama hattı", True,
                    "RansomLook kendi Tor tarama ve gruba özel ayrıştırma hattını belgeliyor.",
                ),
                _criterion(
                    "safe_minimal_content", "Güvenli asgari içerik", True,
                    "Seçilen uç nokta grup, gönderi başlığı ve keşif zamanı döndürüyor; "
                    "çalınmış dosya veya ham sayfa gövdesi içermiyor.",
                ),
            ),
            blockers=(),
            reference_urls=(
                "https://github.com/RansomLook/RansomLook",
                "https://www.ransomlook.io/doc/",
                "https://github.com/RansomLook/RansomLook/releases",
            ),
        )
        ransomwatch = RansomwareSourceCandidate(
            identifier="ransomwatch-archive",
            label="RansomWatch public JSON archive",
            decision="rejected_for_current_feed",
            data_format="Üretilmiş JSON dosyaları",
            access="Açık GitHub dosyaları; anahtar yok",
            collection="Geçmişte doğrudan leak-site tarama ve ayrıştırma",
            maintenance_risk="high",
            criteria=(
                _criterion(
                    "maintained", "Etkin bakım", False,
                    "Sahibi depoyu 3 Mart 2026'da arşivledi ve salt okunur yaptı.",
                ),
                _criterion(
                    "unauthenticated_free", "Ücretsiz ve anahtarsız okuma", True,
                    "Üretilmiş gönderi ve grup dosyaları açık biçimde okunabiliyor.",
                ),
                _criterion(
                    "structured_bounded", "Yapılandırılmış ve dar çağrı", False,
                    "Yayımlanan dosya sınırlı güncel uç nokta yerine üretilmiş tam veri "
                    "kümesidir.",
                ),
                _criterion(
                    "clear_reuse_terms", "Açık yeniden kullanım koşulu", True,
                    "Depo Unlicense ile yayımlanmıştır.",
                ),
                _criterion(
                    "independent_collection", "Bağımsız toplama hattı", True,
                    "Proje izlenen adreslere doğrudan ziyaretleri ve ayrıştırıcı çıktısını "
                    "belgelemiştir.",
                ),
                _criterion(
                    "safe_minimal_content", "Güvenli asgari içerik", False,
                    "Tam veri kümesi uzak gönderi adresleri ve XTI'ın ihtiyaç duymadığı "
                    "başka alanlar içerebilir.",
                ),
            ),
            blockers=(
                "Arşivlenmiş veri güvenilir ve güncel ikinci kaynak sağlayamaz.",
                "Tam veri kümesi dosyası ilk kişisel kullanım entegrasyonu için gereksizdir.",
            ),
            reference_urls=("https://github.com/joshhighet/ransomwatch",),
        )
        darkfield = RansomwareSourceCandidate(
            identifier="darkfield-observer",
            label="Darkfield public observatory",
            decision="deferred",
            data_format="Açık sayfalar ile JSON, REST, RSS, CSV ve STIX arayüzleri",
            access="Açık gezinme; geniş API ücretsiz Observer anahtarı ve günlük kota kullanıyor",
            collection="Kendi Tor taraması ile birden çok açık toplayıcının birleşimi",
            maintenance_risk="medium",
            criteria=(
                _criterion(
                    "maintained", "Etkin bakım", True,
                    "Gözlemevi güncel yöntem ve veri hattı sağlık açıklamalarını yayımlıyor.",
                ),
                _criterion(
                    "unauthenticated_free", "Ücretsiz ve anahtarsız okuma", False,
                    "Açık gezinme anahtarsız; belgelenen geniş API ise Observer anahtarı "
                    "ve kota kullanıyor.",
                ),
                _criterion(
                    "structured_bounded", "Yapılandırılmış ve dar çağrı", False,
                    "Bu değerlendirmede kararlı, anahtarsız ve güncel kayıt sözleşmesi "
                    "sabitlenemedi.",
                ),
                _criterion(
                    "clear_reuse_terms", "Açık yeniden kullanım koşulu", True,
                    "İşletmeci, atıfla ticari API/akış kullanımına izin verildiğini belirtiyor.",
                ),
                _criterion(
                    "independent_collection", "Bağımsız toplama hattı", False,
                    "Yöntem kendi taramasını RansomLook, RansomWatch ve ransomware.live "
                    "ile birleştiriyor.",
                ),
                _criterion(
                    "safe_minimal_content", "Güvenli asgari içerik", False,
                    "Daha geniş veri kümesi bu dilimin dışındaki kimlik bilgileri, Telegram "
                    "ve ham kanıtları da kapsıyor.",
                ),
            ),
            blockers=(
                "Önce asgari uç nokta, kesin şema ve kimlik doğrulama politikası sabitlenmeli.",
                "Bu kaynak ileride eklenirse üst kaynak çakışması görünür kalmalı.",
            ),
            reference_urls=(
                "https://darkfield.orizon.one/about",
                "https://darkfield.orizon.one/methodology",
                "https://darkfield.orizon.one/pricing",
            ),
        )
        return RansomwareSourceEvaluationReport(
            profile_version=PROFILE_VERSION,
            evaluated_at=EVALUATED_AT,
            required_criteria=REQUIRED,
            selected_identifier=ransomlook.identifier,
            selected_next_step=(
                "Sıkı, salt okunur ve yedi günlük RansomLook önizlemesini kullan; "
                "kayıtlarını ve kaynak anlamını ThreatCluster kalıcılığından ayrı tut."
            ),
            candidates=(ransomlook, ransomwatch, darkfield),
            notes=(
                "Bu rapor çalışma anında çevrimdışıdır; adresleri sürümlü kararı belgeler.",
                "Kaynağın seçilmesi, işletmeci iddialarını doğrulanmış ihlal yapmaz.",
                "Seçilen hiçbir kaynak XTI'ın çalınmış veri indirmesine veya leak-site'lara "
                "bağlanmasına izin vermez.",
            ),
        )
