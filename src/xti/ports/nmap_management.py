"""Contracts for authorized Nmap target inventory and immutable plans."""

from typing import Protocol

from xti.domain.nmap_management import (
    ManagedNmapPlan,
    ManagedNmapPlanDefinition,
    ManagedNmapPlanMutation,
    NmapTargetDefinition,
    NmapTargetScope,
    NmapTargetScopeDetails,
    NmapTargetScopeMutation,
)


class NmapManagementRepository(Protocol):
    def save_target(
        self,
        asset_id: str,
        asset_value: str,
        display_name: str,
        definition: NmapTargetDefinition,
        authorization_reason: str,
        *,
        recorded_at: str,
    ) -> NmapTargetScopeMutation:
        ...

    def revoke_target(
        self,
        asset_id: str,
        name: str,
        *,
        reason: str,
        recorded_at: str,
    ) -> NmapTargetScopeMutation:
        ...

    def get_target(self, asset_id: str, name: str) -> NmapTargetScope:
        ...

    def list_targets(
        self,
        asset_id: str,
        *,
        active_only: bool = True,
        limit: int = 100,
    ) -> tuple[NmapTargetScope, ...]:
        ...

    def target_details(
        self, asset_id: str, name: str, *, event_limit: int = 50,
    ) -> NmapTargetScopeDetails:
        ...

    def save_plan(
        self,
        asset_id: str,
        asset_value: str,
        definition: ManagedNmapPlanDefinition,
        *,
        recorded_at: str,
    ) -> ManagedNmapPlanMutation:
        ...

    def get_plan(self, asset_id: str, plan_id: str) -> ManagedNmapPlan:
        ...

    def list_plans(
        self, asset_id: str, *, limit: int = 100,
    ) -> tuple[ManagedNmapPlan, ...]:
        ...
