"""Read organization evidence and exact navigation links in one SQLite snapshot."""

from datetime import datetime
import json
from pathlib import Path
import sqlite3

from xti.adapters.schema import SCHEMA_VERSION
from xti.adapters.sqlite import SQLiteAssetRepository, StorageError
from xti.adapters.sqlite_brand_username_reviews import SQLiteBrandUsernameReviewRepository
from xti.adapters.sqlite_brand_username_watches import SQLiteBrandUsernameWatchRepository
from xti.adapters.sqlite_cases import SQLiteCaseRepository, read_case_evidence_links
from xti.adapters.sqlite_cname import SQLiteSurfaceCnameRepository
from xti.adapters.sqlite_findings import SQLiteFindingRepository, _FINDING_COLUMNS
from xti.adapters.sqlite_inbox import SQLiteInboxRepository, _COMBINED_NOTIFICATIONS
from xti.adapters.sqlite_jobs import SQLiteJobRepository
from xti.adapters.sqlite_mail import SQLiteSurfaceMailRepository
from xti.adapters.sqlite_organization_scope import read_organization_scope
from xti.adapters.sqlite_organization_content import read_organization_content
from xti.adapters.sqlite_public_notices import read_public_notice_snapshot
from xti.adapters.sqlite_public_notice_watches import (
    read_public_notice_watch_details, read_complete_public_notice_watch,
)
from xti.adapters.sqlite_ransomlook_claims import SQLiteRansomLookClaimRepository
from xti.adapters.sqlite_ransomlook_watches import SQLiteRansomLookWatchRepository
from xti.adapters.sqlite_ransomware_claims import SQLiteRansomwareClaimRepository
from xti.adapters.sqlite_ransomware_watches import SQLiteRansomwareWatchRepository
from xti.adapters.sqlite_surface_candidates import SQLiteSurfaceCandidateRepository
from xti.adapters.sqlite_services import SQLiteSurfaceServiceScanRepository
from xti.adapters.sqlite_surface import SQLiteSurfaceRepository
from xti.adapters.sqlite_surface_freshness import read_surface_freshness_snapshot
from xti.domain.assets import ValidationError, normalize_domain
from xti.domain.brand_username_reviews import brand_username_review_candidate_id
from xti.domain.cases import canonical_snapshot
from xti.domain.organization_export import (
    MAX_EXPORT_TARGETS, MAX_EXPORT_RECORDS, OrganizationExportSnapshot,
    validate_complete_export,
)
from xti.domain.organization_report import (
    OrganizationReport, OrganizationReportAttempt, OrganizationReportCoverage,
    OrganizationReportPage, OrganizationReportRecord, OrganizationReportTarget,
    ReportNavigation, report_freshness, surface_result_status,
)
from xti.domain.organizations import normalize_organization_id


_MAX_ROWS = 50_000


def _navigation(label: str, *arguments: str) -> ReportNavigation:
    return ReportNavigation(label, arguments)


def _time(value: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value)
        if parsed.tzinfo is None or parsed.utcoffset() is None:
            raise ValueError("timezone required")
        return parsed
    except (ValueError, TypeError, OverflowError) as error:
        raise StorageError("Kuruluş raporu kanıt zamanı bozuk.") from error


def _rows(connection: sqlite3.Connection, query: str, values: tuple = ()) -> list:
    rows = connection.execute(query + " LIMIT ?", (*values, _MAX_ROWS + 1)).fetchall()
    if len(rows) > _MAX_ROWS:
        raise StorageError("Kuruluş hedefinin kanıtı 50.000 kayıt doğrulama sınırını aşıyor.")
    return rows


def _audited_case_links(connection: sqlite3.Connection):
    # The same lifecycle validation protects case reads and organization views.
    return read_case_evidence_links(connection)


class _SnapshotReader:
    def __init__(self, connection: sqlite3.Connection, *, observed_at: str,
                 stale_after_hours: int, item_offset: int, item_limit: int) -> None:
        self.connection = connection
        self.observed_at = observed_at
        self.stale_after_hours = stale_after_hours
        self.item_offset = item_offset
        self.item_limit = item_limit
        self._cache: dict[str, object] = {}

    def cached(self, key, loader):
        if key not in self._cache:
            self._cache[key] = loader(self.connection)
        return self._cache[key]

    def page(self, kind: str, records: list[OrganizationReportRecord]) -> OrganizationReportPage:
        records.sort(key=lambda record: (_time(record.recorded_at), record.id), reverse=True)
        selected = tuple(records[self.item_offset:self.item_offset + self.item_limit])
        return OrganizationReportPage(
            kind, selected, len(records), self.item_offset, self.item_limit,
            self.item_offset + len(selected) < len(records),
        )

    def coverage(self, family, source, latest, success, notes=()):
        return OrganizationReportCoverage(
            family, source, latest, success,
            report_freshness(
                success.recorded_at if success else None,
                self.observed_at, self.stale_after_hours,
            ), tuple(notes),
        )

    @staticmethod
    def attempt(run, *, status=None, definition=None, baseline=None):
        if run is None:
            return None
        at = getattr(run, "recorded_at", None) or getattr(run, "executed_at", None)
        at = at or getattr(run, "finished_at", None) or run.started_at
        _time(at)
        actual_definition = getattr(run, "definition_sha256", None)
        return OrganizationReportAttempt(
            run.id, status or run.status, at, getattr(run, "error", None),
            getattr(run, "source_run_id", None), actual_definition,
            actual_definition == definition if definition is not None else None,
            baseline,
        )

    def domain(self, membership) -> OrganizationReportTarget:
        connection, domain = self.connection, membership.link.target.value
        asset = connection.execute("SELECT id FROM assets WHERE value=?", (domain,)).fetchone()
        if asset is None:
            raise StorageError("Kuruluş domain bağlantısı artık çözümlenemiyor.")
        asset_id = asset[0]
        findings, case_keys = [], set()
        for row in _rows(
            connection, f"SELECT {_FINDING_COLUMNS} FROM findings WHERE asset_id=? ORDER BY id",
            (asset_id,),
        ):
            finding = SQLiteFindingRepository._finding(row)
            if (
                finding.asset_value != domain or normalize_domain(finding.domain) != finding.domain
                or finding.status not in {"new", "suspicious", "uncertain", "dismissed"}
            ):
                raise StorageError("Kuruluş bulgusunun domain veya karar bağı bozuk.")
            normalize_organization_id(finding.id)
            _time(finding.created_at)
            findings.append(OrganizationReportRecord(
                finding.id, "finding", finding.domain, finding.status, finding.last_seen_at,
                "local-match", finding.reasons,
                navigation=(
                    _navigation("Bulgu kanıtı ve insan kararı", "findings", "show", finding.id),
                    _navigation("Kayıtlı CTI bağlantıları", "cti", "context", "--type", "domain", "--value", finding.domain),
                ),
            ))
            case_keys.add(("finding", finding.id))
        candidates = []
        for identifier, in _rows(
            connection, "SELECT id FROM surface_candidates WHERE asset_id=? ORDER BY id", (asset_id,),
        ):
            candidate = SQLiteSurfaceCandidateRepository._candidate(
                SQLiteSurfaceCandidateRepository._candidate_row(connection, identifier),
            )
            if (candidate.asset_id, candidate.asset_value) != (asset_id, domain):
                raise StorageError("Kuruluş alt alan adının kök bağı bozuk.")
            candidates.append(OrganizationReportRecord(
                candidate.id, "surface_candidate", candidate.domain, candidate.status,
                candidate.last_seen_at, "passive-discovery", (candidate.reason,),
                navigation=(_navigation("Aday ve kaynakları", "surface", "candidate", "show", candidate.id),),
            ))
        surface = read_surface_freshness_snapshot(connection, asset_id, domain)
        coverage = self.domain_coverage(asset_id, domain, surface)
        public_notices, public_coverage = self.public_notices(domain)
        coverage.append(public_coverage)
        case_keys.update(self.public_notice_case_keys(domain=domain))
        notices = self.domain_notices(asset_id, domain)
        from xti.adapters.sqlite_group_projection import guard, current
        group_records = []
        guard(connection)
        for (group_id,) in connection.execute('SELECT id FROM research_group_heads WHERE root_type=? AND root_value=? ORDER BY id', ('domain', domain)):
            group_record = current(connection, group_id)
            group = group_record['group']
            if group['root'] != ['domain', domain]:
                continue
            decision = group_record['decision']
            group_records.append(OrganizationReportRecord(group_record['id'], 'research_group',
                ', '.join(member['label'] for member in group['members']), group_record['status'],
                group_record['last_checked_at'], 'local-research-groups',
                (group['rule'], group['temporal']['state'], 'Son kayıtlı grup; canlı yeniden kontrol değildir.',
                 'Karar: ' + (decision['value'] if decision else 'henüz yok')),
                navigation=(_navigation('Güncel grup kanıtı', 'groups', 'current', group_record['id']),)))
            case_keys.add(('research_group', group_record['id']))
        return OrganizationReportTarget(
            membership, (("domain", domain),), tuple(coverage),
            (
                self.page("findings", findings), self.page("surface_candidates", candidates),
                self.page("public_notices", public_notices),
                self.page('research_groups', sorted(group_records, key=lambda row: row.id)),
                self.page("notifications", notices), self.page("case_links", self.case_links(case_keys)),
            ),
            (
                _navigation("Domain analizi", "analyze", domain),
                _navigation("Kaynak katkısı", "sources", "contribution", domain),
                _navigation("CTI bağlantıları", "cti", "context", "--type", "domain", "--value", domain),
                _navigation("Domain değişimleri", "changes", "--domain", domain, "--days", "7"),
                _navigation("Kamu olay kaynağı", "notices", "search", "--domain", domain),
            ),
            (
                "Domain bağlantısı yalnız bu kayıtlı kökü seçer; alt adayların ayrı varlık kontrollerini otomatik dahil etmez.",
                "Bulgu ve pasif aday listeleri insan kararlarıyla gösterilir; kesin kötü niyet veya sahiplik hükmü değildir.",
                "Vaka bağlantıları bu domainin bulgularına veya tam domain eşleşen tarihî kamu kanıtına verilmiş açık insan bağlantılarıdır.",
            ), surface,
        )

    def public_notices(self, domain: str) -> tuple[list[OrganizationReportRecord], OrganizationReportCoverage]:
        snapshot = self.cached("public-notices", read_public_notice_snapshot)
        source_notes = (snapshot.attribution, snapshot.license, snapshot.source_url,
                        "Yalnız kaynak domain alanının tam eşleşmesi seçilir; isimden sahiplik veya doğrulanmış ihlal çıkarılmaz.",
                        "Katalog yenilemesi ortaktır; sıfır eşleşme güvenli olduğu anlamına gelmez.")
        coverage = self.coverage("public-notices", snapshot.source_name,
                                 self.attempt(snapshot.latest_run), self.attempt(snapshot.latest_complete_run), source_notes)
        records = []
        for notice in snapshot.notices:
            if notice.domain != domain:
                continue
            flags = (f"{name}={getattr(notice, name)}" for name in (
                "is_verified", "is_fabricated", "is_sensitive", "is_retired", "is_spam_list", "is_malware", "is_stealer_log"))
            details = (
                f"Kaynağın tahmin ettiği olay tarihi: {notice.breach_date}",
                f"Kaynağa eklenme: {notice.added_at}", f"Kaynakta değişme: {notice.modified_at}",
                f"Kaynağın kayıt sayısı: {notice.pwn_count}", "Veri kategorileri: " + ", ".join(notice.data_classes),
                "Kaynak sınıfları (XTI kararı değil): " + ", ".join(flags),
                notice.source_url, snapshot.attribution, snapshot.license,
            ) + (("Kaynak katkısı: " + notice.source_attribution,) if notice.source_attribution else ())
            records.append(OrganizationReportRecord(
                notice.id, "public_notice", notice.title, "source_metadata", snapshot.latest_complete_run.finished_at,
                snapshot.source_name, details, source_run_id=snapshot.latest_complete_run.id,
                navigation=(_navigation("Kamu kaynağının tam kaydı", "notices", "show", notice.id),), public_notice=notice,
            ))
        return records, coverage

    def domain_coverage(self, asset_id, domain, surface):
        connection, coverage = self.connection, []
        for provider in ("crt.sh", "urlscan"):
            attempts = []
            for identifier, in _rows(
                connection,
                "SELECT a.id FROM scan_attempts a JOIN scan_jobs j ON j.id=a.job_id "
                "WHERE j.provider=? AND instr(j.targets,?)>0 ORDER BY a.rowid",
                (provider, '"' + domain + '"'),
            ):
                run = SQLiteJobRepository._get_attempt(connection, identifier)
                job = SQLiteJobRepository._get_job(connection, run.job_id)
                if domain not in job.targets:
                    continue
                attempts.append(run)
            latest = attempts[-1] if attempts else None
            success = next((run for run in reversed(attempts) if run.status == "complete"), None)
            coverage.append(self.coverage(
                "brand", provider, self.attempt(latest), self.attempt(success),
                ("Toplu çalışma varsa durum bütün kaynak çalışmasına aittir; yalnız bu domaine ait başarı oranı değildir.",),
            ))
        for provider in ("crt.sh", "theharvester"):
            runs = []
            for identifier, in _rows(
                connection,
                "SELECT id FROM surface_discovery_runs WHERE asset_id=? AND provider=? ORDER BY sequence",
                (asset_id, provider),
            ):
                runs.append(SQLiteSurfaceCandidateRepository._run(
                    SQLiteSurfaceCandidateRepository._run_row(connection, identifier),
                ))
            latest = runs[-1] if runs else None
            success = next((run for run in reversed(runs) if run.status == "complete"), None)
            coverage.append(self.coverage("discovery", provider, self.attempt(latest), self.attempt(success)))
        for kind, check in (
            ("web", surface.latest_check), ("mail", surface.latest_mail_check),
            ("services", surface.latest_service_check), ("cname", surface.latest_cname_check),
        ):
            status = surface_result_status(check) if check else None
            latest = OrganizationReportAttempt(check.id, status, check.recorded_at) if check else None
            success = self.surface_last_success(kind, asset_id, domain) if check else None
            coverage.append(self.coverage(
                "surface", kind, latest, success,
                ("Güncellik son tam kontrolün yaşını ölçer; en son başarısız kontrol ayrıca görünür.",),
            ))
        return coverage

    def surface_last_success(self, kind: str, asset_id: str, domain: str) -> OrganizationReportAttempt | None:
        table, repository = {
            "web": ("surface_checks", SQLiteSurfaceRepository),
            "mail": ("surface_mail_checks", SQLiteSurfaceMailRepository),
            "services": ("surface_service_checks", SQLiteSurfaceServiceScanRepository),
            "cname": ("surface_cname_checks", SQLiteSurfaceCnameRepository),
        }[kind]
        extra = "authorization_reason, " if kind == "services" else ""
        rows = _rows(self.connection,
                     f"SELECT id, asset_id, ?, {extra}result, state_sha256, change, recorded_at "
                     f"FROM {table} WHERE asset_id=? ORDER BY rowid DESC", (domain, asset_id))
        for row in rows:
            check = repository._check(row, domain)
            if surface_result_status(check) == "complete":
                return OrganizationReportAttempt(check.id, "complete", check.recorded_at)
        return None

    def social(self, membership) -> OrganizationReportTarget:
        data = self.cached("social", SQLiteBrandUsernameReviewRepository._audit)
        watches, runs, items, candidates, _, _, by_candidate, _ = data
        watch = watches[membership.link.target.value]
        definition = SQLiteBrandUsernameWatchRepository._definition(watch)
        selected_runs = sorted((run for run in runs.values() if run.watch_id == watch.id), key=lambda run: run.sequence)
        latest = selected_runs[-1] if selected_runs else None
        success = next((run for run in reversed(selected_runs)
                        if run.status == "complete" and run.definition_sha256 == definition), None)
        profiles, case_keys = [], set()
        for item in items:
            if success is None or item.run_id != success.id:
                continue
            details = [f"Platform: {item.platform}", f"Değişim: {item.action}"]
            navigation = [_navigation("Kaynak çalışması", "brand", "watch-run-show", success.id)]
            if item.status == "found_unverified":
                candidate_id = brand_username_review_candidate_id(
                    watch_id=watch.id, definition_sha256=definition,
                    platform=item.platform, state_sha256=item.state_sha256,
                )
                if candidate_id in by_candidate:
                    review = SQLiteBrandUsernameReviewRepository._state(candidate_id, by_candidate[candidate_id], candidates)
                    details.extend((f"İnsan kararı: {review.decision}", review.reason))
                    navigation.append(_navigation("İnsan incelemesi", "brand", "watch-review-show", candidate_id))
                    case_keys.add(("social_profile", candidate_id))
            profiles.append(OrganizationReportRecord(
                item.id, "social_profile", item.profile_url or item.platform,
                item.status, success.recorded_at, watch.source_key, tuple(details),
                run_id=success.id, definition_sha256=definition, navigation=tuple(navigation),
            ))
        latest_attempt = self.attempt(latest, definition=definition, baseline=(latest.previous_complete_run_id is None) if latest else None)
        success_attempt = self.attempt(success, definition=definition, baseline=(success.previous_complete_run_id is None) if success else None)
        notices = self.watch_notices("username-watch", watch.id)
        return OrganizationReportTarget(
            membership, (("username", watch.username), ("platforms", ", ".join(watch.platforms)), ("definition_sha256", definition)),
            (self.coverage("username-watch", watch.source_key, latest_attempt, success_attempt),),
            (self.page("profiles", profiles), self.page("notifications", notices), self.page("case_links", self.case_links(case_keys))),
            (_navigation("İzleme geçmişi", "brand", "watch-show", watch.id),),
            (
                "Profil satırları yalnız güncel tanımın son başarılı çalışmasından gelir; son hata önceki kanıtı silmez.",
                "unreported, hesap olmadığı veya silindiği anlamına gelmez; bulunma kimliği veya taklidi doğrulamaz.",
                "Bildirim geçmişi bu izleme kimliğine aittir; eski tanımın bildirimi güncel sorguya uygulanmaz.",
            ),
        )

    def ransomware(self, membership) -> OrganizationReportTarget:
        kind, watch_id = membership.link.target.kind, membership.link.target.value
        is_rl = kind == "ransomlook-watch"
        source = "ransomlook" if is_rl else "threatcluster"
        repository = SQLiteRansomLookWatchRepository if is_rl else SQLiteRansomwareWatchRepository
        claim_repository = SQLiteRansomLookClaimRepository if is_rl else SQLiteRansomwareClaimRepository
        watches, _, runs, items = self.cached(kind, repository._audit)[:4]
        feed_runs, _ = self.cached(source + "-feed", claim_repository._audit)
        watch = watches[watch_id]
        definition = repository._definition(watch)
        selected = sorted((run for run in runs.values() if run.watch_id == watch_id), key=lambda run: run.sequence)
        latest = selected[-1] if selected else None
        success = next((run for run in reversed(selected) if run.definition_sha256 == definition), None)
        feed_latest = feed_runs[-1] if feed_runs else None
        feed_success = next((run for run in reversed(feed_runs) if run.status == "complete"), None)
        records, case_keys = [], set()
        for item in items:
            if success is None or item.run_id != success.id or item.action == "removed":
                continue
            claim = item.match.claim
            records.append(OrganizationReportRecord(
                claim.id, "ransomware_claim", claim.victim, "source_claim", success.executed_at,
                source, (f"Grup: {claim.group}", f"Kaynak zamanı: {claim.discovered_at}", f"Değişim: {item.action}", f"Eşleşme: {item.match.match_type}"),
                run_id=success.id, source_run_id=success.source_run_id, definition_sha256=success.definition_sha256,
                navigation=(_navigation("İddia kanıtı", "ransomware", "watch-run-show", success.id, "--source", source),),
            ))
            case_keys.add(("ransomware_ransomlook" if is_rl else "ransomware_threatcluster", claim.id))
        coverage = (
            self.coverage(kind, source, self.attempt(latest, status="complete", definition=definition, baseline=latest.previous_run_id is None if latest else None),
                          self.attempt(success, status="complete", definition=definition, baseline=success.previous_run_id is None if success else None)),
            self.coverage("shared-feed", source, self.attempt(feed_latest), self.attempt(feed_success),
                          ("Kaynak yenilemesi ortaktır; tek başına bu izlemenin yeniden çalıştırıldığı anlamına gelmez.",)),
        )
        notes = [
            "Kaynak iddiaları doğrulanmış ihlal değildir; kuruluş bağlantısı aynı adlı şirketin kimliğini doğrulamaz.",
            "İddialar yalnız güncel tanımın son kayıtlı izlemesindendir; çıkarılmış öğeler güncel listeye eklenmez.",
            "Güncel sorgu etiketi tarihî çalışma sorgusu değildir; eski bildirimde tam çalışma/tanım özeti korunur.",
        ]
        if success and feed_success and success.source_run_id != feed_success.id:
            notes.append("Daha yeni başarılı kaynak yenilemesi var; bu izleme henüz o kaynak çalışmasını kapsamıyor.")
        return OrganizationReportTarget(
            membership, (("current_query", watch.query), ("match_mode", watch.match_mode), ("definition_sha256", definition)),
            coverage,
            (self.page("claims", records), self.page("notifications", self.watch_notices(kind, watch_id)), self.page("case_links", self.case_links(case_keys))),
            (_navigation("İzleme geçmişi", "ransomware", "watch-show", watch_id, "--source", source),), tuple(notes),
        )

    def notification_records(self, identifiers, *, expected_watch=None, expected_domain=None):
        records = []
        for identifier in identifiers:
            notification = SQLiteInboxRepository._get(self.connection, identifier)
            if notification.evidence_id is not None:
                evidence = SQLiteInboxRepository._change_evidence(self.connection, notification.evidence_type, notification.evidence_id)
                if expected_domain != evidence.asset_value:
                    raise StorageError("Kuruluş bildirimi farklı domain kanıtına bağlı.")
            run_id = notification.ransomware_run_id or notification.ransomlook_run_id
            details = [f"Olay: {notification.event_type}"]
            definition, source_run = None, None
            if expected_watch is not None:
                kind, watch_id = expected_watch
                if kind == "username-watch":
                    data = self.cached("social", SQLiteBrandUsernameReviewRepository._audit)
                    candidate = data[3].get(notification.brand_candidate_id)
                    if candidate is None or candidate.watch_id != watch_id:
                        raise StorageError("Kuruluş bildirimi farklı sosyal izlemeye bağlı.")
                    run_id, definition = candidate.run_id, candidate.definition_sha256
                    details.append(f"İnsan karar adayı: {candidate.id}")
                else:
                    repository = SQLiteRansomLookWatchRepository if kind == "ransomlook-watch" else SQLiteRansomwareWatchRepository
                    _, _, runs, _ = self.cached(kind, repository._audit)[:4]
                    run = runs.get(run_id)
                    if run is None or run.watch_id != watch_id:
                        raise StorageError("Kuruluş bildirimi farklı iddia izlemesine bağlı.")
                    source_run, definition = run.source_run_id, run.definition_sha256
            records.append(OrganizationReportRecord(
                notification.id, "notification", notification.event_type,
                "unread" if notification.read_at is None else "read", notification.created_at,
                "local-inbox", tuple(details), run_id, source_run, definition,
                (_navigation("Bildirim ve kanıtı", "inbox", "show", notification.id),),
            ))
        return records

    def domain_notices(self, asset_id, domain):
        query = (
            "SELECT n.id FROM (" + _COMBINED_NOTIFICATIONS + ") n WHERE "
            "n.finding_id IN (SELECT id FROM findings WHERE asset_id=?) OR "
            "n.candidate_id IN (SELECT id FROM surface_candidates WHERE asset_id=?) OR "
            "(n.evidence_type='surface' AND n.evidence_id IN (SELECT id FROM surface_checks WHERE asset_id=?)) OR "
            "(n.evidence_type='mail' AND n.evidence_id IN (SELECT id FROM surface_mail_checks WHERE asset_id=?)) OR "
            "(n.evidence_type='service' AND n.evidence_id IN (SELECT id FROM surface_service_checks WHERE asset_id=?)) "
            "ORDER BY n.sequence"
        )
        identifiers = [row[0] for row in _rows(self.connection, query, (asset_id,) * 5)]
        return self.notification_records(identifiers, expected_domain=domain)

    def watch_notices(self, kind, watch_id):
        if kind == "username-watch":
            query = (
                "SELECT n.id FROM brand_username_review_notifications n JOIN "
                "brand_username_review_events e ON e.id=n.review_event_id WHERE e.watch_id=? ORDER BY n.sequence"
            )
        else:
            table = "ransomlook_watch_notifications" if kind == "ransomlook-watch" else "ransomware_watch_notifications"
            query = f"SELECT id FROM {table} WHERE watch_id=? ORDER BY sequence"
        identifiers = [row[0] for row in _rows(self.connection, query, (watch_id,))]
        return self.notification_records(identifiers, expected_watch=(kind, watch_id))

    def public_notice_case_keys(self, *, domain=None, organization_id=None):
        keys = set()
        for link in self.cached("case-evidence", _audited_case_links):
            if not link.active or link.evidence_type not in {"public_notice", "public_notice_watch"}:
                continue
            payload = json.loads(link.snapshot_json)
            if link.evidence_type == "public_notice_watch":
                if organization_id is not None and payload["watch"]["organization_id"] == organization_id:
                    keys.add((link.evidence_type, link.evidence_id))
            elif domain is not None and any(
                item.get(side) is not None and item[side].get("domain") == domain
                for item in payload["items"] for side in ("before", "after")
            ):
                keys.add((link.evidence_type, link.evidence_id))
        return keys

    def case_links(self, evidence_keys):
        if not evidence_keys:
            return []
        links = self.cached("case-evidence", _audited_case_links)
        records = []
        for link in links:
            if not link.active or (link.evidence_type, link.evidence_id) not in evidence_keys:
                continue
            case = SQLiteCaseRepository._get_case(self.connection, link.case_id)
            lifecycle = self.connection.execute(
                "SELECT sequence,id,case_id,activity_type,reference_id,summary,reason,"
                "snapshot_json,snapshot_sha256,recorded_at FROM case_activities "
                "WHERE case_id=? AND activity_type IN ('case_created','case_updated','status_changed') "
                "ORDER BY sequence DESC LIMIT 1", (case.id,),
            ).fetchone()
            expected, _ = canonical_snapshot(SQLiteCaseRepository._case_payload(case))
            if lifecycle is None or lifecycle[7] != expected:
                raise StorageError("Kuruluşun bağlı vaka durumu kanıtıyla uyuşmuyor.")
            if SQLiteCaseRepository._activity(lifecycle).case_id != case.id:
                raise StorageError("Kuruluşun vaka yaşam döngüsü bağı bozuk.")
            # No title, notes or unrelated evidence from a case shared across groups.
            records.append(OrganizationReportRecord(
                link.id, "case_link", case.id, case.status, link.updated_at,
                "human-case-link", (f"Kanıt türü: {link.evidence_type}", f"Kanıt kimliği: {link.evidence_id}", f"Öncelik: {case.priority}"),
                navigation=(
                    _navigation("Bağlı vaka", "cases", "show", case.id),
                    _navigation("Vakadaki donmuş kanıt", "cases", "evidence-show", case.id, link.id),
                ),
            ))
        return records


class SQLiteOrganizationReportRepository:
    def __init__(self, path: Path) -> None:
        self._storage = SQLiteAssetRepository(path)

    def read(self, organization_id: str, *, observed_at: str, stale_after_hours: int,
             target_offset: int, target_limit: int, item_offset: int, item_limit: int) -> OrganizationReport:
        return self._read(
            organization_id, observed_at=observed_at, stale_after_hours=stale_after_hours,
            target_offset=target_offset, target_limit=target_limit,
            item_offset=item_offset, item_limit=item_limit, complete=False,
        )

    def read_complete(self, organization_id: str, *, observed_at: str,
                      stale_after_hours: int) -> OrganizationExportSnapshot:
        return self._read(
            organization_id, observed_at=observed_at, stale_after_hours=stale_after_hours,
            target_offset=0, target_limit=MAX_EXPORT_TARGETS,
            item_offset=0, item_limit=MAX_EXPORT_RECORDS, complete=True,
        )

    def _read(self, organization_id, *, observed_at, stale_after_hours,
              target_offset, target_limit, item_offset, item_limit, complete):
        try:
            with self._storage._connection(readonly=True) as connection:
                connection.execute("BEGIN")
                scope = read_organization_scope(connection, organization_id)
                SQLiteInboxRepository._validate_sequences(connection)
                reader = _SnapshotReader(
                    connection, observed_at=observed_at, stale_after_hours=stale_after_hours,
                    item_offset=item_offset, item_limit=item_limit,
                )
                effective = scope.effective_links
                if complete and len(effective) > MAX_EXPORT_TARGETS:
                    raise ValidationError("Tam rapor 1.000 etkin hedef sınırını aşıyor; dosya yazılmadı.")
                targets = []
                record_count = len(scope.links)
                for membership in effective[target_offset:target_offset + target_limit]:
                    if membership.link.target.kind == "domain":
                        targets.append(reader.domain(membership))
                    elif membership.link.target.kind == "username-watch":
                        targets.append(reader.social(membership))
                    else:
                        targets.append(reader.ransomware(membership))
                    record_count += sum(len(page.items) for page in targets[-1].sections)
                    if complete and record_count > MAX_EXPORT_RECORDS:
                        raise ValidationError("Tam rapor 50.000 kayıt sınırını aşıyor; dosya yazılmadı.")
                if complete:
                    watch, watch_runs = read_complete_public_notice_watch(
                        connection, organization_id, maximum_records=MAX_EXPORT_RECORDS,
                    )
                else:
                    watch = read_public_notice_watch_details(
                        connection, organization_id, event_limit=item_limit, run_limit=item_limit,
                        event_offset=item_offset, run_offset=item_offset,
                    )
                report = OrganizationReport(
                    scope, observed_at, True, stale_after_hours, tuple(targets), len(effective),
                    target_offset, target_limit, item_offset, item_limit,
                    target_offset + len(targets) < len(effective),
                    (
                        "Hedef bölümleri kuruluşun şu an etkin açık bağlantılarını seçer; geçmiş sahiplik veya olay atfı yapmaz. Kamu olay izleme bölümü ise kesin kuruluş kimliğiyle tarihî kapsamı ayrıca gösterir.",
                        "Bağlantısı/kuruluşu/hedefi geri çekilmiş kayıtlar kapsamda görünür, sonuçlara katılmaz; kaynak kayıtları silinmez.",
                        "Bölümler aynı kanıtı paylaşabilir; sayaçlar benzersiz tehdit toplamı değildir.",
                        "Sayfa sınırları yalnız gösterimi etkiler; her bölüm toplamı ve devam bilgisi ayrı verilir.",
                        "Komutlar gezinme önerisidir; bu rapor onları çalıştırmaz, ağa çıkmaz ve bildirimleri okundu yapmaz.",
                    ), SCHEMA_VERSION,
                    public_notice_watch=watch,
                    public_notice_case_links=reader.page("public_notice_case_links", reader.case_links(
                        reader.public_notice_case_keys(organization_id=organization_id),
                    )),
                    content=read_organization_content(connection, scope,
                        observed_at=observed_at, stale_after_hours=stale_after_hours,
                        scope_offset=target_offset, scope_limit=MAX_EXPORT_RECORDS if complete else target_limit,
                        item_offset=item_offset, item_limit=item_limit),
                )
                if complete:
                    result = OrganizationExportSnapshot(report, watch_runs)
                    validate_complete_export(result, organization_id)
                    return result
                return report
        except ValidationError as error:
            if complete:
                raise
            raise StorageError("Kuruluş raporunun kaynak kanıtı doğrulanamadı; kayıtlar değiştirilmedi.") from error
        except (sqlite3.Error, ValueError, TypeError, KeyError, OverflowError) as error:
            raise StorageError("Kuruluş raporunun kaynak kanıtı doğrulanamadı; kayıtlar değiştirilmedi.") from error
