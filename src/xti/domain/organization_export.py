"""Complete organization report exports with explicit resource boundaries."""

from dataclasses import dataclass

from xti.domain.assets import ValidationError
from xti.domain.organization_report import OrganizationReport
from xti.domain.public_notice_watches import PublicNoticeWatchRunReport


MAX_EXPORT_TARGETS = 1_000
MAX_EXPORT_RECORDS = 50_000
MAX_EXPORT_BYTES = 32 * 1024 * 1024


class OrganizationExportPublicationError(RuntimeError):
    def __init__(self, path: str) -> None:
        self.path = path
        super().__init__("Raporun içeriği yazıldı; klasöre kalıcı kaydı doğrulanamadı. "
                         "Dosya mevcut olabilir: " + path)


@dataclass(frozen=True, slots=True)
class OrganizationExportSnapshot:
    report: OrganizationReport
    public_notice_watch_runs: tuple[PublicNoticeWatchRunReport, ...] = ()


@dataclass(frozen=True, slots=True)
class OrganizationExportFile:
    path: str
    byte_count: int
    sha256: str


@dataclass(frozen=True, slots=True)
class OrganizationExportResult:
    organization_id: str
    organization_name: str
    observed_at: str
    target_count: int
    record_count: int
    public_notice_watch_run_count: int
    file: OrganizationExportFile


def export_record_count(snapshot: OrganizationExportSnapshot) -> int:
    """Count scope links, section rows, watch events/runs and historical items."""
    report = snapshot.report
    count = len(report.scope.links) + sum(
        len(section.items) for target in report.targets for section in target.sections
    )
    if report.public_notice_watch is not None:
        count += len(report.public_notice_watch.events) + len(report.public_notice_watch.runs)
    if report.public_notice_case_links is not None:
        count += len(report.public_notice_case_links.items)
    return count + sum(len(run.items) + len(run.scope.members) for run in snapshot.public_notice_watch_runs)


def validate_complete_export(snapshot: OrganizationExportSnapshot, organization_id: str) -> None:
    """A paginated or differently scoped response must never be labelled complete."""
    if not isinstance(snapshot, OrganizationExportSnapshot):
        raise ValidationError("Kuruluş dışa aktarım sonucu beklenen biçimde değil.")
    report = snapshot.report
    if (not isinstance(report, OrganizationReport) or report.scope.organization.id != organization_id
            or not report.stored_data_only or report.target_offset != 0 or report.item_offset != 0
            or report.has_more_targets or report.total_target_count != len(report.targets)):
        raise ValidationError("Kuruluş dışa aktarımı tam veya doğru kapsamda değil; dosya yazılmadı.")
    if len(report.targets) > MAX_EXPORT_TARGETS:
        raise ValidationError(f"Tam rapor en fazla {MAX_EXPORT_TARGETS} etkin hedef içerebilir; dosya yazılmadı.")
    expected = {view.link.id: view for view in report.scope.effective_links}
    actual = {target.membership.link.id: target.membership for target in report.targets}
    if actual != expected or len(actual) != len(report.targets):
        raise ValidationError("Kuruluş raporunun hedefleri açık etkin kapsamla uyuşmuyor; dosya yazılmadı.")
    for target in report.targets:
        for page in target.sections:
            if page.offset != 0 or page.has_more or page.total_count != len(page.items):
                raise ValidationError("Kuruluş bölümünde gösterilmeyen kayıt var; tam rapor dosyası yazılmadı.")
    case_links = report.public_notice_case_links
    if case_links is not None and (
        case_links.offset != 0 or case_links.has_more or case_links.total_count != len(case_links.items)
    ):
        raise ValidationError("Kamu olay vaka bağlantıları eksik; tam rapor dosyası yazılmadı.")
    watch = report.public_notice_watch
    if watch is None:
        if snapshot.public_notice_watch_runs:
            raise ValidationError("Kuruluş dışa aktarımında bağımsız izleme geçmişi bulundu.")
    else:
        if (watch.organization.id != organization_id or watch.watch.organization_id != organization_id
                or watch.total_run_count != len(watch.runs) or watch.total_event_count != len(watch.events)
                or watch.run_offset != 0 or watch.event_offset != 0):
            raise ValidationError("Kuruluş izleme geçmişi tam veya doğru kapsamda değil; dosya yazılmadı.")
        runs = {value.run.id: value for value in snapshot.public_notice_watch_runs}
        if len(runs) != len(snapshot.public_notice_watch_runs) or set(runs) != {run.id for run in watch.runs}:
            raise ValidationError("Kuruluş izleme çalışmalarının tamamı aktarılmadı; dosya yazılmadı.")
        for run in watch.runs:
            details = runs[run.id]
            if (details.run != run or details.watch.id != watch.watch.id
                    or details.scope.organization_id != organization_id
                    or details.run.organization_id != organization_id
                    or details.offset != 0 or details.total_item_count != len(details.items)):
                raise ValidationError("Kuruluş izleme kanıtı eksik veya farklı kapsamda; dosya yazılmadı.")
    if export_record_count(snapshot) > MAX_EXPORT_RECORDS:
        raise ValidationError(f"Tam rapor en fazla {MAX_EXPORT_RECORDS} kayıt içerebilir; dosya yazılmadı.")
