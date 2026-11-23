#!/usr/bin/env python3
"""Offline P09 accumulated-catalog acceptance; emits one JSON report."""

from __future__ import annotations

from dataclasses import replace
import json
import time
import tracemalloc

from xti.application.source_governance import SourceGovernanceService


COUNT = 10_000
PAGE_SIZE = 200


def main() -> int:
    base = SourceGovernanceService().manifests[0]
    manifests = tuple(
        replace(
            base,
            identifier=f"synthetic:{number:05d}",
            label=f"Synthetic source {number:05d}",
        )
        for number in range(COUNT)
    )
    tracemalloc.start()
    started = time.perf_counter()
    service = SourceGovernanceService(manifests)
    constructed = time.perf_counter()
    observed = []
    for offset in range(0, COUNT, PAGE_SIZE):
        page = service.catalog(offset=offset, limit=PAGE_SIZE)
        observed.extend(item["identifier"] for item in page["sources"])
    finished = time.perf_counter()
    _current, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()

    expected = [item.identifier for item in manifests]
    validation = service.validate()
    if observed != expected or validation["source_count"] != COUNT:
        raise RuntimeError("P09 birikimli katalog sayfalaması kayıt kaybetti veya sırasını bozdu.")
    if len(set(observed)) != COUNT:
        raise RuntimeError("P09 birikimli katalog sayfalaması yinelenen kayıt döndürdü.")
    repeat = service.catalog(offset=0, limit=PAGE_SIZE)
    if repeat["catalog_sha256"] != validation["catalog_sha256"]:
        raise RuntimeError("P09 katalog özeti değişmeyen okumada kararsız.")
    print(json.dumps({
        "ok": True,
        "package": "P09",
        "network_access": False,
        "database_access": False,
        "source_count": COUNT,
        "page_size": PAGE_SIZE,
        "page_count": COUNT // PAGE_SIZE,
        "catalog_sha256": validation["catalog_sha256"],
        "construct_seconds": round(constructed - started, 6),
        "page_all_seconds": round(finished - constructed, 6),
        "peak_tracemalloc_bytes": peak,
    }, ensure_ascii=True, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
