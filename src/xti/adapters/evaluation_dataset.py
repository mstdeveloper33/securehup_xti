"""Strict loader for the pinned synthetic domain-evaluation dataset."""

from functools import lru_cache
import hashlib
from importlib.resources import files
import json

from xti.domain.evaluation import EvaluationCase, EvaluationDataset


DATASET_NAME = "domain_evaluation_v2.json"
DATASET_SHA256 = "f7531925dbd72884519d56b251c5a6247ed10bc696a003f1a97fcad12c18582a"
_ROOT_KEYS = frozenset({"schema_version", "dataset_version", "description", "cases"})
_CASE_KEYS = frozenset({"id", "category", "asset", "domain", "expected", "baseline", "note"})
_LABELS = frozenset({"review", "ignore"})


class EvaluationDataError(RuntimeError):
    """The bundled, versioned evaluation artifact is missing or corrupt."""


def _text(value, name: str, maximum: int) -> str:
    if (
        not isinstance(value, str) or value != value.strip() or not value
        or len(value) > maximum or not value.isprintable()
    ):
        raise EvaluationDataError(
            f"Paketlenmiş değerlendirme verisinde geçersiz {name} alanı var."
        )
    return value


@lru_cache(maxsize=1)
def load_evaluation_dataset() -> EvaluationDataset:
    content = files("xti").joinpath("data").joinpath(DATASET_NAME).read_bytes()
    digest = hashlib.sha256(content).hexdigest()
    if digest != DATASET_SHA256:
        raise EvaluationDataError("Paketlenmiş değerlendirme verisinin özeti uyuşmuyor.")
    if len(content) > 256 * 1024:
        raise EvaluationDataError("Paketlenmiş değerlendirme verisi beklenen sınırı aşıyor.")
    try:
        raw = json.loads(content)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise EvaluationDataError(
            "Paketlenmiş değerlendirme verisi geçerli UTF-8 JSON değil."
        ) from exc
    if not isinstance(raw, dict) or frozenset(raw) != _ROOT_KEYS or raw["schema_version"] != 1:
        raise EvaluationDataError("Paketlenmiş değerlendirme veri düzeni desteklenmiyor.")
    version = _text(raw["dataset_version"], "sürüm", 64)
    description = _text(raw["description"], "açıklama", 1000)
    if not isinstance(raw["cases"], list) or not 1 <= len(raw["cases"]) <= 1000:
        raise EvaluationDataError("Paketlenmiş değerlendirme örnek sayısı geçersiz.")
    result = []
    identifiers = set()
    for number, item in enumerate(raw["cases"], start=1):
        if not isinstance(item, dict) or frozenset(item) != _CASE_KEYS:
            raise EvaluationDataError(f"Paketlenmiş değerlendirme örneği {number} geçersiz.")
        identifier = _text(item["id"], "kimlik", 64)
        if identifier in identifiers:
            raise EvaluationDataError(
                "Paketlenmiş değerlendirme verisinde tekrarlı kimlik var."
            )
        identifiers.add(identifier)
        expected = _text(item["expected"], "beklenti", 16)
        baseline = _text(item["baseline"], "başlangıç sonucu", 16)
        if expected not in _LABELS or baseline not in _LABELS:
            raise EvaluationDataError(
                "Paketlenmiş değerlendirme verisinde bilinmeyen etiket var."
            )
        result.append(EvaluationCase(
            id=identifier,
            category=_text(item["category"], "kategori", 64),
            asset=_text(item["asset"], "izlenen adres", 253),
            domain=_text(item["domain"], "aday adres", 253),
            expected=expected,
            baseline=baseline,
            note=_text(item["note"], "örnek notu", 1000),
        ))
    return EvaluationDataset(version, digest, description, tuple(result))
