"""Human-readable managed component inventory and its composition entry point."""

import shlex

from xti.adapters.components import ManagedComponentInstallationInspector
from xti.application.components import ComponentCatalogService
from xti.interfaces.text import safe_text


def make_component_service() -> ComponentCatalogService:
    return ComponentCatalogService(ManagedComponentInstallationInspector())


def register_components_parser(commands):
    commands.add_parser('components', help='Bağlı açık kaynak araçların pin, kapsam ve yerel kurulum bilgilerini göster.')


def component_lines(report: dict) -> list[str]:
    states = {'ready': 'Kurulum bilgileri uyumlu', 'missing': 'Kurulu değil', 'invalid': 'Kurulum bilgileri geçersiz'}
    lines = ['Engine açık kaynak araçları', 'Yerel kurulum denetimi; canlı kaynak erişimi veya çalışma testi değildir.']
    for item in report['components']:
        pin, installation = item['expected'], item['installation']
        lines.extend(('', f"{safe_text(item['label'])} | {states[installation['state']]}",
                      f"  Görev: {safe_text(item['purpose'])}",
                      f"  Beklenen sürüm: {safe_text(pin['version'] or 'commit ile sabit')} | commit: {safe_text(pin['commit'])}",
                      f"  Bağlantı profili: {safe_text(pin['integration_profile'])}",
                      f"  Lisans: {safe_text(item['license']['spdx'])} | Python: {safe_text(item['runtime']['python_requirement'])}"))
        configuration = item['configuration']
        if configuration['kind'] == 'public_username_lookup':
            lines.append('  Platformlar: ' + ', '.join(
                f"{safe_text(profile['name'])}={len(profile['platforms'])}" for profile in configuration['selection_profiles']))
        else:
            lines.append('  Kaynaklar: ' + ', '.join(safe_text(source) for source in configuration['sources']))
        if installation['error']:
            lines.append('  Denetim açıklaması: ' + safe_text(installation['error']))
        lines.append('  Kurulum: ' + safe_text(shlex.join(item['setup_command'])))
        if item['verify_command']:
            lines.append('  Ayrı doğrulama: ' + safe_text(shlex.join(item['verify_command'])))
        lines.extend('  ' + safe_text(note) for note in item['notes'])
    lines.extend(safe_text(note) for note in report['notes'])
    return lines
