"""Read existing source history and local tool metadata without network access."""

from __future__ import annotations

from dataclasses import replace
import hashlib
from importlib.metadata import distributions
import json
import os
from pathlib import Path
import stat

from xti.adapters.sqlite import SQLiteAssetRepository, StorageError
from xti.adapters.sqlite_brand_username_watches import SQLiteBrandUsernameWatchRepository
from xti.adapters.sqlite_cooldowns import SQLiteCooldownRepository
from xti.adapters.sqlite_cti_feeds import SQLiteCtiFeedRepository, _RUN_SELECT as FEED_RUN_SELECT
from xti.adapters.sqlite_cti_knowledge import SQLiteCtiKnowledgeRepository
from xti.adapters.sqlite_jobs import SQLiteJobRepository
from xti.adapters.sqlite_public_notices import read_public_notice_snapshot
from xti.adapters.sqlite_news import read_news_catalog
from xti.adapters.sqlite_mentions import read_mentions_catalog
from xti.adapters.sqlite_warninglists import read_warninglists
from xti.adapters.sqlite_ransomlook_claims import SQLiteRansomLookClaimRepository
from xti.adapters.sqlite_ransomware_claims import SQLiteRansomwareClaimRepository
from xti.adapters.sqlite_surface_candidates import SQLiteSurfaceCandidateRepository
from xti.adapters.theharvester_archive import TheHarvesterArchiveSource
from xti.adapters.tool_installation import (
    ToolInstallationError, pending_installation, tool_installation_lock,
    brand_installation_lock, brand_installation_pending,
)
from xti.domain.assets import ValidationError, normalize_domain
from xti.domain.component_pins import HARVESTER_PIN, MAIGRET_PIN, SHERLOCK_PIN
from xti.domain.cti_attack import ATTACK_SOURCE_NAME
from xti.domain.cti_feeds import CTI_FEED_POLICIES
from xti.domain.public_notices import HIBP_ATTRIBUTION, HIBP_LICENSE, HIBP_SOURCE_URL
from xti.domain.news import NEWS_SOURCES
from xti.domain.warninglists import POLICIES as WARNINGLIST_POLICIES
from xti.domain.source_readiness import SourceReadinessEvidence, SourceReadinessSnapshot
from xti.ports.discovery import SourceError


MAIGRET_SHA = MAIGRET_PIN.catalog_sha256
MAIGRET_COMMIT = MAIGRET_PIN.commit
MAIGRET_VERSION = MAIGRET_PIN.version
SHERLOCK_SHA = SHERLOCK_PIN.catalog_sha256
SHERLOCK_COMMIT = SHERLOCK_PIN.commit
SHERLOCK_VERSION = SHERLOCK_PIN.version


def _row(identifier, label, scope, command, *, notes=(), installation="builtin"):
    return SourceReadinessEvidence(
        identifier, label, scope, installation, "never", None, None, None,
        command, tuple(notes),
    )


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Duplicate JSON key")
        result[key] = value
    return result


class LocalSourceInstallationInspector:
    """Check pinned metadata/catalogs without importing or executing third-party code."""

    def __init__(self, project_dir: Path):
        self.project_dir = Path(project_dir)

    def inspect(self, source: str) -> tuple[str, str | None]:
        if source == HARVESTER_PIN.identifier:
            checkout = self.project_dir / ".tools" / HARVESTER_PIN.identifier
            executable = checkout / ".venv" / "bin" / HARVESTER_PIN.package
            if pending_installation(checkout.parent):
                return "invalid", "theHarvester kurulumu tamamlanmamış; ./scripts/setup-harvester --recover çalıştır."
            if not checkout.exists():
                return "missing", "theHarvester ayrı ortamı kurulmamış."
            try:
                with tool_installation_lock(checkout.parent, exclusive=False, create=False):
                    TheHarvesterArchiveSource._verify_checkout(checkout, executable)
                    if not os.access(executable, os.X_OK):
                        raise SourceError("theHarvester çalıştırıcısı çalıştırılabilir değil.")
            except (OSError, SourceError, ToolInstallationError) as error:
                return "invalid", str(error)
            return "ready", None
        if source not in {MAIGRET_PIN.identifier, SHERLOCK_PIN.identifier}:
            raise ValueError("Unknown local source tool")
        if brand_installation_pending(self.project_dir):
            return "invalid", "Marka ortamı kurtarma bekliyor; ./scripts/setup-brand --recover çalıştır."
        if not self.project_dir.exists():
            return "missing", "Proje marka araç ortamı kurulmamış."
        try:
            with brand_installation_lock(self.project_dir, exclusive=False, create=False):
                if brand_installation_pending(self.project_dir):
                    return "invalid", "Marka ortamı kurtarma bekliyor; ./scripts/setup-brand --recover çalıştır."
                return self._inspect_brand(source)
        except ToolInstallationError as error:
            return "invalid", str(error)

    def _inspect_brand(self, source: str) -> tuple[str, str | None]:
        tools = {
            pin.identifier: (
                pin.distribution, pin.package, pin.version, pin.commit,
                pin.repository, pin.catalog_size, digest,
            )
            for pin, digest in ((MAIGRET_PIN, MAIGRET_SHA), (SHERLOCK_PIN, SHERLOCK_SHA))
        }
        if source not in tools:
            raise ValueError("Unknown local source tool")
        venv = self.project_dir / ".venv"
        if venv.is_symlink() or (os.path.lexists(venv) and not venv.is_dir()):
            return "invalid", "Proje .venv ortamı gerçek bir dizin olmalı; değiştirilmedi."
        if not venv.exists():
            return "missing", "Proje marka araç ortamı kurulmamış."
        name, package, version, commit, repository, size, digest = tools[source]
        try:
            if not os.access(venv / "bin" / "python", os.X_OK):
                raise ValueError("Sanal ortam Python çalıştırıcısı yok.")
            locations = tuple(venv.glob("lib/python*/site-packages"))
            matches = [
                item for item in distributions(path=[str(path) for path in locations])
                if str(item.metadata.get("Name", "")).lower().replace("_", "-") == name
            ]
            if not matches:
                return "missing", f"{source} paketi proje ortamında kurulu değil."
            if len(matches) != 1 or matches[0].version != version:
                raise ValueError("Kurulu paket sürümü veya tekilliği uyuşmuyor.")
            installed = matches[0]
            location = Path(installed.locate_file("")).resolve()
            if not location.is_relative_to(venv.resolve()):
                raise ValueError("Paket proje ortamının dışında.")
            raw = installed.read_text("direct_url.json")
            if raw is None or len(raw) > 16_384:
                raise ValueError("Git kurulum kaydı yok veya boyutu geçersiz.")
            direct = json.loads(raw, object_pairs_hook=_unique_object)
            vcs = direct.get("vcs_info") if isinstance(direct, dict) else None
            if (
                not isinstance(direct, dict) or direct.get("url") != repository
                or not isinstance(vcs, dict) or vcs.get("vcs") != "git"
                or vcs.get("commit_id") != commit or vcs.get("requested_revision") != commit
            ):
                raise ValueError("Kurulu kaynak commit'i incelenen sürümle uyuşmuyor.")
            catalog = Path(installed.locate_file(f"{package}/resources/data.json"))
            metadata = catalog.lstat()
            if (
                not stat.S_ISREG(metadata.st_mode) or stat.S_ISLNK(metadata.st_mode)
                or metadata.st_size != size
                or not catalog.resolve().is_relative_to(venv.resolve())
                or hashlib.sha256(catalog.read_bytes()).hexdigest() != digest
            ):
                raise ValueError("Paketli site kataloğu doğrulanamadı.")
            if source == "maigret" and not os.access(venv / "bin" / "maigret", os.X_OK):
                raise ValueError("Maigret çalıştırıcısı yok.")
        except (OSError, ValueError, TypeError, KeyError, UnicodeError) as error:
            return "invalid", str(error)
        return "ready", None


class SQLiteSourceReadinessRepository:
    def __init__(self, database: Path, project_dir: Path | None = None) -> None:
        self.database = Path(database)
        self.storage = SQLiteAssetRepository(database)
        self.installations = LocalSourceInstallationInspector(
            project_dir or Path(__file__).resolve().parents[3]
        )

    def _empty_rows(self, domain):
        target = domain or "DOMAIN"
        scope = f"Kök: {domain}" if domain else "Tüm kökler içindeki son çalışma"
        rows = [
            _row(f"scan:{key}", f"{key} marka araması", scope,
                 f"./xti scan {target} --source {key}")
            for key in ("crt.sh", "urlscan")
        ]
        rows.extend(
            _row(f"surface:{key}", f"{key} alt alan adı keşfi", scope,
                 f"./xti surface discover {target} --source {key}")
            for key in ("crt.sh", "theharvester")
        )
        rows.extend(
            _row(f"social:{key}", label, "Tüm sosyal izlemeler içindeki son kayıt",
                 "./xti brand watch-add --help", notes=(
                     "Yazmasız username-preview aramaları bu geçmişe dahil değildir.",
                     "Kurulum denetimi paket/commit/kataloğu okur; canlı platform erişimini ölçmez.",
                 ))
            for key, label in (("maigret", "Maigret"), ("sherlock", "Sherlock"))
        )
        rows.extend(
            _row(f"ioc:{key}", policy.label, "Yerel IOC beslemesi",
                 f"./xti ioc sync --source {key}")
            for key, policy in CTI_FEED_POLICIES.items()
        )
        rows.extend(
            _row(f"ransomware:{key}", label, "Yerel iddia kaynağı geçmişi",
                 f"./xti ransomware refresh --source {key}")
            for key, label in (("threatcluster", "ThreatCluster"), ("ransomlook", "RansomLook"))
        )
        rows.append(_row(
            "notices:hibp", "Have I Been Pwned kamu olay kataloğu",
            "Ortak kamu olay kataloğu; domain filtresinden bağımsız", "./xti notices refresh",
            notes=(
                HIBP_ATTRIBUTION, HIBP_LICENSE, HIBP_SOURCE_URL,
                "Anahtarsız kamu metadata kataloğu; e-posta, parola veya sızıntı içeriği sorgusu değildir.",
                "Kayıt sayısı son başarılı kataloğun toplamıdır; bu domainin eşleşme sayısı değildir.",
                "Kaynak hatası önceki başarılı kataloğu silmez; bu ekran internet erişimini denemez.",
            ),
        ))
        rows.append(replace(_row(
            "cti:attack", "MITRE ATT&CK", "Son kayıtlı CTI kanıtı",
            "./xti cti attack-sync", notes=(
                "ATT&CK için başarısız deneme ve tam senkron geçmişi tutulmuyor.",
                "Son başarı alanı yalnız son kayıtlı kaynak kanıtının zamanıdır; boş başarılı senkron görünmeyebilir.",
            ),
        ), latest_status="unknown"))
        rows.extend(_row(
            f"news:{source.key}", source.name, "Ortak haber kaynağı; domain filtresinden bağımsız",
            f"./xti news refresh --source {source.key}",
            notes=(source.attribution, source.url,
                   "Yalnız saklanan kaynak geçmişi gösterilir; canlı internet erişimi denenmez.",
                   "Kayıt sayısı saklanan son bilinen haberlerdir; seçilen domainin eşleşme sayısı değildir.",
                   "Akıştan düşen eski haber korunur; başarısız deneme önceki kanıtı silmez."),
        ) for source in NEWS_SOURCES)
        rows.append(_row(
            'mentions:tavily', 'Tavily firma ve tedarikçi içerik araması',
            'Açıkça seçilen hedeflerin arama geçmişi; domain filtresinden bağımsız',
            './xti mentions status',
            notes=(
                'builtin yalnız adaptörün mevcut olduğunu belirtir; API anahtarı, hesap bakiyesi veya canlı erişim doğrulanmaz.',
                'Son deneme/başarı farklı firma veya sorguya ait olabilir; her kaydın özgün arama kapsamını inceleyin.',
                'Kayıt sayısı saklanan son bilinen adaylardır; bütün internetin veya bir firmanın toplam haber sayısı değildir.',
                'Ücretsiz kredi kullanılabilir; hesap kotası ve ücretli kullanım ayarları Tavily tarafından yönetilir.',
                'Arama sonucu adayı tehdit veya ihlal doğrulaması değildir.',
            ),
        ))
        rows.extend(_row(
            f'warninglist:{policy.id}', f'MISP: {policy.label}',
            'Seçili çalışma alanının referans listesi; domain filtresinden bağımsız',
            f'./xti warninglists sync --list {policy.id}',
            notes=('Liste eşleşmesi güvenli kararı veya otomatik istisna değildir.',
                   'Güncellik liste içeriğinin değişim tarihi değil, son geçerli indirme zamanıdır.'),
        ) for policy in WARNINGLIST_POLICIES.values())
        for index, row in enumerate(rows):
            tool = row.identifier.split(":", 1)[1]
            if row.identifier in {"social:maigret", "social:sherlock", "surface:theharvester"}:
                state, error = self.installations.inspect(tool)
                command = row.next_command
                if state != "ready":
                    command = ("./scripts/setup-harvester" if tool == "theharvester"
                               else "./scripts/setup-brand")
                rows[index] = replace(
                    row, installation=state, next_command=command,
                    notes=(*row.notes, *((error,) if error else ())),
                )
        return {row.identifier: row for row in rows}

    @staticmethod
    def _record(row, latest, success, *, attempt_field="started_at", count_field=None):
        if latest is None:
            return row
        return replace(
            row, latest_status=latest.status,
            last_attempt_at=getattr(latest, attempt_field),
            last_success_at=(getattr(success, "finished_at", None) or
                             getattr(success, "checked_at", None)) if success else None,
            error=latest.error,
            record_count=getattr(latest, count_field) if count_field else None,
        )

    def snapshot(self, *, domain: str | None = None) -> SourceReadinessSnapshot:
        if domain is not None:
            domain = normalize_domain(domain)
        rows = self._empty_rows(domain)
        if not self.database.exists() and not self.database.is_symlink():
            return SourceReadinessSnapshot("not_initialized", tuple(rows.values()))
        with self.storage._connection(readonly=True) as connection:
            connection.execute("BEGIN")
            if domain and connection.execute(
                "SELECT id FROM assets WHERE value=?", (domain,),
            ).fetchone() is None:
                raise ValidationError("Kök adres kayıtlı değil; önce assets add ile ekleyin.")
            self._scan_rows(connection, rows, domain)
            self._surface_rows(connection, rows, domain)
            self._social_rows(connection, rows)
            self._claim_rows(connection, rows)
            self._public_notice_row(connection, rows)
            self._news_rows(connection, rows)
            self._mention_row(connection, rows)
            self._attack_row(connection, rows)
            for state in read_warninglists(connection):
                key = f'warninglist:{state.list_id}'
                row = self._record(rows[key], state.latest_run, state.successful_run)
                rows[key] = replace(row, record_count=len(state.snapshot.entries) if state.snapshot else None)
            for item in connection.execute(
                "SELECT provider, not_before, recorded_at, reason FROM provider_cooldowns"
            ):
                cooldown = SQLiteCooldownRepository._row(item)
                for key in (f"scan:{cooldown.provider}", f"surface:{cooldown.provider}"):
                    if key in rows:
                        rows[key] = replace(rows[key], cooldown_until=cooldown.not_before)
            connection.rollback()
        # Feed status reuses the existing complete source/history audit. Each
        # feed read is independent; this overview is not a cross-source snapshot.
        for key, policy in CTI_FEED_POLICIES.items():
            repository = SQLiteCtiFeedRepository(self.database, policy)
            status = repository.status(run_limit=100)
            complete = next((run for run in status.recent_runs if run.status == "complete"), None)
            if complete is None and status.latest_run is not None:
                with self.storage._connection(readonly=True) as connection:
                    result = connection.execute(
                        f"SELECT {FEED_RUN_SELECT} FROM cti_feed_runs "
                        "WHERE source_name=? AND status='complete' AND sequence<=? "
                        "ORDER BY sequence DESC LIMIT 1",
                        (policy.source_name, status.latest_run.sequence),
                    ).fetchone()
                    complete = repository._run(result) if result else None
            rows[f"ioc:{key}"] = self._record(
                rows[f"ioc:{key}"], status.latest_run, complete, count_field="indicator_count",
            )
        return SourceReadinessSnapshot("ready", tuple(rows.values()))

    def _scan_rows(self, connection, rows, domain):
        for provider in ("crt.sh", "urlscan"):
            clause = " AND EXISTS(SELECT 1 FROM json_each(j.targets) WHERE value=?)" if domain else ""
            params = (provider, domain) if domain else (provider,)
            def select(success=False, targets=None):
                target_clause = " AND j.targets=?" if targets is not None else ""
                parameters = (*params, json.dumps(targets, separators=(",", ":"))) if targets is not None else params
                found = connection.execute(
                    "SELECT a.id FROM scan_attempts a JOIN scan_jobs j ON j.id=a.job_id "
                    "WHERE j.provider=?" + clause +
                    (" AND a.status='complete'" if success else "") +
                    target_clause + " ORDER BY a.rowid DESC LIMIT 1", parameters,
                ).fetchone()
                if not found:
                    return None, None
                attempt = SQLiteJobRepository._get_attempt(connection, found[0])
                details = SQLiteJobRepository._details(connection, attempt.job_id)
                return attempt, details.job
            latest, job = select()
            success, _ = select(True, job.targets) if job else (None, None)
            row = self._record(rows[f"scan:{provider}"], latest, success)
            if latest:
                errors = tuple(query.error for query in latest.queries if query.error)
                notes = tuple(note for query in latest.queries for note in query.coverage_notes)
                row = replace(
                    row, scope="Son çalışma: " + ", ".join(job.targets),
                    error=latest.error or ("; ".join(errors) if errors else None),
                    record_count=sum(query.record_count for query in latest.queries),
                    notes=(*row.notes, *notes),
                    next_command=f"./xti scan {domain or job.targets[0]} --source {provider}",
                )
            rows[row.identifier] = row

    def _surface_rows(self, connection, rows, domain):
        repository = SQLiteSurfaceCandidateRepository(self.database)
        for provider in ("crt.sh", "theharvester"):
            clause = " AND asset_value=?" if domain else ""
            params = (provider, domain) if domain else (provider,)
            def select(success=False, asset_id=None):
                asset_clause = " AND asset_id=?" if asset_id is not None else ""
                parameters = (*params, asset_id) if asset_id is not None else params
                found = connection.execute(
                    "SELECT id FROM surface_discovery_runs WHERE provider=?" + clause +
                    (" AND status='complete'" if success else "") +
                    asset_clause + " ORDER BY sequence DESC LIMIT 1", parameters,
                ).fetchone()
                return repository._run(repository._run_row(connection, found[0])) if found else None
            latest = select()
            success = select(True, latest.asset_id) if latest else None
            row = self._record(rows[f"surface:{provider}"], latest, success, count_field="candidate_count")
            if latest:
                row = replace(row, scope=f"Son kök: {latest.asset_value}", notes=(*row.notes, *latest.warnings))
                if row.installation in {"builtin", "ready"}:
                    row = replace(row, next_command=f"./xti surface discover {latest.asset_value} --source {provider}")
            rows[row.identifier] = row

    def _social_rows(self, connection, rows):
        watches, _events, runs, _items = SQLiteBrandUsernameWatchRepository._audit(connection)
        for provider in ("maigret", "sherlock"):
            matching = sorted((run for run in runs.values()
                               if watches[run.watch_id].source_key == provider), key=lambda run: run.sequence)
            latest = matching[-1] if matching else None
            complete = next((run for run in reversed(matching)
                             if latest and run.status == "complete"
                             and run.watch_id == latest.watch_id
                             and run.definition_sha256 == latest.definition_sha256), None)
            row = self._record(rows[f"social:{provider}"], latest, complete,
                               attempt_field="recorded_at", count_field="found_count")
            if latest:
                watch = watches[latest.watch_id]
                row = replace(row, scope=f"Son izleme: {watch.display_name} ({latest.username})",
                              notes=(*row.notes, f"Raporlanmayan platform: {latest.unreported_count}; hesap yokluğu anlamına gelmez."))
                if row.installation == "ready":
                    row = replace(row, next_command=f"./xti brand watch-run {watch.id}" if watch.active
                                  else "./xti brand watch-list")
            elif row.installation == "ready":
                watch = next((watch for watch in watches.values()
                              if watch.source_key == provider and watch.active), None)
                if watch:
                    row = replace(row, next_command=f"./xti brand watch-run {watch.id}")
            rows[row.identifier] = row

    def _claim_rows(self, connection, rows):
        for provider, repository in (
            ("threatcluster", SQLiteRansomwareClaimRepository),
            ("ransomlook", SQLiteRansomLookClaimRepository),
        ):
            runs, _items = repository._audit(connection)
            latest = runs[-1] if runs else None
            complete = next((run for run in reversed(runs) if run.status == "complete"), None)
            key = f"ransomware:{provider}"
            rows[key] = self._record(rows[key], latest, complete, count_field="claim_count")

    def _attack_row(self, connection, rows):
        repository = SQLiteCtiKnowledgeRepository(self.database)
        repository._audit_attack_source(connection)
        event = connection.execute(
            "SELECT e.recorded_at FROM cti_entity_assertion_events e "
            "JOIN cti_entity_assertions a ON a.id=e.assertion_id "
            "WHERE a.source_name=? ORDER BY e.rowid DESC LIMIT 1", (ATTACK_SOURCE_NAME,),
        ).fetchone()
        count = connection.execute(
            "SELECT COUNT(*) FROM cti_entity_assertions WHERE source_name=? AND active=1",
            (ATTACK_SOURCE_NAME,),
        ).fetchone()[0]
        rows["cti:attack"] = replace(rows["cti:attack"], last_success_at=event[0] if event else None,
                                      record_count=count if event else None)

    def _public_notice_row(self, connection, rows):
        snapshot = read_public_notice_snapshot(connection)
        complete = snapshot.latest_complete_run
        row = self._record(rows["notices:hibp"], snapshot.latest_run, complete)
        rows["notices:hibp"] = replace(row, record_count=complete.notice_count if complete else None)

    def _news_rows(self, connection, rows):
        for status in read_news_catalog(connection).sources:
            key = "news:" + status.source.key
            row = self._record(rows[key], status.latest_run, status.latest_complete_run)
            rows[key] = replace(row, record_count=status.article_count if status.latest_complete_run else None)

    def _mention_row(self, connection, rows):
        catalog = read_mentions_catalog(connection)
        latest = catalog.runs[-1] if catalog.runs else None
        success = next((run for run in reversed(catalog.runs) if run.status == 'complete'), None)
        row = self._record(rows['mentions:tavily'], latest, success)
        rows['mentions:tavily'] = replace(row, record_count=len(catalog.records) if success else None)
