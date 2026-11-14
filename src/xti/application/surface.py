"""Explicit-scope DNS/TLS baselines without depending on storage or transport."""

from collections.abc import Callable
from datetime import datetime, timezone
import math
import time

from xti.domain.collection_history import CollectionOperationToken
from xti.domain.assets import Asset, ValidationError, normalize_domain
from xti.domain.discovery import SourceBatch
from xti.domain.enrichment import ProbeResult
from xti.domain.findings import DomainInput, ImportDocument
from xti.domain.overview import SurfaceOverview, SurfaceOverviewSnapshot, SurfaceRelation
from xti.domain.surface import (
    SurfaceCandidate,
    SurfaceCandidateDetails,
    SurfaceCandidateEvidence,
    SurfaceCheck,
    SurfaceDetails,
    SurfaceDiscoveryResult,
    SurfaceDiscoveryRun,
    SurfaceDiscoveryRunRequest,
    SURFACE_DISCOVERY_PROVIDERS,
    SurfaceWatchCycle,
    SurfaceWatchReport,
    SurfaceScope,
    SurfaceSummary,
)
from xti.ports.assets import AssetRepository
from xti.ports.discovery import DomainSource, SourceError
from xti.ports.enrichment import TargetProbe
from xti.ports.surface import (
    SurfaceCandidateRepository,
    SurfaceOverviewRepository,
    SurfaceRepository,
)


MAX_DISCOVERY_DOCUMENTS = 10_000
SURFACE_CANDIDATE_STATUSES = frozenset({"pending", "owned", "rejected"})


class SurfaceOverviewService:
    """Build a bounded relationship view from one stored-data snapshot."""

    def __init__(
        self, assets: AssetRepository, repository: SurfaceOverviewRepository,
    ) -> None:
        self.assets = assets
        self.repository = repository

    def _asset(self, value: str) -> Asset:
        normalized = normalize_domain(value)
        for asset in self.assets.list():
            if asset.value == normalized:
                return asset
        raise ValidationError("Adres kayıtlı değil. Önce './xti assets add' kullan.")

    @staticmethod
    def _relations(snapshot: SurfaceOverviewSnapshot) -> tuple[SurfaceRelation, ...]:
        root = snapshot.asset_value
        relations: list[SurfaceRelation] = []
        for candidate in snapshot.candidates:
            relations.append(SurfaceRelation(
                "discovered_subdomain", "domain", root, "domain", candidate.domain,
                "surface_candidate", candidate.id, candidate.last_seen_at,
                f"status={candidate.status}; sources={candidate.source_count}",
            ))

        check = snapshot.latest_check
        if check is not None:
            for address in check.result.addresses:
                relations.append(SurfaceRelation(
                    "resolves_to", "domain", root, "ip", address,
                    "surface_check", check.id, check.recorded_at, None,
                ))
            certificate = check.result.certificate
            if certificate is not None:
                certificate_node = f"sha256:{certificate.sha256}"
                relations.append(SurfaceRelation(
                    "presents_certificate", "domain", root, "certificate", certificate_node,
                    "surface_check", check.id, check.recorded_at,
                    f"subject={certificate.subject}; issuer={certificate.issuer}",
                ))
                for name in certificate.dns_names:
                    relations.append(SurfaceRelation(
                        "certificate_covers", "certificate", certificate_node,
                        "domain_pattern", name, "surface_check", check.id,
                        check.recorded_at, None,
                    ))

        mail_check = snapshot.latest_mail_check
        if mail_check is not None:
            for record in mail_check.result.mx_records:
                preference, exchange = record.split(" ", 1)
                if exchange != ".":
                    relations.append(SurfaceRelation(
                        "uses_mail_exchange", "domain", root, "domain", exchange,
                        "mail_dns_check", mail_check.id, mail_check.recorded_at,
                        f"preference={preference}",
                    ))
        service_check = snapshot.latest_service_check
        if service_check is not None and service_check.result.checked_address is not None:
            for item in service_check.result.ports:
                if item.state == "open":
                    relations.append(SurfaceRelation(
                        "offers_tcp_service", "domain", root, "tcp_service",
                        f"{service_check.result.checked_address}:{item.port}/tcp",
                        "service_scan_check", service_check.id, service_check.recorded_at,
                        item.service_hint,
                    ))
        return tuple(relations)

    def show(self, asset_value: str, *, candidate_limit: int = 20) -> SurfaceOverview:
        if type(candidate_limit) is not int or not 1 <= candidate_limit <= 100:
            raise ValidationError("Genel görünüm aday sınırı 1–100 arasında olmalı.")
        asset = self._asset(asset_value)
        snapshot = self.repository.snapshot(
            asset.id, asset.value, candidate_limit=candidate_limit,
        )
        if not isinstance(snapshot, SurfaceOverviewSnapshot):
            raise ValidationError("Dış yüzey genel görünümü beklenen biçimde değil.")
        if snapshot.asset_id != asset.id or snapshot.asset_value != asset.value:
            raise ValidationError("Dış yüzey genel görünümü kayıtlı adresle uyuşmuyor.")
        return SurfaceOverview(
            snapshot.asset_id, snapshot.asset_value, snapshot.scope,
            snapshot.latest_check, snapshot.latest_mail_check,
            snapshot.latest_service_check, snapshot.latest_discovery_run,
            snapshot.candidate_counts,
            snapshot.candidates, self._relations(snapshot),
        )


class SurfaceService:
    def __init__(
        self, assets: AssetRepository, repository: SurfaceRepository,
        probe: TargetProbe | None = None, clock: Callable[[], datetime] | None = None,
    ) -> None:
        self.assets = assets
        self.repository = repository
        self.probe = probe
        self.clock = clock or (lambda: datetime.now(timezone.utc))

    def _now(self) -> str:
        value = self.clock()
        if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
            raise ValidationError("Kapsam işlem zamanı geçersiz; kayıt yapılmadı.")
        return value.astimezone(timezone.utc).isoformat()

    @staticmethod
    def _reason(value: str) -> str:
        if (
            not isinstance(value, str) or value != value.strip()
            or not 1 <= len(value) <= 1000 or not value.isprintable()
        ):
            raise ValidationError("Kapsam gerekçesi 1–1000 görünür karakter olmalı.")
        return value

    def _asset(self, value: str) -> Asset:
        normalized = normalize_domain(value)
        for asset in self.assets.list():
            if asset.value == normalized:
                return asset
        raise ValidationError("Adres kayıtlı değil. Önce './xti assets add' kullan.")

    def approve(self, asset_value: str, reason: str) -> tuple[SurfaceScope, bool]:
        asset = self._asset(asset_value)
        return self.repository.activate(asset.id, asset.value, self._reason(reason), self._now())

    def revoke(self, asset_value: str, reason: str) -> SurfaceScope:
        asset = self._asset(asset_value)
        return self.repository.revoke(asset.id, self._reason(reason), self._now())

    def scope_for_check(self, asset_value: str) -> SurfaceScope:
        asset = self._asset(asset_value)
        details = self.repository.details(asset.id, history_limit=1)
        if not details.scope.active:
            raise ValidationError(
                "Bu adresin dış yüzey kapsamı etkin değil. Önce 'surface approve' kullan."
            )
        return details.scope

    def check(self, asset_value: str) -> SurfaceCheck:
        scope = self.scope_for_check(asset_value)
        if self.probe is None:
            raise ValidationError("Ağ kontrolü bu çalışma yolunda yapılandırılmadı.")
        result = self.probe.check(scope.asset_value)
        if not isinstance(result, ProbeResult) or result.domain != scope.asset_value:
            raise ValidationError("Dış yüzey kontrolü istenen adresle eşleşmiyor; kaydedilmedi.")
        return self.repository.append_check(scope.asset_id, result)

    def list(self, *, active_only: bool = True, limit: int = 100) -> tuple[SurfaceSummary, ...]:
        if type(active_only) is not bool or type(limit) is not int or not 1 <= limit <= 100:
            raise ValidationError("Dış yüzey liste sınırı 1–100 arasında olmalı.")
        return self.repository.list(active_only=active_only, limit=limit)

    def show(self, asset_value: str, *, history_limit: int = 20) -> SurfaceDetails:
        if type(history_limit) is not int or not 1 <= history_limit <= 100:
            raise ValidationError("Dış yüzey geçmiş sınırı 1–100 arasında olmalı.")
        asset = self._asset(asset_value)
        return self.repository.details(asset.id, history_limit=history_limit)


class SurfaceDiscoveryService:
    """Passive source discovery; it never connects to a discovered candidate."""

    def __init__(
        self, assets: AssetRepository, repository: SurfaceCandidateRepository,
        source: DomainSource | None = None, clock: Callable[[], datetime] | None = None,
    ) -> None:
        self.assets = assets
        self.repository = repository
        self.source = source
        self.clock = clock or (lambda: datetime.now(timezone.utc))

    def _now(self) -> str:
        value = self.clock()
        if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
            raise ValidationError("Pasif keşif zamanı geçersiz; kayıt yapılmadı.")
        return value.astimezone(timezone.utc).isoformat()

    @staticmethod
    def _reason(value: str) -> str:
        if (
            not isinstance(value, str) or value != value.strip()
            or not 1 <= len(value) <= 1000 or not value.isprintable()
        ):
            raise ValidationError("Aday karar gerekçesi 1–1000 görünür karakter olmalı.")
        return value

    @staticmethod
    def _error_message(value: object) -> str:
        raw = str(value)
        visible = "".join(
            character if character.isprintable() else f"\\u{ord(character):04x}"
            for character in raw
        )
        return (visible or "Pasif kaynak bilinmeyen bir hata verdi.")[:2000]

    def _asset(self, value: str) -> Asset:
        normalized = normalize_domain(value)
        for asset in self.assets.list():
            if asset.value == normalized:
                return asset
        raise ValidationError("Adres kayıtlı değil. Önce './xti assets add' kullan.")

    @staticmethod
    def _documents(batch: SourceBatch) -> tuple[ImportDocument, ...]:
        if not isinstance(batch, SourceBatch):
            raise ValidationError("Pasif kaynak beklenen yanıtı vermedi; kayıt yapılmadı.")
        documents = batch.documents
        if not isinstance(documents, tuple) or len(documents) > MAX_DISCOVERY_DOCUMENTS:
            raise ValidationError("Pasif keşif 10.000 kaynak kaydı sınırını aştı; kayıt yapılmadı.")
        if any(
            not isinstance(document, ImportDocument)
            or not isinstance(document.records, tuple)
            or any(not isinstance(record, DomainInput) for record in document.records)
            for document in documents
        ):
            raise ValidationError("Pasif kaynakta geçersiz kayıt bulundu; işlem durduruldu.")
        if (
            type(batch.skipped_names) is not int or batch.skipped_names < 0
            or type(batch.record_count) is not int or batch.record_count < 0
            or not isinstance(batch.warnings, tuple) or len(batch.warnings) > 100
            or any(
                not isinstance(item, str) or not 1 <= len(item) <= 1000
                or not item.isprintable() for item in batch.warnings
            )
        ):
            raise ValidationError("Pasif kaynağın kapsam özeti geçersiz; kayıt yapılmadı.")
        return documents

    def discover(
        self, asset_value: str, *, operation: CollectionOperationToken | None = None,
    ) -> SurfaceDiscoveryResult:
        asset = self._asset(asset_value)
        if self.source is None:
            raise ValidationError("Pasif keşif kaynağı bu çalışma yolunda yapılandırılmadı.")
        provider = getattr(self.source, "provider", "crt.sh")
        if provider not in SURFACE_DISCOVERY_PROVIDERS:
            raise ValidationError("Pasif keşif sağlayıcısı desteklenmiyor.")
        started_at = self._now()
        pattern = f"%.{asset.value}"
        source_url = self.source.search_url(pattern)
        try:
            batch = self.source.search(pattern)
        except SourceError as exc:
            error = self._error_message(exc)
            finished_at = self._now()
            _, run = self.repository.record_discovery(
                asset.id, asset.value, (), SurfaceDiscoveryRunRequest(
                    "failed", source_url, started_at, finished_at,
                    0, 0, 0, (), 0, error, provider,
                ),
                **({"operation": operation} if operation is not None else {}),
            )
            return SurfaceDiscoveryResult(
                asset.value, started_at, finished_at, "failed", source_url,
                0, 0, 0, (), 0, 0, 0, 0, (), error, run.id, provider,
            )
        try:
            documents = self._documents(batch)
            by_key: dict[tuple[str, str], SurfaceCandidateEvidence] = {}
            ignored = 0
            suffix = "." + asset.value
            for document in documents:
                if not isinstance(document.sha256, str):
                    raise ValidationError("Pasif kaynak özeti geçersiz; kayıt yapılmadı.")
                for record in document.records:
                    domain = normalize_domain(record.domain)
                    if domain == asset.value or not domain.endswith(suffix):
                        ignored += 1
                        continue
                    evidence = SurfaceCandidateEvidence(
                        domain=domain,
                        provider=provider,
                        source_name=document.source_name,
                        source_sha256=document.sha256,
                        raw_domain=record.raw_domain,
                        observed_at=record.observed_at,
                    )
                    key = (domain, document.sha256)
                    previous = by_key.get(key)
                    if previous is not None and previous != evidence:
                        raise ValidationError("Kaynak aynı pasif kanıt için çelişen veri döndürdü.")
                    by_key[key] = evidence
                    if len(by_key) > MAX_DISCOVERY_DOCUMENTS:
                        raise ValidationError("Pasif keşif 10.000 kanıt sınırını aştı; kayıt yapılmadı.")
        except ValidationError as exc:
            error = self._error_message(exc)
            finished_at = self._now()
            _, run = self.repository.record_discovery(
                asset.id, asset.value, (), SurfaceDiscoveryRunRequest(
                    "failed", source_url, started_at, finished_at,
                    0, 0, 0, (), 0, error, provider,
                ),
                **({"operation": operation} if operation is not None else {}),
            )
            return SurfaceDiscoveryResult(
                asset.value, started_at, finished_at, "failed", source_url,
                0, 0, 0, (), 0, 0, 0, 0, (), error, run.id, provider,
            )

        status = "partial" if batch.warnings or batch.skipped_names else "complete"
        finished_at = self._now()
        evidence = tuple(by_key[key] for key in sorted(by_key))
        saved, run = self.repository.record_discovery(
            asset.id, asset.value, evidence, SurfaceDiscoveryRunRequest(
                status, source_url, started_at, finished_at,
                batch.record_count, batch.skipped_names, ignored, batch.warnings,
                len({item.domain for item in evidence}), None, provider,
            ),
            **({"operation": operation} if operation is not None else {}),
        )
        return SurfaceDiscoveryResult(
            asset.value, started_at, finished_at, status, source_url,
            batch.record_count, batch.skipped_names, ignored, batch.warnings,
            saved.candidates_created, saved.candidates_existing,
            saved.evidence_created, saved.evidence_existing,
            tuple(sorted({item.domain for item in by_key.values()})), None, run.id,
            provider,
        )

    def list(
        self, asset_value: str, *, status: str | None = "pending", limit: int = 100,
    ) -> tuple[SurfaceCandidate, ...]:
        asset = self._asset(asset_value)
        if status is not None and status not in SURFACE_CANDIDATE_STATUSES:
            raise ValidationError("Aday durumu pending, owned veya rejected olmalı.")
        if type(limit) is not int or not 1 <= limit <= 500:
            raise ValidationError("Alt alan adı aday sınırı 1–500 arasında olmalı.")
        return self.repository.list_candidates(asset.id, status=status, limit=limit)

    def show(self, candidate_id: str, *, source_limit: int = 100) -> SurfaceCandidateDetails:
        if type(source_limit) is not int or not 1 <= source_limit <= 500:
            raise ValidationError("Kaynak kanıtı sınırı 1–500 arasında olmalı.")
        return self.repository.candidate_details(candidate_id, source_limit=source_limit)

    def decide(
        self, candidate_id: str, status: str, reason: str,
    ) -> tuple[SurfaceCandidate, bool]:
        if status not in SURFACE_CANDIDATE_STATUSES:
            raise ValidationError("Aday kararı pending, owned veya rejected olmalı.")
        return self.repository.decide_candidate(
            candidate_id, status, self._reason(reason), self._now(),
        )

    def runs(self, asset_value: str, *, limit: int = 20) -> tuple[SurfaceDiscoveryRun, ...]:
        asset = self._asset(asset_value)
        if type(limit) is not int or not 1 <= limit <= 100:
            raise ValidationError("Pasif keşif geçmiş sınırı 1–100 arasında olmalı.")
        return self.repository.list_discovery_runs(asset.id, limit=limit)

    def run(self, run_id: str) -> SurfaceDiscoveryRun:
        return self.repository.discovery_run(run_id)


class SurfaceWatchService:
    """Repeat passive discovery within explicit cycle and start-time budgets."""

    def __init__(
        self, discovery: SurfaceDiscoveryService, *,
        clock: Callable[[], datetime] | None = None,
        monotonic: Callable[[], float] = time.monotonic,
        sleeper: Callable[[float], None] = time.sleep,
    ) -> None:
        self.discovery = discovery
        self.clock = clock or (lambda: datetime.now(timezone.utc))
        self.monotonic = monotonic
        self.sleeper = sleeper

    @staticmethod
    def validate_limits(
        max_cycles: int, interval_seconds: int, max_duration_seconds: int,
    ) -> None:
        for value, minimum, maximum, message in (
            (max_cycles, 1, 1000, "Pasif izleme tur sayısı 1–1000 arasında olmalı."),
            (interval_seconds, 300, 86400,
             "Pasif izleme aralığı 300–86400 saniye arasında olmalı."),
            (max_duration_seconds, 1, 604800,
             "Pasif izleme süresi 1–604800 saniye arasında olmalı."),
        ):
            if type(value) is not int or not minimum <= value <= maximum:
                raise ValidationError(message)

    def _now(self) -> str:
        value = self.clock()
        try:
            if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
                raise ValueError("timezone required")
            return value.astimezone(timezone.utc).isoformat()
        except (TypeError, ValueError, OverflowError) as error:
            raise ValidationError("Pasif izleme zamanı geçersiz.") from error

    def _tick(self) -> float:
        value = self.monotonic()
        try:
            if type(value) not in (int, float) or not math.isfinite(value):
                raise ValueError("invalid monotonic clock")
            return float(value)
        except (TypeError, ValueError, OverflowError) as error:
            raise ValidationError("Pasif izleme süresini ölçen saat geçersiz.") from error

    def run(
        self, asset_value: str, *, max_cycles: int = 3,
        interval_seconds: int = 3600, max_duration_seconds: int = 86400,
        progress: Callable[[str], None] | None = None,
    ) -> SurfaceWatchReport:
        self.validate_limits(max_cycles, interval_seconds, max_duration_seconds)
        # Validate the registered root and configured source before time starts
        # and before any passive network request is made.
        self.discovery.list(asset_value, status=None, limit=1)
        if self.discovery.source is None:
            raise ValidationError("Pasif keşif kaynağı bu çalışma yolunda yapılandırılmadı.")
        normalized = normalize_domain(asset_value)
        started_at = self._now()
        started = self._tick()
        previous = started
        cycles: list[SurfaceWatchCycle] = []

        def elapsed() -> float:
            nonlocal previous
            current = self._tick()
            if current < previous or not math.isfinite(current - started):
                raise ValidationError(
                    "Pasif izleme süresini ölçen saat geriye gitti; izleme durduruldu."
                )
            previous = current
            return current - started

        stop_reason = "cycles"
        for cycle in range(1, max_cycles + 1):
            if elapsed() >= max_duration_seconds:
                stop_reason = "duration"
                break
            if progress:
                progress(f"Pasif keşif turu {cycle}/{max_cycles}: {normalized}")
            result = self.discovery.discover(normalized)
            cycles.append(SurfaceWatchCycle(
                cycle=cycle, run_id=result.run_id, status=result.status,
                started_at=result.started_at, finished_at=result.finished_at,
                candidate_count=len(result.candidate_domains),
                candidates_created=result.candidates_created,
                evidence_created=result.evidence_created, error=result.error,
            ))
            if progress:
                progress(
                    f"Pasif keşif turu {cycle}/{max_cycles} tamamlandı; "
                    f"durum: {result.status}."
                )
            if cycle == max_cycles:
                break
            wait_started = elapsed()
            if wait_started >= max_duration_seconds:
                stop_reason = "duration"
                break
            wait_until = min(wait_started + interval_seconds, max_duration_seconds)
            if progress:
                progress("Sonraki pasif keşif turu bekleniyor. Durdurmak için Ctrl+C.")
            while True:
                remaining = wait_until - elapsed()
                if remaining <= 0:
                    break
                self.sleeper(min(1.0, remaining))
            if elapsed() >= max_duration_seconds:
                stop_reason = "duration"
                break

        duration = elapsed()
        finished_at = self._now()
        statuses = tuple(item.status for item in cycles)
        return SurfaceWatchReport(
            asset_value=normalized, planned_cycles=max_cycles,
            completed_cycles=len(cycles), complete=statuses.count("complete"),
            partial=statuses.count("partial"), failed=statuses.count("failed"),
            candidates_created=sum(item.candidates_created for item in cycles),
            evidence_created=sum(item.evidence_created for item in cycles),
            started_at=started_at, finished_at=finished_at, elapsed_seconds=duration,
            stop_reason=stop_reason, cycles=tuple(cycles),
            notes=(
                "Her tamamlanan tur ayrı ve kalıcı bir pasif keşif çalışmasıdır.",
                "Süre sınırı yeni tur başlatmayı durdurur; başlamış kaynak sorgusu tamamlanırken toplam süre aşılabilir.",
                "Bu izleme adaylara DNS, TLS veya HTTPS isteği göndermez ve sahiplik kararı vermez.",
            ),
            provider=getattr(self.discovery.source, "provider", "crt.sh"),
        )
