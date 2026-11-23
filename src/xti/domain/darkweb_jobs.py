"""Durable admission contract for one network-free P05 analysis run."""

from xti.domain.assets import ValidationError
from xti.domain.content_monitoring import digest
from xti.domain.mentions import mention_uuid


SOURCE = "darkweb-monitor"
FIELDS = {"darkweb_profile_id", "darkweb_profile_revision", "darkweb_force"}


def selection(values: dict, sources: list[str], scope: dict) -> dict:
    if SOURCE not in sources:
        if any(values.get(key) is not None for key in FIELDS):
            raise ValidationError("Dark web seçimi darkweb-monitor kaynak işi gerektirir.")
        return {}
    if sources != [SOURCE] or scope["indicator_type"] != "sha256":
        raise ValidationError(
            "Dark web işi tek kaynaklı ve profil kapsam SHA256 değeriyle planlanmalı."
        )
    identifier = mention_uuid(values.get("darkweb_profile_id"))
    revision = values.get("darkweb_profile_revision")
    force = values.get("darkweb_force", False)
    if type(revision) is not int or not 1 <= revision < 2**31 or type(force) is not bool:
        raise ValidationError("Dark web profil sürümü veya zaman tercihi geçersiz.")
    return {
        "darkweb_profile_id": identifier,
        "darkweb_profile_revision": revision,
        "darkweb_force": force,
    }


def profile_scope_sha256(profile: dict) -> str:
    return digest({
        "profile_id": profile["id"],
        "profile_revision": profile["revision"],
        "organization_id": profile["organization_id"],
        "definition": profile["definition"],
    })


def snapshot_scope_sha256(snapshot: dict) -> str:
    return digest({
        "profile_id": snapshot["profile_id"],
        "profile_revision": snapshot["profile_revision"],
        "organization_id": snapshot["definition"]["organization_id"],
        "definition": snapshot["definition"],
    })


def guard(profile: dict, plan: dict) -> bool:
    return (
        profile["id"] == plan["darkweb_profile_id"]
        and profile["revision"] == plan["darkweb_profile_revision"]
        and profile["binding_state"] == "ready"
        and profile_scope_sha256(profile) == plan["value"]
    )


def validate_receipt(value: object, plan: dict) -> dict:
    fields = {
        "kind", "run_id", "profile_id", "profile_revision", "report_sha256",
        "source_status", "reused_receipt",
    }
    if (
        not isinstance(value, dict)
        or set(value) != fields
        or value.get("kind") != "darkweb_monitor_run"
        or value.get("profile_id") != plan["darkweb_profile_id"]
        or value.get("profile_revision") != plan["darkweb_profile_revision"]
        or value.get("source_status") not in ("complete", "failed", "interrupted")
        or type(value.get("reused_receipt")) is not bool
    ):
        raise ValidationError("Dark web iş makbuzu kapsamı geçersiz.")
    mention_uuid(value["run_id"])
    checksum = value["report_sha256"]
    if (
        not isinstance(checksum, str)
        or len(checksum) != 64
        or any(character not in "0123456789abcdef" for character in checksum)
    ):
        raise ValidationError("Dark web iş raporu özeti geçersiz.")
    return value
