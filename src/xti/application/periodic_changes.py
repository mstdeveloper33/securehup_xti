"""Daily and weekly local changes, without refreshing any external source."""
from collections.abc import Callable
from datetime import datetime, timedelta, timezone
from xti.domain.assets import ValidationError, normalize_domain
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
        limit: int = 100,
    ) -> PeriodicChangesReport:
        if type(days) is not int or days not in {1, 7}:
            raise ValidationError('Dönem 1 veya 7 gün olmalı.')
        if type(limit) is not int or not 1 <= limit <= 500:
            raise ValidationError('Dönem raporu bölüm sınırı 1–500 arasında olmalı.')
        scope = PeriodicScope(normalize_domain(domain) if domain is not None else None)
        end = self.clock()
        if not isinstance(end, datetime) or end.tzinfo is None or end.utcoffset() is None:
            raise ValidationError('Dönem raporu saati saat dilimi bilgili olmalı.')
        end = end.astimezone(timezone.utc)
        window = PeriodicWindow((end - timedelta(days=days)).isoformat(), end.isoformat(), days)
        snapshot = self.repository.read(window, scope, limit_per_section=limit)
        notes = (
            'Rapor yerel kayıt zamanını kullanır; internetteki bütün olayları kapsadığı anlamına gelmez.',
            'İlk ölçümler başlangıç bölümündedir; yeni tehdit veya doğrulanmış ihlal sayılmaz.',
            'Ailelerin ve izlemelerin sayıları örtüşebilir; tek bir benzersiz tehdit toplamı üretilmez.',
            'Artık raporlanmayan hesap veya kaynak listesinden çıkan iddia, silinme ya da sorunun giderilmesi kanıtı değildir.',
            'Ransomware satırlarında izleme kimliği/tanım özeti tarihsel bağdır; bugünkü sorgu veya ad eski sonuca uygulanmaz.',
        ) + snapshot.notes
        if scope.domain is not None:
            notes += ('Domain filtresi yalnız açık domain bağı olan marka ve dış yüzey kayıtlarını seçer; sosyal/ransomware ilişkisi tahmin edilmez.',)
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
        )
