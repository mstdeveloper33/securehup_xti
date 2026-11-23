from contextlib import closing
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

from xti.adapters.cti_analysis_inputs import SQLiteCtiAnalysisInputs
from xti.adapters.sqlite import SQLiteAssetRepository, StorageError
from xti.adapters.sqlite_cti_analysis import (
    SQLiteCtiAnalysisRepository, case_snapshot, company_in, validate_case_snapshot,
)
from xti.adapters.sqlite_organizations import SQLiteOrganizationRepository
from xti.application.cti_analysis import CtiAnalysisService
from xti.domain.assets import ValidationError
from xti.domain.cti_analysis import PREFIX, CtiAnalysisError, analyse, profile_definition


ACTOR_A = "10000000-0000-4000-8000-000000000001"
ACTOR_B = "10000000-0000-4000-8000-000000000002"
CAMPAIGN = "10000000-0000-4000-8000-000000000003"
MALWARE = "10000000-0000-4000-8000-000000000004"
NEGATED = "10000000-0000-4000-8000-000000000005"
INDICATOR_1 = "20000000-0000-4000-8000-000000000001"
INDICATOR_2 = "20000000-0000-4000-8000-000000000002"
INDICATOR_3 = "20000000-0000-4000-8000-000000000003"
PROFILE_ID = "30000000-0000-4000-8000-000000000001"
ORG_ID = "40000000-0000-4000-8000-000000000001"
AT = datetime(2026, 11, 21, 12, tzinfo=timezone.utc)


def assertion(identifier, source, description, confidence=80, aliases=()):
    return {"id": identifier, "source_name": source,
        "source_reference": "https://reports.example/" + identifier,
        "confidence": confidence, "description": description,
        "last_seen_at": AT.isoformat(), "aliases": list(aliases)}


def relation(identifier, source_id, relationship_type, target_kind, target_id, *assertions):
    return {"id": identifier, "source_entity_id": source_id,
        "relationship_type": relationship_type, "target_kind": target_kind,
        "target_id": target_id, "assertions": list(assertions)}


def definition(organization_id=ORG_ID, **changes):
    values = {"name": "CTI acceptance", "organization_id": organization_id,
        "criticality": "high", "identity_threshold": 88,
        "minimum_independent_sources": 2, "alert_score_min": 60,
        "trend_new_threshold": 2, "fresh_days": 30, "max_entities": 100,
        "max_relationships": 200, "max_candidates": 100,
        "max_graph_nodes": 100, "max_graph_edges": 200,
        "interval_seconds": 300,
        "source_policies": [
            {"source_name": "source-a", "reliability": 90, "independence_group": "publisher-a"},
            {"source_name": "source-b", "reliability": 80, "independence_group": "publisher-b"},
        ]}
    values.update(changes)
    return profile_definition(values)


def attack_entity(stix_id, stix_type, external_id, name, aliases=()):
    return {"stix_id": stix_id, "stix_type": stix_type, "external_id": external_id,
        "name": name, "aliases": list(aliases), "source_url": "https://attack.example/" + external_id,
        "modified_at": AT.isoformat(), "description": name}


def labelled_snapshot(*, organization_id=ORG_ID, profile_id=PROFILE_ID):
    group = attack_entity("intrusion-set--example", "intrusion-set", "G0001", "Example Bear", ("EX Bear",))
    technique = attack_entity("attack-pattern--shell", "attack-pattern", "T1059", "Command and Scripting Interpreter")
    entities = [
        {"id": ACTOR_A, "entity_type": "threat-actor", "display_name": "Example Bear",
         "assertions": [assertion("a1", "source-a", "Uses T1059 against finance organizations in Turkey.", aliases=("EX Bear",))]},
        {"id": ACTOR_B, "entity_type": "threat-actor", "display_name": "EX Bear",
         "assertions": [assertion("a2", "source-b", "Russian actor discussed in banking incidents.", 75, ("Example Bear",))]},
        {"id": CAMPAIGN, "entity_type": "campaign", "display_name": "Example Operation",
         "assertions": [assertion("a3", "source-a", "Campaign record.")]},
        {"id": MALWARE, "entity_type": "malware", "display_name": "Example Bear",
         "assertions": [assertion("a4", "source-b", "Malware record.")]},
        {"id": NEGATED, "entity_type": "campaign", "display_name": "Neutral Operation",
         "assertions": [assertion("a5", "source-a", "Not Turkey and not finance targeting.")]},
    ]
    relationships = [
        relation("r1", ACTOR_A, "related-to", "indicator", INDICATOR_1,
                 assertion("r1a", "source-a", "Shared domain A")),
        relation("r2", CAMPAIGN, "related-to", "indicator", INDICATOR_1,
                 assertion("r2a", "source-a", "Shared domain A")),
        relation("r3", ACTOR_A, "related-to", "indicator", INDICATOR_2,
                 assertion("r3a", "source-b", "Shared domain B")),
        relation("r4", CAMPAIGN, "related-to", "indicator", INDICATOR_2,
                 assertion("r4a", "source-b", "Shared domain B")),
        relation("r5", ACTOR_B, "related-to", "indicator", INDICATOR_3,
                 assertion("r5a", "source-a", "One shared IP")),
        relation("r6", MALWARE, "related-to", "indicator", INDICATOR_3,
                 assertion("r6a", "source-b", "One shared IP")),
    ]
    return {"policy": "cti-analysis-v1", "captured_at": AT.isoformat(),
        "profile_id": profile_id, "profile_revision": 1,
        "definition": definition(organization_id),
        "organization": {"id": organization_id, "display_name": "Example Corp", "domains": ["example.com"]},
        "entities": entities, "relationships": relationships,
        "indicators": [
            {"id": INDICATOR_1, "indicator_type": "domain", "value": "example.com", "assertions": []},
            {"id": INDICATOR_2, "indicator_type": "url", "value": "https://portal.example.com/path", "assertions": []},
            {"id": INDICATOR_3, "indicator_type": "ipv4", "value": "203.0.113.7", "assertions": []},
        ],
        "attack": {"run_id": "attack-run", "version": "fixture", "content_sha256": "a" * 64,
            "entities": [group, technique], "relationships": [], "phases": []},
        "accepted_identity_links": []}


class CtiAnalysisRuleTests(unittest.TestCase):
    def test_labelled_rules_are_explainable_and_conservative(self):
        result = analyse(labelled_snapshot())
        candidates = result["candidates"]
        rules = {row["body"]["rule"] for row in candidates}
        self.assertIn("alias_or_name_similarity", rules)
        self.assertIn("cti_to_attack_alias_similarity", rules)
        self.assertIn("explicit_attack_id_in_source_text", rules)
        self.assertIn("multiple_shared_indicators_and_independent_sources", rules)
        self.assertIn("exact_owned_domain_indicator_relationship", rules)
        self.assertTrue(all(not row["body"]["automatic_verdict"] for row in candidates))
        # Identical labels across different entity types are not merged.
        self.assertFalse(any(row["kind"] == "identity"
            and {row["body"]["subject"]["id"], row["body"]["object"]["id"]} == {ACTOR_A, MALWARE}
            for row in candidates))
        # One shared IP never creates an attribution candidate.
        self.assertFalse(any(row["kind"] == "attribution"
            and {row["body"]["subject"]["id"], row["body"]["object"]["id"]} == {ACTOR_B, MALWARE}
            for row in candidates))
        negated_tags = [row for row in candidates if row["kind"] == "tag"
                        and row["body"]["subject"]["id"] == NEGATED]
        self.assertEqual(negated_tags, [])
        self.assertGreaterEqual(result["source_coverage"]["warnings"]["negated_tags_skipped"], 1)
        self.assertEqual(result["source_coverage"]["cti_source_names"], ["source-a", "source-b"])
        self.assertEqual(result["source_coverage"]["cti_source_count"], 2)
        self.assertEqual(len(result["source_coverage"]["cti_source_scope_sha256"]), 64)

    def test_source_scope_digest_changes_only_when_source_scope_changes(self):
        snapshot = labelled_snapshot()
        original = analyse(snapshot)["source_coverage"]
        snapshot["entities"][0]["assertions"][0]["description"] = "Changed signal content."
        content_changed = analyse(snapshot)["source_coverage"]
        self.assertEqual(original["comparison_sha256"], content_changed["comparison_sha256"])
        snapshot["entities"][0]["assertions"][0]["source_name"] = "source-c"
        source_changed = analyse(snapshot)["source_coverage"]
        self.assertNotEqual(original["comparison_sha256"], source_changed["comparison_sha256"])

    def test_subday_worker_timing_does_not_create_new_candidate_evidence(self):
        snapshot = labelled_snapshot()
        original = analyse(snapshot)
        snapshot["captured_at"] = (AT + timedelta(hours=23)).isoformat()
        later = analyse(snapshot)
        self.assertEqual(
            [row["body_sha256"] for row in original["candidates"]],
            [row["body_sha256"] for row in later["candidates"]],
        )

    def test_candidate_identity_survives_display_label_and_criticality_changes(self):
        snapshot = labelled_snapshot()
        original = analyse(snapshot)
        original_identity = next(row for row in original["candidates"]
            if row["kind"] == "identity"
            and {row["body"]["subject"]["id"], row["body"]["object"]["id"]} == {ACTOR_A, ACTOR_B})
        original_priority = next(row for row in original["candidates"] if row["kind"] == "priority")
        snapshot["entities"][0]["display_name"] = "Renamed Example Bear"
        snapshot["organization"]["display_name"] = "Renamed Example Corp"
        snapshot["definition"] = definition(criticality="critical")
        changed = analyse(snapshot)
        changed_identity = next(row for row in changed["candidates"]
            if row["kind"] == "identity"
            and {row["body"]["subject"]["id"], row["body"]["object"]["id"]} == {ACTOR_A, ACTOR_B})
        changed_priority = next(row for row in changed["candidates"] if row["kind"] == "priority")
        self.assertEqual(original_identity["candidate_key"], changed_identity["candidate_key"])
        self.assertNotEqual(original_identity["body_sha256"], changed_identity["body_sha256"])
        self.assertEqual(original_priority["candidate_key"], changed_priority["candidate_key"])
        self.assertNotEqual(original_priority["body_sha256"], changed_priority["body_sha256"])
        self.assertNotEqual(original["source_coverage"]["comparison_sha256"],
                            changed["source_coverage"]["comparison_sha256"])

    def test_graph_contains_source_claims_and_candidate_layer(self):
        graph = analyse(labelled_snapshot())["graph"]
        self.assertTrue(any(edge["state"] == "source_claim" and edge["evidence_reference"] == "cti.relationship:r1"
                            for edge in graph["edges"]))
        self.assertTrue(any(edge["state"] == "candidate" for edge in graph["edges"]))
        self.assertLessEqual(len(graph["nodes"]), 100)
        self.assertLessEqual(len(graph["edges"]), 200)

    def test_accepted_attack_identity_is_required_for_inherited_technique(self):
        snapshot = labelled_snapshot()
        snapshot["entities"][0]["assertions"][0]["description"] = "No explicit technique id."
        without = analyse(snapshot)
        self.assertFalse(any(row["body"]["rule"] == "accepted_identity_plus_official_attack_uses"
                             for row in without["candidates"]))
        snapshot["attack"]["relationships"] = [{"stix_id": "relationship--uses",
            "source_stix_id": "intrusion-set--example", "target_stix_id": "attack-pattern--shell",
            "relationship_type": "uses", "source_url": "https://attack.example/uses",
            "modified_at": AT.isoformat(), "description": "Official catalog relation"}]
        snapshot["accepted_identity_links"] = [{"candidate_id": "50000000-0000-4000-8000-000000000001",
            "cti_entity_id": ACTOR_A, "attack_stix_id": "intrusion-set--example",
            "evidence_id": "60000000-0000-4000-8000-000000000001",
            "review_id": "70000000-0000-4000-8000-000000000001", "reviewed_at": AT.isoformat()}]
        with_link = analyse(snapshot)
        self.assertTrue(any(row["body"]["rule"] == "accepted_identity_plus_official_attack_uses"
                            for row in with_link["candidates"]))

    def test_contract_rejects_unknown_and_unsafe_profile_values(self):
        with self.assertRaises(ValidationError):
            profile_definition({"name": "x", "organization_id": ORG_ID, "unknown": True})
        with self.assertRaises(ValidationError):
            profile_definition({"name": "x", "organization_id": ORG_ID,
                "source_policies": [{"source_name": "a", "reliability": 101,
                                     "independence_group": "a"}]})


class FrozenInputs:
    def __init__(self, snapshot):
        self.snapshot = snapshot
        self.calls = 0

    def capture(self, plan, accepted, at):
        self.calls += 1
        result = deepcopy(self.snapshot)
        result.update(captured_at=at, profile_id=plan["profile"]["id"],
                      profile_revision=plan["profile"]["revision"],
                      definition=plan["definition"], accepted_identity_links=deepcopy(accepted))
        result["organization"] = {"id": plan["organization"]["id"],
            "display_name": plan["organization"]["display_name"], "domains": ["example.com"]}
        return result


class CtiAnalysisFlowTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(); self.addCleanup(temporary.cleanup)
        self.path = Path(temporary.name) / "xti.db"
        SQLiteAssetRepository(self.path).initialize()
        orgs = SQLiteOrganizationRepository(self.path)
        self.organization = orgs.add(name_key="example corp", display_name="Example Corp",
            reason="Controlled P04 test", recorded_at=AT.isoformat()).organization
        self.repository = SQLiteCtiAnalysisRepository(self.path)
        self.inputs = FrozenInputs(labelled_snapshot(organization_id=self.organization.id))
        self.now = AT
        self.service = CtiAnalysisService(self.repository, self.inputs,
                                           now=lambda: self.now.isoformat())
        self.profile = self.service.execute(PREFIX + "profile.add", name="Acceptance",
            organization_id=self.organization.id, criticality="high",
            source_policies=definition(self.organization.id)["source_policies"],
            idempotency_key="profile")

    def run_analysis(self, key, *, force=True):
        self.now += timedelta(minutes=10)
        return self.service.execute(PREFIX + "run", identifier=self.profile["id"],
            expected_revision=self.profile["revision"], force=force, idempotency_key=key)

    def candidates(self):
        return self.service.execute(PREFIX + "candidates", profile_id=self.profile["id"], limit=100)["items"]

    def test_baseline_replay_unchanged_and_public_snapshot(self):
        first = self.run_analysis("run-1")
        self.assertTrue(first["report"]["silent_baseline"])
        self.assertEqual(first["report"]["notifications"], 0)
        self.assertNotIn("entities", first["snapshot"])
        self.assertTrue(first["snapshot"]["frozen_input_available"])
        replay = self.service.execute(PREFIX + "run", identifier=self.profile["id"],
            expected_revision=1, force=True, idempotency_key="run-1")
        self.assertTrue(replay["replayed"]); self.assertEqual(self.inputs.calls, 1)
        same = self.run_analysis("run-2")
        self.assertEqual(same["report"]["new_evidence"], 0)
        self.assertEqual(same["report"]["changed_candidates"], 0)
        self.assertEqual(same["report"]["notifications"], 0)
        self.assertTrue(all(row["observation_state"] == "observed_in_latest_complete_run"
                            for row in self.candidates()))

    def test_review_is_evidence_bound_and_change_reopens_with_inbox(self):
        self.run_analysis("baseline")
        identity = next(row for row in self.candidates() if row["kind"] == "identity")
        self.service.execute(PREFIX + "review", identifier=identity["id"],
            evidence_id=identity["evidence_id"], expected_revision=0,
            expected_observation_revision=identity["observation_revision"],
            decision="same_entity", reason="Controlled acceptance", idempotency_key="review")
        self.assertFalse(self.service.execute(PREFIX + "candidate.show", identifier=identity["id"])["needs_review"])
        self.inputs.snapshot["entities"][0]["assertions"][0]["confidence"] = 79
        changed = self.run_analysis("changed")
        current = self.service.execute(PREFIX + "candidate.show", identifier=identity["id"])
        self.assertTrue(current["needs_review"])
        self.assertEqual(current["review"]["decision"], "same_entity")
        self.assertGreater(changed["report"]["changed_candidates"], 0)
        from xti.adapters.sqlite_inbox import SQLiteInboxRepository
        inbox = SQLiteInboxRepository(self.path).list(status="all", limit=100)
        self.assertGreater(inbox.total_count, 0)
        detail = SQLiteInboxRepository(self.path).get(inbox.items[0].notification.id)
        self.assertIsNotNone(detail.cti_analysis_change)
        self.assertNotEqual(detail.cti_analysis_change["before"]["id"],
                            detail.cti_analysis_change["after"]["id"])

    def test_disappeared_candidate_is_retained_but_not_current(self):
        self.run_analysis("baseline")
        self.inputs.snapshot["entities"] = []
        self.inputs.snapshot["relationships"] = []
        self.inputs.snapshot["indicators"] = []
        second = self.run_analysis("empty")
        self.assertGreater(second["report"]["retained_not_observed_count"], 0)
        self.assertTrue(all(row["observation_state"] == "retained_not_observed_in_latest_complete_run"
                            for row in self.candidates()))

    def test_company_scope_case_snapshot_and_corruption_fail_closed(self):
        self.run_analysis("baseline")
        candidate = self.candidates()[0]
        with self.repository.connection() as connection:
            company = company_in(connection, self.organization.id)
            frozen = case_snapshot(connection, candidate["id"])
        self.assertEqual(company["total_count"], len(self.candidates()))
        self.assertEqual(validate_case_snapshot(json.loads(frozen.snapshot_json))["candidate"]["id"], candidate["id"])
        with closing(sqlite3.connect(self.path)) as connection:
            connection.execute("UPDATE cti_analysis_evidence SET body_json='{}' WHERE id=?",
                               (candidate["evidence_id"],)); connection.commit()
        with self.assertRaises(StorageError):
            self.service.execute(PREFIX + "candidate.show", identifier=candidate["id"])

    def test_actual_case_link_freezes_historical_analysis_evidence(self):
        self.run_analysis("baseline")
        candidate = self.candidates()[0]
        from xti.config import Settings
        from xti.interfaces.cli import make_case_service
        cases = make_case_service(Settings(data_dir=self.path.parent))
        case = cases.create("CTI analysis case", summary="Controlled investigation",
                            reason="P04 acceptance").case
        linked = cases.add_evidence(case.id, "cti_analysis", candidate["id"],
                                    reason="Analyst selected candidate")
        self.inputs.snapshot["entities"][0]["assertions"][0]["confidence"] = 79
        self.run_analysis("changed")
        with closing(sqlite3.connect(self.path)) as connection:
            row = connection.execute(
                "SELECT snapshot_json FROM case_evidence WHERE id=?", (linked.evidence.id,),
            ).fetchone()
        frozen = json.loads(row[0])
        self.assertEqual(frozen["candidate"]["evidence_id"], candidate["evidence_id"])
        self.assertNotEqual(self.service.execute(PREFIX + "candidate.show",
            identifier=candidate["id"])["evidence_id"], candidate["evidence_id"])

    def test_explicit_recovery_and_idempotency_collision(self):
        plan = self.repository.plan(self.profile["id"])
        snapshot = self.inputs.capture(plan, [], self.now.isoformat())
        run, replayed = self.repository.reserve({"identifier": self.profile["id"],
            "expected_revision": 1, "force": True, "idempotency_key": "reserved"},
            snapshot, self.now.isoformat())
        self.assertFalse(replayed); self.assertEqual(run["status"], "running")
        with self.assertRaises(CtiAnalysisError):
            self.run_analysis("blocked")
        recovered = self.service.execute(PREFIX + "recover", identifier=run["id"],
            idempotency_key="recover")
        self.assertEqual(recovered["status"], "interrupted")
        with self.assertRaises(CtiAnalysisError) as caught:
            self.service.execute(PREFIX + "recover", identifier=run["id"],
                idempotency_key="profile")
        self.assertEqual(caught.exception.code, "idempotency_conflict")


class CtiAnalysisInputScopeTests(unittest.TestCase):
    def test_scoped_assertion_reader_cannot_be_starved_by_unrelated_rows(self):
        connection = sqlite3.connect(":memory:")
        self.addCleanup(connection.close)
        connection.execute("CREATE TABLE assertions (id TEXT, owner_id TEXT, value TEXT, active INTEGER)")
        connection.executemany("INSERT INTO assertions VALUES (?,?,?,1)", [
            ("a", "unrelated", "wrong"), ("b", "selected", "right")])
        rows = SQLiteCtiAnalysisInputs._scoped_rows(connection, table="assertions",
            owner="owner_id", columns="id,owner_id,value", identifiers={"selected"},
            maximum=1, order="owner_id,id", message="too many")
        self.assertEqual(rows, [("b", "selected", "right")])

    def test_real_stored_cti_is_captured_without_network(self):
        from xti.adapters.sqlite_cti_knowledge import SQLiteCtiKnowledgeRepository
        from xti.application.cti_knowledge import CtiKnowledgeService
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "xti.db"
            SQLiteAssetRepository(path).initialize()
            organization = SQLiteOrganizationRepository(path).add(
                name_key="stored example", display_name="Stored Example",
                reason="P04 stored input", recorded_at=AT.isoformat()).organization
            knowledge = CtiKnowledgeService(SQLiteCtiKnowledgeRepository(path), clock=lambda: AT)
            knowledge.add_entity("threat-actor", "Stored Bear", source_name="source-a",
                source_reference="report:stored-a", confidence=80, aliases=("SB",),
                description="Stored actor targets finance in Turkey.")
            knowledge.add_entity("threat-actor", "SB", source_name="source-b",
                source_reference="report:stored-b", confidence=75, aliases=("Stored Bear",),
                description="Independent stored source.")
            service = CtiAnalysisService(SQLiteCtiAnalysisRepository(path),
                                         SQLiteCtiAnalysisInputs(path), now=lambda: AT.isoformat())
            profile = service.execute(PREFIX + "profile.add", name="Stored CTI",
                organization_id=organization.id,
                source_policies=definition(organization.id)["source_policies"],
                idempotency_key="stored-profile")
            run = service.execute(PREFIX + "run", identifier=profile["id"],
                expected_revision=1, force=True, idempotency_key="stored-run")
            self.assertEqual(run["report"]["source_coverage"]["cti_entities"], 2)
            self.assertGreater(run["report"]["counts"]["identity"], 0)
            self.assertEqual(run["snapshot"]["counts"]["entities"], 2)


class CtiAnalysisMigrationTests(unittest.TestCase):
    def test_schema91_to_92_is_atomic_and_recoverable(self):
        from tests.case_evidence_v91_fixture import case_evidence_layout_v91
        from xti.adapters.cti_analysis_schema import create
        from xti.adapters.schema import SCHEMA_VERSION, validate_schema
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "data" / "xti.db"
            storage = SQLiteAssetRepository(path); storage.initialize(); storage.add("example.com")
            with closing(sqlite3.connect(path)) as connection, connection:
                case_evidence_layout_v91(connection)
                connection.execute("PRAGMA user_version=91")
                self.assertEqual(validate_schema(connection, allow_legacy=True), 91)
            before = path.read_bytes()
            def interrupted(connection):
                create(connection)
                raise KeyboardInterrupt("controlled migration interruption")
            with patch("xti.adapters.sqlite.create_cti_analysis_schema", side_effect=interrupted):
                with self.assertRaises(KeyboardInterrupt):
                    storage.migrate()
            self.assertEqual(path.read_bytes(), before)
            self.assertEqual(len(list((path.parent / "backups").glob("*.db"))), 1)
            self.assertEqual(storage.migrate()["to_version"], SCHEMA_VERSION)


if __name__ == "__main__":
    unittest.main()
