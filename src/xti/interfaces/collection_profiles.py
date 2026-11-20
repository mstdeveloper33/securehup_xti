"""CLI arguments and safe terminal views for named collection selections."""

import argparse

from xti.domain.assets import ValidationError
from xti.domain.collection import COLLECTION_TASK_IDS, DEFAULT_COLLECTION_TASKS
from xti.domain.news import NEWS_SOURCES
from xti.domain.collection_profiles import (
    CollectionProfile, CollectionProfileDefinition, CollectionProfileDetails,
    CollectionProfileMutation, normalize_profile_definition,
)
from xti.interfaces.text import safe_text


_OPTION_FIELDS = (
    "tasks", "typos", "stale_after_hours", "finding_limit",
    "username_watch_ids", "ransomware_watch_ids", "ransomlook_watch_ids", "watch_item_limit",
    "news_sources", "search_watch_ids", "only_news", "social_watch_ids", "only_social",
)
_ACTIONS = {"added": "Kaydedildi", "updated": "Güncellendi", "reactivated": "Yeniden etkin",
            "revoked": "Geri çekildi", "unchanged": "Değişmedi"}


def add_collection_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument('--social-watch', action='append', dest='social_watch_ids', metavar='ID',
        help='Aynı domaine ait birleşik sosyal takip tanımını ekle; tekrarlanabilir.')
    parser.add_argument('--only-social', action='store_true', default=None,
        help='Yalnız --social-watch ile seçilen birleşik sosyal takipleri çalıştır.')
    # None distinguishes an omitted option from an explicit attempt to override
    # a saved profile, even when the supplied value equals today's default.
    parser.add_argument(
        "--task", action="append", choices=COLLECTION_TASK_IDS, dest="tasks",
        help="İş seç; tekrarlanabilir. Varsayılan: scan-crtsh, scan-urlscan, discover-crtsh.",
    )
    parser.add_argument(
        "--only-news", action="store_true", default=None,
        help="Yalnız açıkça seçilen haber kaynaklarını ve haber aramalarını çalıştır.",
    )
    parser.add_argument(
        "--news-source", action="append", dest="news_sources",
        choices=tuple(source.key for source in NEWS_SOURCES),
        help="RSS/Atom kaynağını ekle; tekrarlanabilir. Varsayılan haber toplamaz.",
    )
    parser.add_argument(
        "--search-watch", action="append", dest="search_watch_ids", metavar="ID",
        help="Haber aramasını yenilemeden sonra karşılaştır; üç haber kaynağının seçilmesini gerektirir.",
    )
    parser.add_argument("--typos", action="store_true", default=None, help="Sınırlı yazım varyantları.")
    parser.add_argument("--stale-after-hours", type=int, help="Güncellik eşiği; varsayılan 24 saat (1–8760).")
    parser.add_argument("--finding-limit", type=int, help="Analiz görünüm sınırı; varsayılan 10 (1–50).")
    parser.add_argument(
        "--username-watch", action="append", dest="username_watch_ids", metavar="ID",
        help="Kayıtlı Maigret/Sherlock izlemesini ekle; tekrarlanabilir.",
    )
    parser.add_argument(
        "--ransomware-watch", action="append", dest="ransomware_watch_ids", metavar="ID",
        help="ThreatCluster izlemesini ekle; tekrarlanabilir.",
    )
    parser.add_argument(
        "--ransomlook-watch", action="append", dest="ransomlook_watch_ids", metavar="ID",
        help="RansomLook izlemesini ekle; tekrarlanabilir.",
    )
    parser.add_argument(
        "--watch-item-limit", type=int,
        help="İzleme görünüm sınırı; varsayılan 100 (1–500), toplama kapsamını daraltmaz.",
    )


def register_profiles_parser(commands) -> None:
    parser = commands.add_parser("profiles", help="Toplama seçimlerini adla kaydet, göster ve geri çek.")
    actions = parser.add_subparsers(dest="profile_action", required=True)
    save = actions.add_parser("save", help="Tam seçimi kaydet/güncelle; ağdan toplama başlatmaz.")
    save.add_argument("name", help="Profil adı; örneğin gunluk.")
    save.add_argument("domain", help="Önceden kaydedilmiş domain.")
    add_collection_arguments(save)
    listing = actions.add_parser("list", help="Kayıtlı profilleri listele.")
    listing.add_argument("--all", action="store_true", dest="all_entries")
    listing.add_argument("--limit", type=int, default=50)
    show = actions.add_parser("show", help="Seçimleri ve değişiklik geçmişini göster.")
    show.add_argument("name")
    show.add_argument("--event-limit", type=int, default=50)
    revoke = actions.add_parser("revoke", help="Kaydı silmeden çalıştırılmasını kapat.")
    revoke.add_argument("name")
    revoke.add_argument("--reason", required=True)


def validate_profile_selection(args) -> None:
    if args.profile is not None:
        if args.domain is not None or any(getattr(args, field) is not None for field in _OPTION_FIELDS):
            raise ValidationError("--profile ile domain veya toplama ayarı birlikte verilemez; profili güncelleyin.")
    elif args.domain is None:
        raise ValidationError("Toplama için domain veya --profile AD gerekli.")


def definition_from_arguments(args) -> CollectionProfileDefinition:
    only_news = getattr(args, "only_news", False)
    only_social = getattr(args, 'only_social', False)
    social = getattr(args, 'social_watch_ids', None)
    if only_social and (only_news or args.tasks is not None or args.news_sources or args.search_watch_ids
            or args.username_watch_ids or args.ransomware_watch_ids or args.ransomlook_watch_ids or args.typos):
        raise ValidationError('--only-social başka toplama seçenekleriyle birlikte kullanılamaz.')
    if only_social and not social:
        raise ValidationError('--only-social için en az bir --social-watch seçin.')
    if only_news and (
        args.tasks is not None or args.username_watch_ids or args.ransomware_watch_ids
        or args.ransomlook_watch_ids or args.typos or social
    ):
        raise ValidationError("--only-news ile başka toplama işleri, sosyal/sızıntı izlemeleri veya --typos seçilemez.")
    if only_news and not args.news_sources:
        raise ValidationError("--only-news için en az bir --news-source seçin.")
    return normalize_profile_definition(CollectionProfileDefinition(
        asset_value=args.domain,
        task_ids=() if only_news or only_social else tuple(args.tasks) if args.tasks is not None else DEFAULT_COLLECTION_TASKS,
        username_watch_ids=tuple(args.username_watch_ids or ()),
        ransomware_watch_ids=tuple(args.ransomware_watch_ids or ()),
        ransomlook_watch_ids=tuple(args.ransomlook_watch_ids or ()),
        typos=args.typos if args.typos is not None else False,
        stale_after_hours=args.stale_after_hours if args.stale_after_hours is not None else 24,
        finding_limit=args.finding_limit if args.finding_limit is not None else 10,
        watch_item_limit=args.watch_item_limit if args.watch_item_limit is not None else 100,
        news_sources=tuple(args.news_sources or ()),
        search_watch_ids=tuple(args.search_watch_ids or ()),
        social_watch_ids=tuple(social or ()),
    ))


def profile_lines(profile: CollectionProfile) -> list[str]:
    definition = profile.definition
    lines = [
        f"Profil: {safe_text(profile.display_name)} | {'Etkin' if profile.active else 'Geri çekilmiş'}",
        f"Kimlik: {safe_text(profile.id)} | Sürüm: {profile.revision}",
        f"Domain: {safe_text(definition.asset_value)}",
        f"İşler: {safe_text(', '.join(definition.task_ids) or 'Yalnız seçili izleme/yayın işleri')}",
        f"Haber kaynakları: {safe_text(', '.join(definition.news_sources) or 'Seçilmedi')}",
        f"Yazım varyantları: {'açık' if definition.typos else 'kapalı'}",
        f"Güncellik: {definition.stale_after_hours} saat | Analiz görünümü: {definition.finding_limit}",
        f"İzleme görünüm sınırı: {definition.watch_item_limit}",
    ]
    for label, ids in (
        ("Sosyal", definition.username_watch_ids),
        ("ThreatCluster", definition.ransomware_watch_ids),
        ("RansomLook", definition.ransomlook_watch_ids),
        ("Haber araması", definition.search_watch_ids),
        ('Birleşik sosyal', definition.social_watch_ids),
    ):
        lines.append(f"{label} izlemeleri: {len(ids)}")
        lines.extend(f"  {safe_text(watch_id)}" for watch_id in ids)
    return lines


def mutation_lines(mutation: CollectionProfileMutation) -> list[str]:
    return [
        f"Toplama profili: {_ACTIONS[mutation.action]}", *profile_lines(mutation.profile),
        "Bu işlem kaynak sorgulamadı. Profil, domain ile izlemeler arasında sahiplik kanıtı değildir.",
    ]


def detail_lines(details: CollectionProfileDetails) -> list[str]:
    lines = [*profile_lines(details.profile), "", f"Değişiklik geçmişi: {details.event_count}"]
    for event in details.events:
        lines.append(
            f"  {safe_text(event.recorded_at)} | sürüm {event.revision} | {_ACTIONS[event.action]}"
        )
        if event.reason:
            lines.append(f"    {safe_text(event.reason)}")
    if details.event_count > len(details.events):
        lines.append(f"{details.event_count - len(details.events)} eski değişiklik görünüm sınırı dışında.")
    return [*lines, "Geçmiş tanımlar JSON çıktısında tam olarak bulunur."]


def list_lines(profiles: tuple[CollectionProfile, ...], has_more: bool) -> list[str]:
    lines = ["Kayıtlı toplama profilleri:"]
    if not profiles:
        lines.append("Bu seçimde profil yok.")
    for profile in profiles:
        lines.append(
            f"  {safe_text(profile.display_name)} | {safe_text(profile.definition.asset_value)} | "
            f"sürüm {profile.revision} | {'etkin' if profile.active else 'geri çekilmiş'}"
        )
    if has_more:
        lines.append("Liste sınırı dışında profiller var; --limit en fazla 500 olabilir. Bilinen adı profiles show AD ile açın.")
    return lines
