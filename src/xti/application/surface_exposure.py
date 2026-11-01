"""Classify stored surface evidence without claiming vulnerabilities."""

from collections.abc import Callable
from datetime import datetime, timedelta, timezone

from xti.domain.assets import Asset, ValidationError, normalize_domain
from xti.domain.priority import parse_timestamp
from xti.domain.surface import SurfaceDiscoveryRun
from xti.domain.surface_exposure import (
    SurfaceExposureCandidate,
    SurfaceExposureCoverage,
    SurfaceExposureReport,
)
from xti.domain.surface_freshness import SurfaceFreshnessSnapshot
from xti.ports.assets import AssetRepository
from xti.ports.surface_freshness import SurfaceFreshnessRepository


class SurfaceExposureService:
    """Produce review candidates from the latest stored evidence only."""

    def __init__(
        self, assets: AssetRepository, repository: SurfaceFreshnessRepository, *,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self.assets = assets
        self.repository = repository
        self.clock = clock or (lambda: datetime.now(timezone.utc))

    def _asset(self, value: str) -> Asset:
        normalized = normalize_domain(value)
        for asset in self.assets.list():
            if asset.value == normalized:
                return asset
        raise ValidationError("Adres kayıtlı değil. Önce './xti assets add' kullan.")

    def _now(self) -> datetime:
        value = self.clock()
        try:
            if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
                raise ValueError("timezone required")
            return value.astimezone(timezone.utc)
        except (TypeError, ValueError, OverflowError) as error:
            raise ValidationError("Maruziyet değerlendirme zamanı geçersiz.") from error

    @staticmethod
    def _freshness(recorded_at: str, now: datetime, stale_after_hours: int) -> str:
        recorded = parse_timestamp(recorded_at)
        if recorded is None or recorded > now:
            return "clock_error"
        return (
            "current"
            if now - recorded < timedelta(hours=stale_after_hours)
            else "stale"
        )

    @classmethod
    def _coverage(
        cls, check_type: str, check, quality: str, now: datetime,
        stale_after_hours: int, next_command: str,
    ) -> SurfaceExposureCoverage:
        if check is None:
            return SurfaceExposureCoverage(
                check_type, "not_checked", None, None,
                "Bu kanıt ailesi için kayıtlı kontrol yok.", next_command,
            )
        freshness = cls._freshness(check.recorded_at, now, stale_after_hours)
        if freshness == "clock_error":
            status = "clock_error"
            reason = "Kanıt zamanı okunamıyor veya gelecekte; sonuç güvenle yaşlandırılamadı."
        elif quality != "complete":
            status = quality
            reason = (
                "Son kontrol başarısız; veri yokluğu veya güvenli durum kanıtlanmadı."
                if quality == "failed"
                else "Son kontrol kısmi; eksik bölüm tamamlanmış sayılmadı."
            )
        else:
            status = freshness
            reason = (
                f"Son kanıt {stale_after_hours} saatlik aralıkta."
                if freshness == "current"
                else f"Son kanıt en az {stale_after_hours} saat önce kaydedilmiş."
            )
        return SurfaceExposureCoverage(
            check_type, status, check.id, check.recorded_at, reason,
            None if status == "current" else next_command,
        )

    @classmethod
    def _discovery_coverage(
        cls, run, now: datetime, stale_after_hours: int, next_command: str,
    ) -> SurfaceExposureCoverage:
        if run is None:
            return SurfaceExposureCoverage(
                "passive_discovery", "not_checked", None, None,
                "Bu kök için kayıtlı pasif keşif çalışması yok.", next_command,
            )
        freshness = cls._freshness(run.finished_at, now, stale_after_hours)
        found = run.candidate_count > 0
        if freshness == "clock_error":
            status = "clock_error"
            reason = "Çalışma zamanı okunamıyor veya gelecekte; sonuç yaşlandırılamadı."
        elif run.status == "failed":
            status = "failed"
            reason = (
                "Pasif kaynak çalışmadı; aday görülmemesi boş veya güvenli sonuç değildir."
            )
        elif run.status == "partial":
            status = "partial"
            reason = (
                f"Kısmi kaynak yanıtında {run.candidate_count} aday görüldü; sonuç eksik olabilir."
                if found else
                "Kısmi kaynak yanıtında aday görülmedi; boş sonuç doğrulanmış sayılmaz."
            )
        else:
            status = freshness
            result = (
                f"Kaynak sorgusu tamamlandı ve {run.candidate_count} aday görüldü."
                if found else
                "Kaynak sorgusu tamamlandı; yalnız bu kaynak yanıtında aday görülmedi."
            )
            reason = (
                result if freshness == "current" else
                f"{result} Kanıt en az {stale_after_hours} saat önce kaydedilmiş."
            )
        return SurfaceExposureCoverage(
            "passive_discovery", status, run.id, run.finished_at, reason,
            None if status == "current" else next_command,
        )

    @staticmethod
    def _web_quality(check) -> str:
        if check.result.dns_status in {"failed", "blocked"}:
            return "failed"
        return "partial" if check.result.errors else "complete"

    @staticmethod
    def _mail_quality(check) -> str:
        statuses = (
            check.result.mx_status, check.result.spf_status, check.result.dmarc_status,
        )
        if all(status == "failed" for status in statuses):
            return "failed"
        return "partial" if check.result.errors else "complete"

    @staticmethod
    def _service_quality(check) -> str:
        if check.result.dns_status != "resolved":
            return "failed"
        return (
            "partial"
            if any(item.state == "unknown" for item in check.result.ports)
            else "complete"
        )

    @staticmethod
    def _cname_quality(check) -> str:
        if check.result.alias_status == "failed" or check.result.target_status == "failed":
            return "failed"
        return "complete"

    @classmethod
    def _web_candidates(
        cls, check, now: datetime, stale_after_hours: int,
    ) -> list[SurfaceExposureCandidate]:
        if check is None or check.result.tls_status != "failed":
            return []
        freshness = cls._freshness(check.recorded_at, now, stale_after_hours)
        return [SurfaceExposureCandidate(
            candidate_type="tls_connection_or_validation_issue",
            category="web_transport",
            title="TLS bağlantı veya doğrulama sorunu adayı",
            summary=(
                "Son sınırlı HTTPS kontrolü TLS aşamasını tamamlayamadı; "
                "nedenin sertifika, ağ veya geçici erişim sorunu olduğu henüz ayrılmadı."
            ),
            evidence_level="inconclusive",
            evidence_freshness=freshness,
            evidence_id=check.id,
            recorded_at=check.recorded_at,
            facts=(
                f"DNS durumu: {check.result.dns_status}",
                f"TLS durumu: {check.result.tls_status}",
                f"HTTPS durumu: {check.result.http_status}",
            ),
            limitations=(
                "Bu sonuç sertifika hatasını, kesintiyi veya zafiyeti tek başına kanıtlamaz.",
                "İçerik indirilmedi ve doğrulamasız TLS bağlantısı kurulmadı.",
            ),
            next_step="Sınırlı web kontrolünü tekrarla; sürerse sertifika ve hizmet sahibini elle incele.",
        )]

    @classmethod
    def _mail_candidates(
        cls, check, now: datetime, stale_after_hours: int,
    ) -> list[SurfaceExposureCandidate]:
        if check is None:
            return []
        result = check.result
        accepts_mail = (
            result.mx_status == "present" and result.mx_records != ("0 .",)
        )
        if not accepts_mail:
            return []
        freshness = cls._freshness(check.recorded_at, now, stale_after_hours)
        candidates: list[SurfaceExposureCandidate] = []

        def add(kind: str, title: str, summary: str, facts: tuple[str, ...]) -> None:
            candidates.append(SurfaceExposureCandidate(
                candidate_type=kind,
                category="mail_configuration",
                title=title,
                summary=summary,
                evidence_level="observed",
                evidence_freshness=freshness,
                evidence_id=check.id,
                recorded_at=check.recorded_at,
                facts=facts,
                limitations=(
                    "Kayıt eksikliği tek başına ihlal, sömürü veya teslimat başarısızlığı değildir.",
                    "Politikanın kurum ihtiyacına uygunluğu insan incelemesi gerektirir.",
                ),
                next_step="Yetkili DNS yöneticisiyle beklenen e-posta politikasını doğrula.",
            ))

        if result.spf_status == "missing":
            add(
                "mail_spf_missing", "SPF kaydı eksikliği adayı",
                "MX kaydı bulunan domainin son kanıtında SPF politikası görülmedi.",
                (f"MX kaydı sayısı: {len(result.mx_records)}", "SPF durumu: missing"),
            )
        elif len(result.spf_records) > 1:
            add(
                "mail_spf_multiple", "Birden fazla SPF kaydı adayı",
                "Son DNS kanıtında birden fazla SPF politika kaydı görüldü.",
                (f"SPF kaydı sayısı: {len(result.spf_records)}",),
            )
        if result.dmarc_status == "missing":
            add(
                "mail_dmarc_missing", "DMARC kaydı eksikliği adayı",
                "MX kaydı bulunan domainin son kanıtında DMARC politikası görülmedi.",
                (f"MX kaydı sayısı: {len(result.mx_records)}", "DMARC durumu: missing"),
            )
        elif len(result.dmarc_records) > 1:
            add(
                "mail_dmarc_multiple", "Birden fazla DMARC kaydı adayı",
                "Son DNS kanıtında birden fazla DMARC politika kaydı görüldü.",
                (f"DMARC kaydı sayısı: {len(result.dmarc_records)}",),
            )
        return candidates

    @classmethod
    def _service_candidates(
        cls, check, now: datetime, stale_after_hours: int,
    ) -> list[SurfaceExposureCandidate]:
        if check is None or check.result.dns_status != "resolved":
            return []
        freshness = cls._freshness(check.recorded_at, now, stale_after_hours)
        candidates: list[SurfaceExposureCandidate] = []
        for item in check.result.ports:
            if item.state != "open" or item.port not in {22, 3389, 8080, 8443}:
                continue
            remote = item.port in {22, 3389}
            candidates.append(SurfaceExposureCandidate(
                candidate_type=(
                    f"remote_access_port_{item.port}"
                    if remote else f"alternate_web_port_{item.port}"
                ),
                category="service_reachability",
                title=(
                    f"İnternetten erişilebilen uzak erişim portu adayı: {item.port}/tcp"
                    if remote
                    else f"İnternetten erişilebilen alternatif web portu adayı: {item.port}/tcp"
                ),
                summary=(
                    "Sınırlı TCP kontrolünde kesin IP bu portta bağlantı kabul etti."
                ),
                evidence_level="observed",
                evidence_freshness=freshness,
                evidence_id=check.id,
                recorded_at=check.recorded_at,
                facts=(
                    f"Kesin IP: {check.result.checked_address}",
                    f"Port: {item.port}/tcp",
                    f"Yalnız kullanım ipucu: {item.service_hint}",
                ),
                limitations=(
                    "Açık TCP portu ürün, yönetim paneli, sürüm veya zafiyet kanıtı değildir.",
                    "Banner okunmadı, protokol komutu gönderilmedi ve oturum açılmadı.",
                ),
                next_step=(
                    "Bu erişimin gerekli olduğunu, kaynak kısıtını ve hizmet sahibini doğrula."
                ),
            ))
        return candidates

    @classmethod
    def _cname_candidates(
        cls, check, now: datetime, stale_after_hours: int,
    ) -> list[SurfaceExposureCandidate]:
        if (
            check is None
            or check.result.alias_status != "present"
            or check.result.target_status != "nxdomain"
        ):
            return []
        freshness = cls._freshness(check.recorded_at, now, stale_after_hours)
        chain = " → ".join(
            [check.result.chain[0].owner]
            + [hop.target for hop in check.result.chain]
        )
        return [SurfaceExposureCandidate(
            candidate_type="dangling_cname_target_nxdomain",
            category="dns_alias_configuration",
            title="Sarkan CNAME hedefi adayı",
            summary=(
                "Onaylı tam adresin CNAME zincirindeki terminal hedef, son genel DNS "
                "kanıtında NXDOMAIN döndürdü."
            ),
            evidence_level="inconclusive",
            evidence_freshness=freshness,
            evidence_id=check.id,
            recorded_at=check.recorded_at,
            facts=(
                f"CNAME zinciri: {chain}",
                f"Terminal hedef: {check.result.target}",
                "Terminal hedef durumu: nxdomain",
            ),
            limitations=(
                "NXDOMAIN, hedef adın bu genel DNS görünümünde bulunmadığını gösterir; "
                "kaynağın alınabilir olduğunu kanıtlamaz.",
                "Sağlayıcı hesabı, özel DNS görünümü, geçici kesinti ve sahiplik durumu "
                "bu kontrolle doğrulanmaz.",
                "Kaynak sahiplenilmedi, HTTP isteği yapılmadı ve exploit denenmedi.",
            ),
            next_step=(
                "DNS kaydının hâlâ gerekli olduğunu hizmet sahibiyle doğrula; kanıtı "
                "farklı zamanda tekrarla ve gereksizse yetkili DNS süreciyle kaldır."
            ),
        )]

    def show(
        self, asset_value: str, *, stale_after_hours: int = 24,
    ) -> SurfaceExposureReport:
        if type(stale_after_hours) is not int or not 1 <= stale_after_hours <= 8760:
            raise ValidationError("Maruziyet güncellik eşiği 1–8760 saat arasında olmalı.")
        asset = self._asset(asset_value)
        snapshot = self.repository.snapshot(asset.id, asset.value)
        if not isinstance(snapshot, SurfaceFreshnessSnapshot):
            raise ValidationError("Maruziyet görünümü beklenen biçimde değil.")
        if snapshot.asset_id != asset.id or snapshot.asset_value != asset.value:
            raise ValidationError("Maruziyet görünümü kayıtlı adresle uyuşmuyor.")
        if (
            snapshot.latest_discovery_run is not None
            and (
                not isinstance(snapshot.latest_discovery_run, SurfaceDiscoveryRun)
                or snapshot.latest_discovery_run.asset_id != asset.id
                or snapshot.latest_discovery_run.asset_value != asset.value
            )
        ):
            raise ValidationError("Pasif keşif kanıtı kayıtlı adresle uyuşmuyor.")
        now = self._now()

        web_quality = (
            "not_checked" if snapshot.latest_check is None
            else self._web_quality(snapshot.latest_check)
        )
        mail_quality = (
            "not_checked" if snapshot.latest_mail_check is None
            else self._mail_quality(snapshot.latest_mail_check)
        )
        service_quality = (
            "not_checked" if snapshot.latest_service_check is None
            else self._service_quality(snapshot.latest_service_check)
        )
        cname_quality = (
            "not_checked" if snapshot.latest_cname_check is None
            else self._cname_quality(snapshot.latest_cname_check)
        )
        commands = {
            "discovery": f"./xti surface discover {asset.value}",
            "web": f"./xti surface check {asset.value}",
            "mail": f"./xti surface mail check {asset.value}",
            "services": (
                f'./xti surface services check {asset.value} --address GENEL_IP '
                '--reason "Yetkili kesin IP"'
            ),
            "cname": f"./xti surface cname check {asset.value}",
        }
        coverage = (
            self._discovery_coverage(
                snapshot.latest_discovery_run, now, stale_after_hours,
                commands["discovery"],
            ),
            self._coverage(
                "web", snapshot.latest_check, web_quality, now, stale_after_hours,
                commands["web"],
            ),
            self._coverage(
                "mail", snapshot.latest_mail_check, mail_quality, now, stale_after_hours,
                commands["mail"],
            ),
            self._coverage(
                "services", snapshot.latest_service_check, service_quality, now,
                stale_after_hours, commands["services"],
            ),
            self._coverage(
                "subdomain_takeover", snapshot.latest_cname_check, cname_quality,
                now, stale_after_hours, commands["cname"],
            ),
            SurfaceExposureCoverage(
                "admin_panel_identification", "unsupported", None, None,
                "Sayfa gövdesi, başlık veya banner toplanmadığı için açık panel kimliği çıkarılamaz.",
            ),
        )
        candidates = tuple([
            *self._web_candidates(snapshot.latest_check, now, stale_after_hours),
            *self._mail_candidates(snapshot.latest_mail_check, now, stale_after_hours),
            *self._service_candidates(snapshot.latest_service_check, now, stale_after_hours),
            *self._cname_candidates(snapshot.latest_cname_check, now, stale_after_hours),
        ])
        scope_status = (
            "missing" if snapshot.scope is None
            else "active" if snapshot.scope.active else "revoked"
        )
        current_coverage_count = sum(item.status == "current" for item in coverage)
        attention_coverage_count = sum(
            item.status in {"stale", "partial", "failed", "not_checked", "clock_error"}
            for item in coverage
        )
        return SurfaceExposureReport(
            asset_id=asset.id,
            asset_value=asset.value,
            observed_at=now.isoformat(),
            stale_after_hours=stale_after_hours,
            scope_status=scope_status,
            candidate_count=len(candidates),
            stale_candidate_count=sum(
                item.evidence_freshness == "stale" for item in candidates
            ),
            clock_error_candidate_count=sum(
                item.evidence_freshness == "clock_error" for item in candidates
            ),
            categories=tuple(sorted({item.category for item in candidates})),
            candidates=candidates,
            coverage=coverage,
            notes=(
                "Aday, doğrulanmış zafiyet veya ihlal demek değildir; kanıt ve sınırlarıyla incelenir.",
                "Bu komut yalnız son kayıtlı kanıtları okur; internete bağlanmaz ve kayıt değiştirmez.",
                "Eksik, başarısız, eski veya desteklenmeyen kontrol güvenli sonuç sayılmaz.",
                "CNAME hedefinin NXDOMAIN olması alınabilirlik kanıtı değildir; takeover "
                "doğrulaması kaynak sahiplenme veya exploit işlemi yapmaz.",
            ),
            current_coverage_count=current_coverage_count,
            attention_coverage_count=attention_coverage_count,
            unsupported_coverage_count=sum(
                item.status == "unsupported" for item in coverage
            ),
            scope_next_command=(
                None if scope_status == "active" else
                f'./xti surface approve {asset.value} --reason "Yetkili alan adım"'
            ),
        )
