"""Explicit news scopes, immutable legacy contracts and source-free recovery selection."""

from dataclasses import replace
import hashlib
import json
from types import SimpleNamespace
import unittest
from unittest.mock import Mock
from uuid import uuid4

from xti.application.collection import CollectionService
from xti.application.collection_history import CollectionHistoryService
from xti.domain.assets import ValidationError
from xti.domain.collection import CollectionPlan, CollectionTask, CollectionWatchTarget, DEFAULT_COLLECTION_TASKS
from xti.domain.collection_history import (
    CollectionFrozenPlan, CollectionFrozenUnit, canonical_plan_json, freeze_collection_plan,
    parse_plan_json, resume_units, unit_sha256,
)
from xti.domain.collection_profiles import (
    CollectionProfileDefinition, canonical_definition_json, definition_sha256,
    normalize_profile_definition, parse_definition_json,
)
from xti.domain.global_saved_searches import GLOBAL_SEARCH_WATCH_VERSION
from xti.domain.news import NEWS_POLICY, NEWS_SOURCES


SOURCES = tuple(source.key for source in NEWS_SOURCES)
LEGACY_DEFINITION = '{"asset_value":"example.com","finding_limit":10,"ransomlook_watch_ids":[],"ransomware_watch_ids":[],"stale_after_hours":24,"task_ids":["ioc-feodo"],"typos":false,"username_watch_ids":[],"version":1,"watch_item_limit":100}'
LEGACY_PLAN = '{"executor_contract_version":1,"origin":null,"units":[{"asset_value":"example.com","contract_version":"feed-v1","kind":"ioc","source":"feodo","step_key":"ioc-feodo","watch":null}],"version":1}'


class NewsCollectionContractTests(unittest.TestCase):
    def setUp(self):
        self.identifier = str(uuid4())
        self.target = CollectionWatchTarget(self.identifier, "Example news", "example", "news", "global",
                                            search_event_id=str(uuid4()))

    def service(self):
        analysis = Mock()
        analysis.show.return_value = SimpleNamespace(asset_value="example.com")
        news, searches = Mock(), Mock()
        searches.plan.return_value = (self.target,)
        service = CollectionService(Mock(), {}, {}, analysis, news=news, news_searches=searches)
        return service, news, searches

    def frozen(self):
        definition = CollectionProfileDefinition("example.com", task_ids=(), news_sources=SOURCES,
                                                 search_watch_ids=(self.identifier,))
        tasks = tuple(CollectionTask(f"news-refresh:{key}", "news_refresh", key, key) for key in SOURCES)
        tasks += (CollectionTask(f"search-watch:{self.identifier}", "search_watch", "local", "Example", (self.target,)),)
        plan = CollectionPlan("example.com", False, tasks, ())
        contracts = {task.id: NEWS_POLICY if task.kind == "news_refresh" else GLOBAL_SEARCH_WATCH_VERSION for task in tasks}
        return freeze_collection_plan(definition, plan, contracts=contracts)

    def test_old_definition_and_plan_bytes_and_hashes_are_unchanged(self):
        definition = CollectionProfileDefinition("example.com", task_ids=("ioc-feodo",))
        self.assertEqual(canonical_definition_json(definition), LEGACY_DEFINITION)
        self.assertEqual(definition_sha256(definition), hashlib.sha256(LEGACY_DEFINITION.encode()).hexdigest())
        self.assertEqual(parse_definition_json(LEGACY_DEFINITION), definition)
        plan = CollectionFrozenPlan(definition, (CollectionFrozenUnit("ioc-feodo", "ioc", "feodo", "example.com", None, "feed-v1"),))
        self.assertEqual(canonical_plan_json(plan), LEGACY_PLAN)
        self.assertEqual(parse_plan_json(LEGACY_PLAN, definition), plan)
        raw_unit = json.dumps(json.loads(LEGACY_PLAN)["units"][0], sort_keys=True, separators=(",", ":"))
        self.assertEqual(unit_sha256(plan.units[0]), hashlib.sha256(raw_unit.encode()).hexdigest())

    def test_news_only_and_watch_plan_round_trip_through_v2(self):
        frozen = self.frozen()
        raw = canonical_definition_json(frozen.definition)
        self.assertEqual(json.loads(raw)["version"], 2)
        self.assertEqual(parse_definition_json(raw), frozen.definition)
        raw_plan = canonical_plan_json(frozen)
        self.assertEqual(json.loads(raw_plan)["version"], 2)
        self.assertEqual(json.loads(raw_plan)["executor_contract_version"], 1)
        self.assertEqual(parse_plan_json(raw_plan, frozen.definition), frozen)
        with self.assertRaises(ValidationError):
            canonical_plan_json(replace(frozen, executor_contract_version=2))

    def test_invalid_duplicate_partial_watch_and_empty_scopes_are_rejected(self):
        for sources, watches in ((('certfr',), ()), (('cisa', 'cisa'), ()),
                                 (('cisa',), (self.identifier,)), ((), (self.identifier,)),
                                 (SOURCES, (self.identifier, self.identifier))):
            with self.subTest(sources=sources, watches=watches), self.assertRaises(ValidationError):
                normalize_profile_definition(CollectionProfileDefinition("example.com", news_sources=sources,
                                                                         search_watch_ids=watches))
        with self.assertRaises(ValidationError):
            normalize_profile_definition(CollectionProfileDefinition("example.com", task_ids=()))
        with self.assertRaises(ValidationError):
            parse_definition_json(LEGACY_DEFINITION.replace('"version":1', '"version":2'))

    def test_source_subset_plan_never_fetches_or_expands_sources(self):
        service, news, searches = self.service()
        plan = service.plan("example.com", tasks=(), news_sources=("cert-fr",))
        self.assertEqual(tuple(task.id for task in plan.tasks), ("news-refresh:cert-fr",))
        news.repository.validate.assert_called_once_with()
        news.refresh.assert_not_called()
        searches.plan.assert_not_called()
        self.assertEqual(CollectionProfileDefinition("example.com").task_ids, DEFAULT_COLLECTION_TASKS)

    def test_watch_scope_validation_precedes_storage_or_transport(self):
        service, news, searches = self.service()
        with self.assertRaises(ValidationError):
            service.plan("example.com", tasks=(), news_sources=("cisa",), search_watch_ids=(self.identifier,))
        self.assertEqual(news.mock_calls, [])
        self.assertEqual(searches.mock_calls, [])
        with self.assertRaises(ValidationError):
            service.run("example.com", tasks=(), news_sources=("cisa",))

    def test_resume_keeps_committed_sources_and_selects_only_pending_search(self):
        frozen = self.frozen()
        completed = {unit.step_key for unit in frozen.units if unit.kind == "news_refresh"}
        pending = resume_units(frozen, completed)
        self.assertEqual(pending, (frozen.units[-1],))
        partial = CollectionHistoryService._selection_for_units(frozen.definition, pending)
        self.assertEqual((partial.task_ids, partial.news_sources, partial.search_watch_ids), ((), (), (self.identifier,)))
        service, news, searches = self.service()
        plan = service.plan("example.com", tasks=(), news_sources=partial.news_sources,
                            search_watch_ids=partial.search_watch_ids, allow_empty_base=True)
        self.assertEqual(tuple(task.kind for task in plan.tasks), ("search_watch",))
        self.assertEqual(news.mock_calls, [])
        searches.plan.assert_called_once_with((self.identifier,))

    def test_search_watch_ids_share_existing_total_watch_limit(self):
        ids = tuple(str(uuid4()) for _ in range(50))
        with self.assertRaises(ValidationError):
            normalize_profile_definition(CollectionProfileDefinition("example.com", username_watch_ids=ids,
                news_sources=SOURCES, search_watch_ids=(self.identifier,)))

    def test_changed_saved_query_prevents_resume_before_source_access(self):
        frozen = self.frozen()
        service, news, searches = self.service()
        searches.plan.return_value = (replace(self.target, query="changed company"),)
        history = CollectionHistoryService(Mock(), lambda definition: service, Mock())
        resume = SimpleNamespace(parent=SimpleNamespace(plan=frozen), units=(frozen.units[-1],))
        with self.assertRaises(ValidationError):
            history._resume_context(resume)
        news.refresh.assert_not_called()
        searches.run.assert_not_called()

    def test_changed_definition_event_prevents_resume_with_same_query(self):
        frozen = self.frozen()
        service, news, searches = self.service()
        searches.plan.return_value = (replace(self.target, search_event_id=str(uuid4())),)
        history = CollectionHistoryService(Mock(), lambda definition: service, Mock())
        resume = SimpleNamespace(parent=SimpleNamespace(plan=frozen), units=(frozen.units[-1],))
        with self.assertRaises(ValidationError):
            history._resume_context(resume)
        news.refresh.assert_not_called()
        searches.run.assert_not_called()

    def test_news_watch_requires_immutable_event_and_legacy_watch_hash_omits_new_field(self):
        frozen = self.frozen()
        broken_unit = replace(frozen.units[-1], watch=replace(self.target, search_event_id=None))
        with self.assertRaises(ValidationError):
            canonical_plan_json(replace(frozen, units=frozen.units[:-1] + (broken_unit,)))
        target = CollectionWatchTarget(str(uuid4()), "Brand watch", "example", "username", "exact", ("github.com",))
        unit = CollectionFrozenUnit(f"username-watch:{target.watch_id}", "username_watch", "maigret", "example.com", target, "test-v1")
        legacy = {"step_key": unit.step_key, "kind": unit.kind, "source": unit.source,
                  "asset_value": unit.asset_value, "contract_version": unit.contract_version,
                  "watch": {"watch_id": target.watch_id, "display_name": target.display_name,
                            "query": target.query, "kind": target.kind, "match_mode": target.match_mode,
                            "platforms": list(target.platforms)}}
        expected = hashlib.sha256(json.dumps(legacy, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
        self.assertEqual(unit_sha256(unit), expected)

    def test_successful_sources_are_not_reintroduced_when_other_source_failed(self):
        frozen = self.frozen()
        successful = {unit.step_key for unit in frozen.units if unit.source in {"cisa", "cert-fr"}}
        pending = resume_units(frozen, successful)
        self.assertEqual(tuple(unit.step_key for unit in pending),
                         ("news-refresh:ncsc", f"search-watch:{self.identifier}"))


if __name__ == "__main__":
    unittest.main()
