"""Terminal interface for bounded atomic IOC bulk interchange."""

from dataclasses import asdict
from pathlib import Path

from xti.adapters.ioc_bulk_files import read_bulk_file, write_bulk_file
from xti.adapters.sqlite_cti_indicators import SQLiteCtiIndicatorRepository
from xti.application.ioc_bulk import IocBulkService
from xti.interfaces.text import safe_text


def register_ioc_bulk_parser(actions) -> None:
    preview = actions.add_parser("bulk-preview", help="IOC CSV/JSON/STIX dosyasını yazmadan doğrula ve içerik özetini üret.")
    preview.add_argument("source", type=Path)
    preview.add_argument("--format", required=True, choices=("csv", "json", "stix"))
    apply = actions.add_parser("bulk-import", help="Önizlenmiş IOC dosyasını tek transaction ve tekrar anahtarıyla içe al.")
    apply.add_argument("source", type=Path)
    apply.add_argument("--format", required=True, choices=("csv", "json", "stix"))
    apply.add_argument("--expected-content-sha256", required=True)
    apply.add_argument("--idempotency-key", required=True)
    apply.add_argument("--import-source", required=True, dest="import_source_name")
    apply.add_argument("--import-reference", required=True, dest="import_source_reference")
    export = actions.add_parser("bulk-export", help="Güncel IOC kaynak iddialarını yeni CSV/JSON/STIX dosyasına çıkar.")
    export.add_argument("destination", type=Path)
    export.add_argument("--format", required=True, choices=("csv", "json", "stix"))
    export.add_argument("--indicator-type", choices=("domain", "ipv4", "ipv6", "url", "md5", "sha1", "sha256"))


def execute_ioc_bulk(database: Path, args) -> tuple[dict, list[str]]:
    service = IocBulkService(SQLiteCtiIndicatorRepository(database))
    if args.ioc_action == "bulk-preview":
        result = service.preview(read_bulk_file(args.source), format=args.format)
        data = {
            "format": result.format, "content_sha256": result.content_sha256,
            "preview_sha256": result.preview_sha256,
            "input_count": result.input_count, "record_count": result.record_count,
            "duplicate_count": result.duplicate_count,
            "sample": [asdict(item) for item in result.records[:20]],
            "sample_truncated": len(result.records) > 20,
        }
        return data, [
            "IOC toplu dosyası doğrulandı; henüz kayıt yapılmadı.",
            f"Biçim: {result.format} | girdi: {result.input_count} | benzersiz: {result.record_count} | aynı tekrar: {result.duplicate_count}",
            f"İçerik SHA-256: {safe_text(result.content_sha256)}",
            "İçe almak için bu değeri --expected-content-sha256 ile kullanın.",
        ]
    if args.ioc_action == "bulk-import":
        result = service.import_payload(
            read_bulk_file(args.source), format=args.format,
            expected_content_sha256=args.expected_content_sha256,
            idempotency_key=args.idempotency_key,
            import_source_name=args.import_source_name,
            import_source_reference=args.import_source_reference,
        )
        data = asdict(result)
        return data, [
            "IOC toplu içe alma makbuzu",
            f"Çalışma: {safe_text(result.run_id)} | kayıt: {result.record_count}",
            f"Eklenen {result.added_count}; gözlenen {result.observed_count}; güncellenen {result.updated_count}; yeniden etkin {result.reactivated_count}; değişmeyen {result.unchanged_count}.",
            "Aynı tekrar anahtarı oynatıldı; yeni kayıt oluşmadı." if result.replayed else "Bütün kayıtlar tek transaction içinde işlendi.",
        ]
    build = service.build_export(format=args.format, indicator_type=args.indicator_type)
    artifact = write_bulk_file(
        build.payload, args.destination, format=build.format,
        record_count=build.record_count,
    )
    data = {"build": {key: value for key, value in asdict(build).items() if key != "payload"},
            "artifact": asdict(artifact)}
    return data, [
        "IOC toplu dışa aktarma tamamlandı.",
        f"Biçim: {build.format} | kayıt: {build.record_count}",
        f"Dosya: {safe_text(artifact.destination)}",
        f"SHA-256: {safe_text(artifact.sha256)}",
    ]
