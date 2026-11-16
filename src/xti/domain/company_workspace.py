"""Immutable company selection rules, independent of storage and authentication."""

import re
from uuid import UUID

from xti.domain.assets import ValidationError


COMPANY_ID = re.compile(r"[a-z0-9][a-z0-9_-]{0,63}", re.ASCII)
MAX_COMPANIES = 10_000


class CompanyWorkspaceError(ValidationError):
    """A trusted launcher selection could not be verified; do not fall back."""


def normalize_company_id(value: object) -> str:
    # Never normalize case or whitespace: these are immutable keys, not names.
    if not isinstance(value, str) or COMPANY_ID.fullmatch(value) is None:
        raise CompanyWorkspaceError(
            "Firma kimliği 1–64 küçük ASCII harf, rakam, alt çizgi veya tire olmalı; "
            "harf ya da rakamla başlamalı."
        )
    return value


def _identity(value: object) -> str:
    try:
        if not isinstance(value, str) or str(UUID(value)) != value:
            raise ValueError
    except (ValueError, AttributeError, TypeError):
        raise CompanyWorkspaceError("Firma kayıt alanının kimlik bağı geçersiz.") from None
    return value


def validate_registry(value: object) -> dict:
    if (not isinstance(value, dict)
            or set(value) != {"version", "registry_id", "companies"}
            or type(value["version"]) is not int or value["version"] != 1
            or not isinstance(value["companies"], list)
            or len(value["companies"]) > MAX_COMPANIES):
        raise CompanyWorkspaceError("Firma kayıt dizini biçimi veya sürümü geçersiz.")
    _identity(value["registry_id"])
    companies, workspaces = set(), set()
    for entry in value["companies"]:
        if (not isinstance(entry, dict)
                or set(entry) != {"company_id", "workspace_id", "enabled"}
                or type(entry["enabled"]) is not bool):
            raise CompanyWorkspaceError("Firma kayıt dizini girdisi geçersiz.")
        company = normalize_company_id(entry["company_id"])
        workspace = _identity(entry["workspace_id"])
        if company in companies or workspace in workspaces:
            raise CompanyWorkspaceError("Firma veya kayıt alanı kimliği yineleniyor.")
        companies.add(company)
        workspaces.add(workspace)
    return value


def validate_workspace_binding(value: object, *, registry_id: str, company_id: str,
                               workspace_id: str) -> None:
    expected = {"version": 1, "registry_id": registry_id, "company_id": company_id,
                "workspace_id": workspace_id}
    if (not isinstance(value, dict) or type(value.get("version")) is not int
            or value != expected):
        raise CompanyWorkspaceError("Firma kayıt alanı seçilen firma ve kayıt diziniyle uyuşmuyor.")
