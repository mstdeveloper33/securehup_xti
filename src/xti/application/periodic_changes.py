"""Daily and weekly local changes, without refreshing any external source."""
from collections.abc import Callable
from datetime import datetime, timedelta, timezone
from xti.domain.assets import ValidationError, normalize_domain
from xti.domain.organizations import normalize_organization_id
from xti.domain.periodic_changes import PeriodicChangesReport, PeriodicWindow, PeriodicScope
from xti.ports.periodic_changes import PeriodicChangesRepository


class PeriodicChangesService:

    def __init__(
        self,
        repository: PeriodicChangesRepository,
        *,
        clock: Callable[[], datetime] | None = None,
    ):
        self.repository = repository
        self.clock = clock or (lambda: datetime.now(timezone.utc))

    def show(
        self,
        *,
        days: int = 1,
        domain: str | None = None,
        organization_id: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> PeriodicChangesReport:
        if type(days) is not int or days not in {1, 7}:
            raise ValidationError('Dönem 1 veya 7 gün olmalı.')
        if type(limit) is not int or not 1 <= limit <= 500:
            raise ValidationError('Dönem raporu bölüm sınırı 1–500 arasında olmalı.')
        if type(offset) is not int or not 0 <= offset <= 1_000_000:
            raise ValidationError('Dönem raporu görünüm başlangıcı 0–1.000.000 arasında olmalı.')
        if domain is not None and organization_id is not None:
            raise ValidationError('Domain ve kuruluş filtresi aynı anda kullanılamaz.')
        scope = PeriodicScope(
            normalize_domain(domain) if domain is not None else None,
            normalize_organization_id(organization_id) if organization_id is not None else None,
        )
        end = self.clock()
        if not isinstance(end, datetime) or end.tzinfo is None or end.utcoffset() is None:
            raise ValidationError('Dönem raporu saati saat dilimi bilgili olmalı.')
        end = end.astimezone(timezone.utc)
        window = PeriodicWindow((end - timedelta(days=days)).isoformat(), end.isoformat(), days)
        snapshot = self.repository.read(window, scope, limit_per_section=limit, offset=offset)
        notes = (
            'Rapor yerel kayıt zamanını kullanır; internetteki bütün olayları kapsadığı anlamına gelmez.',
            'İlk ölçümler başlangıç bölümündedir; yeni tehdit veya doğrulanmış ihlal sayılmaz.',
            'Ailelerin ve izlemelerin sayıları örtüşebilir; tek bir benzersiz tehdit toplamı üretilmez.',
            'Artık raporlanmayan hesap veya kaynak listesinden çıkan iddia, silinme ya da sorunun giderilmesi kanıtı değildir.',
            'Ransomware satırlarında izleme kimliği/tanım özeti tarihsel bağdır; bugünkü sorgu veya ad eski sonuca uygulanmaz.',
        ) + snapshot.notes
        if scope.domain is not None:
            notes += ('Domain filtresi yalnız açık domain bağı olan marka/dış yüzey ve kamu olay kaynağının tam Domain alanını seçer; sosyal/ransomware ilişkisi tahmin edilmez.',)
        if scope.organization_id is not None:
            notes += (
                'Kuruluş kapsamı bu okuma anındaki etkin açık bağlantılardır; geçmişteki kuruluş üyeliği veya sahiplik iddiası değildir.',
                'Seçili izlemelerin ortak kaynak durumu bağlam olarak gösterilir; kaynaktaki bütün iddialar kuruluşa ait sayılmaz.',
            )
        return PeriodicChangesReport(
            window,
            scope,
            snapshot.sections,
            snapshot.coverage,
            end.isoformat(),
            notes,
            snapshot.schema_version,
            snapshot.coverage_total_count,
            snapshot.coverage_omitted_count,
            snapshot.organization_scope,
            offset,
        )
