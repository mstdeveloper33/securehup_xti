"""Explicit tool inventory using reviewed pins and existing selection policies."""

from collections.abc import Callable
from datetime import datetime, timezone

from xti.application.brand_username import (
    DEFAULT_PLATFORMS, EXTENDED_PLATFORMS,
    SHERLOCK_DEFAULT_PLATFORMS, SHERLOCK_EXTENDED_PLATFORMS,
)
from xti.domain.assets import ValidationError
from xti.domain.component_pins import REVIEWED_COMPONENT_PINS
from xti.domain.components import (
    COMPONENT_CATALOG_VERSION, COMPONENT_INSTALLATION_STATES, ComponentInstallation,
)
from xti.ports.components import ComponentInstallationInspector


def _configuration(identifier: str) -> dict:
    if identifier == 'betterleaks':
        from xti.domain.betterleaks_pin import ARCHIVES
        return {'kind': 'offline_secret_candidates', 'validation': False, 'automatic_repository_config': False,
                'redaction_percent': 100, 'max_file_bytes': 262144, 'archive_sha256': ARCHIVES}
    if identifier in {'maigret', 'sherlock'}:
        safe, extended = ((DEFAULT_PLATFORMS, EXTENDED_PLATFORMS) if identifier == 'maigret'
                          else (SHERLOCK_DEFAULT_PLATFORMS, SHERLOCK_EXTENDED_PLATFORMS))
        return {
            'kind': 'public_username_lookup', 'default_profile': 'safe',
            'selection_profiles': [
                {'name': 'safe', 'platforms': list(safe)},
                {'name': 'extended', 'platforms': list(extended)},
            ],
            'custom_selection': 'subset_of_extended',
            'request_timeout_seconds': {'default': 10, 'minimum': 5, 'maximum': 30},
        }
    if identifier == 'theharvester':
        return {
            'kind': 'passive_archive_discovery', 'sources': ['commoncrawl', 'waybackarchive'],
            'result_limit': {'default': 250, 'maximum': 500},
            'active_target_checks': False,
        }
    raise ValidationError('Bileşen için açık engine yapılandırma kapsamı tanımlanmamış.')


class ComponentCatalogService:
    def __init__(self, inspector: ComponentInstallationInspector, *,
                 clock: Callable[[], datetime] | None = None):
        self.inspector = inspector
        self.clock = clock or (lambda: datetime.now(timezone.utc))

    def list(self) -> dict:
        now = self.clock()
        if not isinstance(now, datetime) or now.tzinfo is None or now.utcoffset() is None:
            raise ValidationError('Bileşen denetimi saat dilimli zaman gerektirir.')
        rows = []
        for pin in REVIEWED_COMPONENT_PINS:
            configuration = _configuration(pin.identifier)
            installation = self.inspector.inspect(pin.identifier)
            if (not isinstance(installation, ComponentInstallation)
                    or installation.state not in COMPONENT_INSTALLATION_STATES
                    or (installation.error is not None and not isinstance(installation.error, str))):
                raise ValidationError('Bileşen kurulum gözlemi beklenen yapıda değil.')
            archive = pin.identifier == 'theharvester'
            rows.append({
                'identifier': pin.identifier, 'label': pin.label,
                'purpose': ('Kod/paste metninde maskeli hassas bilgi adayı; anahtarları kullanmadan inceleme.' if pin.identifier == 'betterleaks' else 'Arşivlerde kayıtlı kökün alt alan adı adaylarını toplama.' if archive
                            else 'Seçilen platformlarda herkese açık kullanıcı adı profili adaylarını araştırma.'),
                'expected': {
                    'version': pin.version, 'commit': pin.commit, 'repository': pin.repository,
                    'distribution': pin.distribution, 'package': pin.package,
                    'integration_profile': pin.integration_profile,
                    'catalog_sha256': pin.catalog_sha256, 'catalog_size': pin.catalog_size,
                },
                'license': {'spdx': pin.license_spdx, 'reference_url': pin.license_reference_url},
                'runtime': {'python_requirement': pin.python_requirement, 'deployment': pin.deployment},
                'configuration': configuration,
                'setup_command': list(pin.setup_command), 'verify_command': list(pin.verify_command),
                'source_status_ids': [] if pin.identifier == 'betterleaks' else ['surface:theharvester'] if archive else [f'social:{pin.identifier}'],
                'installation': {
                    'state': installation.state, 'error': installation.error,
                    'scope': 'project-managed', 'verification': 'metadata_only', 'execution_tested': False,
                    'inspection_checks': (['installation_journal_and_lock', 'checkout_head_marker', 'launcher_and_interpreter_location'] if archive
                                      else ['installation_journal_and_lock', 'distribution_version', 'vcs_metadata', 'catalog_hash_and_size', 'launcher_files']),
                },
                'notes': ([
                    'theHarvester denetimi HEAD işareti ve çalıştırıcı konumunu okur; tüm çalışma ağacı veya bağımlılık bütünlüğünü kanıtlamaz.',
                    'Ayrı setup-harvester --check, yerel Git kimliği ve --help çalışmasını denetler; bütün bağımlılıkların bütünlüğünü kanıtlamaz.',
                ] if archive else [
                    'Yalnız proje .venv kurulum bilgileri denetlenir; bütün geçişli bağımlılıklar veya çalışma başarısı bu okumada sınanmaz.',
                    'XTI_PYTHON veya PATH ile seçilmiş başka çalışma ortamı bu gözlemle doğrulanmış sayılmaz.',
                ]) + [
                    'Araç eksik veya geçersiz olsa da daha önce kaydedilmiş kanıtlar silinmez ve okunabilir.',
                    'Kurulum durumu canlı kaynak erişimi değildir; geçmiş çalışma/güncellik için sources.status kullanılır.',
                ],
            })
        return {
            'catalog_version': COMPONENT_CATALOG_VERSION,
            'observed_at': now.astimezone(timezone.utc).isoformat(),
            'scope': 'project-managed-tools', 'components': rows,
            'notes': [
                'Yönetilen keşif araçları ve secret dedektörü; P03 görsel/mağaza kitaplıkları brand protection capabilities altında ayrıca listelenir. Tüm geçişli paketlerin envanteri değildir.',
                "Sistem Nmap kurulumu 'surface nmap readiness' ile doğrulanır; hedef/plan/işler 'surface nmap targets/plans/jobs', seçenek kataloğu 'surface nmap capabilities' altında yönetilir.",
                'Beklenen pinler gözlenen sürüm gibi sunulmaz; kurulum denetimi araç çalıştırmaz, indirme veya internet sorgusu yapmaz.',
                'Denetimler bağımsız yerel okumalardır; eşzamanlı kurulum sırasında ortak kesit garantisi yoktur.',
                'Bu görünüm ayar değiştirmez veya kurulum başlatmaz; komutlar yalnız işleticiye yol gösterir.',
            ],
        }
