"""Durable queue admission for one frozen, network-free CTI analysis run."""

from xti.domain.assets import ValidationError
from xti.domain.cti_analysis import digest
from xti.domain.mentions import mention_uuid


SOURCE = "cti-analysis"
FIELDS = {"analysis_profile_id", "analysis_profile_revision", "analysis_force"}


def selection(values: dict, sources: list[str], scope: dict) -> dict:
    if SOURCE not in sources:
        if any(values.get(key) is not None for key in FIELDS):
            raise ValidationError("CTI analiz seçimi cti-analysis kaynak işi gerektirir.")
        return {}
    if sources != [SOURCE] or scope["indicator_type"] != "sha256":
        raise ValidationError("CTI analiz işi tek kaynaklı ve profil kapsam SHA256 değeriyle planlanmalı.")
    identifier = mention_uuid(values.get("analysis_profile_id"))
    revision = values.get("analysis_profile_revision")
    force = values.get("analysis_force", False)
    if type(revision) is not int or not 1 <= revision < 2**31 or type(force) is not bool:
        raise ValidationError("CTI analiz profil sürümü veya zaman tercihi geçersiz.")
    return {"analysis_profile_id": identifier,
            "analysis_profile_revision": revision, "analysis_force": force}


def profile_scope_sha256(profile: dict) -> str:
    return digest({"profile_id": profile["id"], "profile_revision": profile["revision"],
                   "organization_id": profile["organization_id"],
                   "definition": profile["definition"]})


def snapshot_scope_sha256(snapshot: dict) -> str:
    return digest({"profile_id": snapshot["profile_id"],
                   "profile_revision": snapshot["profile_revision"],
                   "organization_id": snapshot["definition"]["organization_id"],
                   "definition": snapshot["definition"]})


def guard(profile: dict, plan: dict) -> bool:
    return (profile["id"] == plan["analysis_profile_id"]
            and profile["revision"] == plan["analysis_profile_revision"]
            and profile["binding_state"] == "ready"
            and profile_scope_sha256(profile) == plan["value"])


def validate_receipt(value: object, plan: dict) -> dict:
    fields = {"kind", "run_id", "profile_id", "profile_revision", "report_sha256",
              "source_status", "reused_receipt"}
    if (not isinstance(value, dict) or set(value) != fields
            or value.get("kind") != "cti_analysis_run"
            or value.get("profile_id") != plan["analysis_profile_id"]
            or value.get("profile_revision") != plan["analysis_profile_revision"]
            or value.get("source_status") not in ("complete", "failed", "interrupted")
            or type(value.get("reused_receipt")) is not bool):
        raise ValidationError("CTI analiz iş makbuzu kapsamı geçersiz.")
    mention_uuid(value["run_id"])
    if (not isinstance(value["report_sha256"], str)
            or len(value["report_sha256"]) != 64
            or any(char not in "0123456789abcdef" for char in value["report_sha256"])):
        raise ValidationError("CTI analiz iş raporu özeti geçersiz.")
    return value
