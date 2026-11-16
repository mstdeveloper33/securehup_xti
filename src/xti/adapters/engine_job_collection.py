"""Execute an immutable saved-profile request through existing collection history."""

from collections.abc import Callable

from xti.application.collection_history import CollectionHistoryService
from xti.application.collection_profiles import collection_options
from xti.domain.engine_jobs import EngineJobError, EngineJobPayload, result_json
from xti.ports.collection_profiles import CollectionProfileRepository


class CollectionProfileJobRunner:
    def __init__(self, profiles: CollectionProfileRepository,
                 history_factory: Callable[[], CollectionHistoryService]):
        self.profiles, self.history_factory = profiles, history_factory

    def prepare(self, profile_name: str, profile_revision: int) -> EngineJobPayload:
        profile = self.profiles.get(profile_name)
        if not profile.active or profile.revision != profile_revision:
            raise EngineJobError('profile_changed', 'Etkin toplama profili istenen sürümle uyuşmuyor.')
        frozen = self.history_factory().freeze_profile(profile)
        payload = EngineJobPayload(profile.id, profile.display_name, profile.revision, profile.definition, frozen)
        payload.to_json()
        return payload

    def run(self, payload: EngineJobPayload, *, session_started: Callable[[str], None]) -> dict:
        profile = self.profiles.get(payload.profile_name)

        def unchanged():
            current = self.profiles.get(payload.profile_name)
            if (not current.active or current != profile
                    or current.id != payload.profile_id or current.display_name != payload.profile_name
                    or current.revision != payload.profile_revision or current.definition != payload.definition):
                raise EngineJobError('profile_changed', 'Toplama profili değişti; bu iş kaynak isteği göndermedi.')

        unchanged()
        history = self.history_factory()
        outcome = history.run(payload.definition.asset_value, profile=profile, preflight=unchanged,
                              session_started=session_started, expected_plan=payload.frozen_plan,
                              **collection_options(payload.definition))
        details = history.show(outcome.session_id)
        receipts = {receipt.step_id: receipt for receipt in details.receipts}
        session = details.session
        steps = []
        for step in details.steps:
            receipt = receipts.get(step.id)
            steps.append({
                'step_key': step.step_key, 'source': step.source, 'status': step.status,
                'receipt': None if receipt is None else {
                    'kind': receipt.result_kind, 'id': receipt.result_id,
                    'status': receipt.result_status, 'recorded_at': receipt.recorded_at,
                    'summary': dict(receipt.summary), 'source_run_id': receipt.source_run_id,
                    'attribution': receipt.source_attribution, 'license': receipt.source_license,
                    'scope': receipt.source_scope,
                },
            })
        result = {
            'collection_session_id': session.id, 'collection_status': session.status,
            'asset_value': session.plan.definition.asset_value, 'analysis_status': session.analysis_status,
            'started_at': session.started_at, 'finished_at': session.finished_at, 'steps': steps,
        }
        result_json(result)
        return result
