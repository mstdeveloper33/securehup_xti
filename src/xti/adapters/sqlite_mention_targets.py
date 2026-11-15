"""Resolve one active organization or supplier from one audited read snapshot."""

from xti.adapters.sqlite import SQLiteAssetRepository
from xti.adapters.sqlite_organizations import SQLiteOrganizationRepository
from xti.adapters.sqlite_supplier_history import read_supplier_history
from xti.domain.assets import ValidationError
from xti.domain.mentions import MentionTarget, validate_target
from xti.domain.organizations import normalize_organization_id


class SQLiteMentionTargetRepository:
    def __init__(self, path):
        self._storage = SQLiteAssetRepository(path)

    def resolve(self, kind, identifier):
        if kind not in {"organization", "supplier"}:
            raise ValidationError("İçerik araması hedefi kuruluş veya tedarikçi olmalı.")
        normalize_organization_id(identifier)
        with self._storage._connection(readonly=True) as connection:
            connection.execute("BEGIN")
            if kind == "organization":
                state = SQLiteOrganizationRepository._audit(connection)
                record = SQLiteOrganizationRepository._organization_by_id(state, identifier)
                domains = tuple(sorted({
                    stored.link.target.value for stored in state.links.values()
                    if stored.link.organization_id == identifier and stored.link.active
                    and stored.link.target.kind == "domain"
                    and state.targets[stored.link.target][1].active
                }))
            else:
                record = read_supplier_history(connection).suppliers.get(identifier)
                if record is None:
                    raise ValidationError("Tedarikçi kaydı bulunamadı.")
                domains = (record.primary_domain,)
            if not record.active:
                raise ValidationError("İçerik araması için seçilen kayıt etkin olmalı.")
            target = MentionTarget(kind, identifier, record.display_name, domains)
            validate_target(target)
            return target
