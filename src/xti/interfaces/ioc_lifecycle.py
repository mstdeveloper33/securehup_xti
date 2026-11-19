"""CLI projection and composition for the shared IOC lifecycle operation."""

from xti.domain.cti_indicators import INDICATOR_TYPES
from xti.interfaces.text import safe_text


def make_ioc_lifecycle_service(database):
    from xti.adapters.sqlite_ioc_lifecycle import SQLiteIocLifecycleRepository
    from xti.application.ioc_lifecycle import IocLifecycleService
    return IocLifecycleService(SQLiteIocLifecycleRepository(database))


def register_ioc_lifecycle_parser(actions):
    parser = actions.add_parser("lifecycle", help="IOC kanıtının güncelliğini, kaynağını ve inceleme gerekçelerini değerlendir.")
    parser.add_argument("indicator_type", choices=INDICATOR_TYPES)
    parser.add_argument("value")
    parser.add_argument("--fresh-days", type=int, help="Güncel kanıt eşiği; ağ göstergeleri 7, hash 30 gün.")
    parser.add_argument("--stale-days", type=int, help="Eski kanıt eşiği; ağ göstergeleri 30, hash 180 gün.")
    parser.add_argument("--source-stale-hours", type=int, default=24, help="Kaynak toplama güncellik eşiği (1–8760 saat).")
    parser.add_argument("--offset", type=int, default=0)
    parser.add_argument("--limit", type=int, default=50)
    parser.add_argument("--expected-snapshot", help="Önceki sayfanın değerlendirme kesiti.")


_ASSESSMENT = {"not_recorded": "Kayıt yok", "needs_review": "İnceleme gerekli",
               "current_context": "Güncel kaynak bağlamı", "historical_only": "Yalnız geçmiş / geçerlilik dışı"}
_CURRENCY = {"recent": "güncel", "aging": "yakın geçmiş", "stale": "eski", "unknown": "bilinmiyor", "future": "saat tutarsız"}
_CLAIM = {"active": "etkin", "revoked": "geri çekilmiş", "expired": "süresi dolmuş", "not_yet_valid": "geçerlilik başlamamış"}
_COLLECTION = {"complete": "başarılı", "failed": "başarısız", "not_checked": "yapılmadı", "unmanaged": "elle kayıt / toplama yönetilmiyor"}


def lifecycle_lines(data):
    query = data["query"]
    lines = [f"IOC yaşam döngüsü: {safe_text(query['indicator_type'])} | {safe_text(query['value'])}",
             "Değerlendirme: " + _ASSESSMENT[data["assessment"]],
             f"Kaynak: {data['source_count']} farklı ad; {data['current_source_count']} etkin/geçerli",
             f"Politika: {data['policy']['version']} | güncel < {data['policy']['fresh_days']} gün; eski ≥ {data['policy']['stale_days']} gün",
             f"İddialar: {len(data['assertions'])}/{data['total_count']} gösteriliyor"]
    for row in data["assertions"]:
        lines.extend([f"  {safe_text(row['source_name'])} | {_CLAIM[row['claim_state']]} | {_ASSESSMENT[row['assessment']]}",
            f"    Kaynak: {safe_text(row['source_reference'])}",
            f"    Özgün güven: {row['confidence']}/100 | Kayıtlı kanıt: {_CURRENCY[row['currency']['state']]}",
            f"    Kayıtlı son tarih: {safe_text(row['assertion_last_seen_at'])}",
            "    Sağlayıcının bildirdiği gözlem: " + (safe_text(row['reported_observation_at']) if row['reported_observation_at'] else "bilinmiyor"),
            f"    Son toplama: {_COLLECTION[row['collection']['status']]}"])
        for key, label in (("latest_attempt", "Son deneme"), ("last_success", "Son başarılı toplama")):
            run = row["collection"][key]
            if run:
                lines.append(f"    {label}: {safe_text(run['finished_at'])} | {run['id']}")
        lines.extend("    " + safe_text(reason["message"]) for reason in row["reasons"])
        lines.append(f"    İddia: {row['assertion_id']} | Olay: {row['last_event']['id']}")
    if data["has_more"]:
        lines.append(f"Sonraki sayfa: --offset {data['offset'] + len(data['assertions'])} --expected-snapshot {data['snapshot_id']}")
    lines.append("Kesit: " + data["snapshot_id"])
    lines.extend(data["notes"])
    return lines


def execute_ioc_lifecycle(database, args):
    parameters = {key: getattr(args, key) for key in ("indicator_type", "value", "fresh_days", "stale_days",
        "source_stale_hours", "offset", "limit", "expected_snapshot")}
    data = make_ioc_lifecycle_service(database).show(**parameters)
    return data, lifecycle_lines(data)
