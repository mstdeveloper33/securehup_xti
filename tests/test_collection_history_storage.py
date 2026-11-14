"""Linear resume, historical definitions and atomic result provenance."""
from contextlib import closing
from dataclasses import replace
from pathlib import Path
import json
import sqlite3
import tempfile
import unittest
from uuid import uuid4

from xti.adapters.sqlite import SQLiteAssetRepository, StorageError
from xti.adapters.sqlite_collection_profiles import SQLiteCollectionProfileRepository
from xti.adapters.sqlite_collection_history import SQLiteCollectionHistoryRepository
from xti.adapters.sqlite_collection_receipts import record_collection_step_receipt
from xti.adapters.sqlite_ransomware_watches import SQLiteRansomwareWatchRepository
from xti.domain.assets import ValidationError
from xti.domain.collection import CollectionWatchTarget
from xti.domain.collection_profiles import CollectionProfileDefinition
from xti.domain.collection_history import CollectionFrozenPlan, CollectionFrozenUnit, CollectionOperationToken, canonical_plan_json, parse_plan_json
from xti.domain.ransomware_claims import RANSOMWARE_SOURCE_NAME, RANSOMWARE_SOURCE_URL
from xti.domain.ransomware_watches import ransomware_watch_definition_sha256

NOW='2026-11-14T08:00:00+00:00'
LATER='2026-11-14T09:00:00+00:00'
EARLIER='2026-11-14T07:00:00+00:00'

class CollectionHistoryStorageTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.path=Path(self.temp.name)/'xti.db'
        self.storage=SQLiteAssetRepository(self.path);self.storage.initialize()
        self.asset,_=self.storage.add('example.com')
        self.repo=SQLiteCollectionHistoryRepository(self.path)
        self.definition=CollectionProfileDefinition('example.com',task_ids=('ioc-feodo',))
        self.plan=CollectionFrozenPlan(self.definition,(CollectionFrozenUnit('ioc-feodo','ioc','feodo','example.com',None,'feed-v1'),))

    def begin(self,plan=None):
        return self.repo.begin(plan or self.plan,started_at=NOW)

    def receipt(self,details,key,status='complete',*,source_run_id=None,recorded_at=NOW):
        step=next(step for step in details.steps if step.step_key==key)
        operation=self.repo.start_step(details.session.id,step.id,started_at=recorded_at)
        unit=next(unit for unit in details.session.plan.units if unit.step_key==key)
        identifier=str(uuid4())
        if unit.kind=='ioc':
            table='cti_feed_runs';kind='feed_run'
            values=dict(id=identifier,source_name='feodo-tracker',status=status,source_url='https://feodotracker.abuse.ch/downloads/ipblocklist.json',content_sha256='a'*64 if status=='complete' else None,started_at=recorded_at,finished_at=recorded_at,source_record_count=0,indicator_count=0,added_count=0,observed_count=0,updated_count=0,unchanged_count=0,reactivated_count=0,revoked_count=0,error='Kontrollü kaynak hatası.' if status=='failed' else None)
        elif unit.kind=='discovery':
            table='surface_discovery_runs';kind='discovery_run'
            values=dict(id=identifier,asset_id=self.asset.id,asset_value='example.com',provider='crt.sh',status=status,source_url='https://crt.sh/',started_at=recorded_at,finished_at=recorded_at,record_count=0,skipped_names=0,ignored_names=0,warnings='[]',candidate_count=0,candidates_created=0,candidates_existing=0,evidence_created=0,evidence_existing=0,error=None)
        elif unit.kind=='ransomware_refresh':
            table='ransomware_claim_runs';kind='threatcluster_source_run'
            values=dict(id=identifier,source_name=RANSOMWARE_SOURCE_NAME,status=status,source_url=RANSOMWARE_SOURCE_URL,content_sha256='a'*64 if status=='complete' else None,started_at=recorded_at,finished_at=recorded_at,fetched_at=recorded_at if status=='complete' else None,generated_at=recorded_at if status=='complete' else None,window_days=7 if status=='complete' else None,source_record_count=0,claim_count=0,added_count=0,updated_count=0,unchanged_count=0,removed_count=0,error='Kontrollü kaynak hatası.' if status=='failed' else None)
        else:
            table='ransomware_watch_runs';kind='threatcluster_watch_run'
            watch=unit.watch
            values=dict(id=identifier,watch_id=watch.watch_id,source_run_id=source_run_id,definition_sha256=ransomware_watch_definition_sha256(query=watch.query,query_key=watch.query.casefold(),kind=watch.kind,match_mode=watch.match_mode),previous_run_id=None,executed_at=recorded_at,total_count=0,added_count=0,updated_count=0,unchanged_count=0,removed_count=0,result_sha256='a'*64)
        with closing(sqlite3.connect(self.path)) as connection,connection:
            connection.execute('PRAGMA foreign_keys=ON')
            connection.execute('BEGIN IMMEDIATE')
            connection.execute(f"INSERT INTO {table} ({','.join(values)}) VALUES ({','.join('?' for _ in values)})",tuple(values.values()))
            receipt=record_collection_step_receipt(connection,operation,result_kind=kind,result_id=identifier,result_status=status)
        return receipt

    def ransomware_plan(self):
        repo=SQLiteRansomwareWatchRepository(self.path)
        watches=[]
        for name in ('Watch Alpha','Watch Beta'):
            watch=repo.upsert(name_key=name.casefold(),display_name=name,kind='organization',query=name,query_key=name.casefold(),match_mode='exact',recorded_at=NOW).watch
            watches.append(watch)
        watches.sort(key=lambda watch:watch.id)
        definition=replace(self.definition,ransomware_watch_ids=tuple(watch.id for watch in watches))
        units=list(self.plan.units)
        units.append(CollectionFrozenUnit('ransomware-refresh:threatcluster','ransomware_refresh','threatcluster','example.com',None,'claims-v1'))
        for watch in watches:
            target=CollectionWatchTarget(watch.id,watch.display_name,watch.query,'organization','exact')
            units.append(CollectionFrozenUnit(f'ransomware-watch:threatcluster:{watch.id}','ransomware_watch','threatcluster','example.com',target,'claims-v1'))
        return CollectionFrozenPlan(definition,tuple(units))

    def test_reads_are_network_free_and_byte_preserving_and_plan_canonical(self):
        details=self.begin()
        before=self.path.read_bytes()
        self.assertEqual(self.repo.get(details.session.id),details)
        self.assertEqual(self.repo.list().sessions,(details.session,))
        self.assertEqual(before,self.path.read_bytes())
        encoded=canonical_plan_json(self.plan)
        self.assertEqual(parse_plan_json(encoded,self.definition),self.plan)
        with self.assertRaises(ValidationError):parse_plan_json(encoded+' ',self.definition)
        with self.assertRaises(ValidationError):self.repo.resume_plan(details.session.id)

    def test_completed_receipt_survives_recovery_and_analysis_only_resume(self):
        original=self.begin();receipt=self.receipt(original,'ioc-feodo')
        self.assertEqual(self.repo.recover_interrupted(recorded_at=LATER),(original.session.id,))
        self.assertEqual(self.repo.recover_interrupted(recorded_at=LATER),())
        before=self.path.read_bytes();resume=self.repo.resume_plan(original.session.id)
        self.assertEqual(before,self.path.read_bytes())
        self.assertEqual(resume.units,())
        self.assertEqual(resume.retained[0].receipt.result_id,receipt.result_id)
        child=self.repo.begin(self.plan,started_at=EARLIER,parent_id=original.session.id)
        self.assertEqual((child.session.generation,child.steps),(2,()))
        complete=self.repo.finish_session(child.session.id,analysis_status='complete',finished_at=EARLIER)
        self.assertEqual(complete.session.status,'complete')
        self.assertEqual(self.repo.get(original.session.id).session.status,'interrupted')
        self.assertEqual(complete.retained[0].receipt.result_id,receipt.result_id)
        with self.assertRaises(ValidationError):self.repo.begin(self.plan,started_at=LATER,parent_id=original.session.id)
        with self.assertRaises(ValidationError):self.repo.resume_plan(child.session.id)

    def test_failed_unit_retries_in_new_session_and_old_failure_remains(self):
        original=self.begin();failed=self.receipt(original,'ioc-feodo','failed')
        closed=self.repo.finish_session(original.session.id,analysis_status='complete',finished_at=NOW)
        self.assertEqual(closed.session.status,'failed')
        child=self.repo.begin(self.plan,started_at=LATER,parent_id=original.session.id)
        complete=self.receipt(child,'ioc-feodo',recorded_at=LATER)
        result=self.repo.finish_session(child.session.id,analysis_status='complete',finished_at=LATER)
        self.assertEqual(result.session.status,'complete')
        self.assertNotEqual(failed.result_id,complete.result_id)
        self.assertEqual(self.repo.get(original.session.id).session.status,'failed')

    def test_partial_without_any_complete_unit_is_partial(self):
        definition=replace(self.definition,task_ids=('discover-crtsh',))
        plan=CollectionFrozenPlan(definition,(CollectionFrozenUnit('discover-crtsh','discovery','crt.sh','example.com',None,'discovery-v1'),))
        session=self.begin(plan);self.receipt(session,'discover-crtsh','partial')
        closed=self.repo.finish_session(session.session.id,analysis_status='complete',finished_at=LATER)
        self.assertEqual(closed.session.status,'partial')
        self.assertEqual(self.repo.resume_plan(session.session.id).units,plan.units)

    def test_profile_revision_change_blocks_resume_but_not_historical_read(self):
        profiles=SQLiteCollectionProfileRepository(self.path)
        profile=profiles.save('Daily profile',self.definition,recorded_at=NOW).profile
        plan=replace(self.plan,origin=self.repo.profile_origin(profile))
        session=self.begin(plan)
        self.repo.finish_session(session.session.id,analysis_status='pending',finished_at=NOW,stop_reason='interrupted')
        profiles.save('Daily profile',replace(self.definition,watch_item_limit=20),recorded_at=LATER)
        self.assertEqual(self.repo.get(session.session.id).session.plan,plan)
        with self.assertRaises(ValidationError):self.repo.resume_plan(session.session.id)
        with self.assertRaises(ValidationError):self.repo.begin(plan,started_at=LATER,parent_id=session.session.id)
        with self.assertRaises(ValidationError):self.repo.profile_origin(profile)

    def test_changed_incomplete_watch_blocks_resume(self):
        plan=self.ransomware_plan();session=self.begin(plan)
        self.repo.finish_session(session.session.id,analysis_status='pending',finished_at=NOW,stop_reason='interrupted')
        with closing(sqlite3.connect(self.path)) as connection,connection:
            connection.execute('UPDATE ransomware_watches SET active=0 WHERE id=?',(plan.units[-1].watch.watch_id,))
        self.assertEqual(self.repo.get(session.session.id).session.plan,plan)
        with self.assertRaises(ValidationError):self.repo.resume_plan(session.session.id)

    def test_missing_historical_watch_reference_stops_reads_without_reinterpreting_revocation(self):
        plan=self.ransomware_plan();session=self.begin(plan)
        self.repo.finish_session(session.session.id,analysis_status='pending',finished_at=NOW,stop_reason='interrupted')
        with closing(sqlite3.connect(self.path)) as connection,connection:
            connection.execute('UPDATE ransomware_watches SET active=0 WHERE id=?',(plan.units[-1].watch.watch_id,))
        self.assertEqual(self.repo.get(session.session.id).session.plan,plan)
        with closing(sqlite3.connect(self.path)) as connection,connection:
            connection.execute('DELETE FROM ransomware_watches WHERE id=?',(plan.units[-1].watch.watch_id,))
        before=self.path.read_bytes()
        with self.assertRaises(StorageError):self.repo.get(session.session.id)
        self.assertEqual(self.path.read_bytes(),before)

    def test_completed_ransomware_member_is_retained_and_only_missing_member_gets_fresh_refresh(self):
        plan=self.ransomware_plan();first=self.begin(plan)
        self.receipt(first,'ioc-feodo')
        refresh=self.receipt(first,'ransomware-refresh:threatcluster')
        first_key,second_key=plan.units[2].step_key,plan.units[3].step_key
        member=self.receipt(first,first_key,source_run_id=refresh.result_id)
        self.repo.finish_session(first.session.id,analysis_status='pending',finished_at=NOW,stop_reason='interrupted')
        # Later changes to completed watch cannot reinterpret or block its old evidence.
        with closing(sqlite3.connect(self.path)) as connection,connection:
            connection.execute('UPDATE ransomware_watches SET active=0 WHERE id=?',(plan.units[2].watch.watch_id,))
        resume=self.repo.resume_plan(first.session.id)
        self.assertEqual([unit.step_key for unit in resume.units],['ransomware-refresh:threatcluster',second_key])
        child=self.repo.begin(plan,started_at=LATER,parent_id=first.session.id)
        with self.assertRaises(ValidationError):self.repo.start_step(child.session.id,child.steps[1].id,started_at=LATER)
        new_refresh=self.receipt(child,'ransomware-refresh:threatcluster',recorded_at=LATER)
        with self.assertRaises(StorageError):self.receipt(child,second_key,source_run_id=refresh.result_id,recorded_at=LATER)
        # Wrong source receipt rolled back source run; the running step can be recovered,
        # never falsely completed or reusing the old refresh.
        self.assertEqual(self.repo.get(child.session.id).steps[1].status,'running')
        self.repo.finish_session(child.session.id,analysis_status='pending',finished_at=LATER,stop_reason='interrupted')
        third=self.repo.begin(plan,started_at=LATER,parent_id=child.session.id)
        third_refresh=self.receipt(third,'ransomware-refresh:threatcluster',recorded_at=LATER)
        self.receipt(third,second_key,source_run_id=third_refresh.result_id,recorded_at=LATER)
        result=self.repo.finish_session(third.session.id,analysis_status='complete',finished_at=LATER)
        self.assertEqual(result.session.status,'complete')
        retained=next(item for item in result.retained if item.unit.step_key==first_key)
        self.assertEqual(retained.receipt.result_id,member.result_id)
        self.assertEqual(retained.receipt.source_run_id,refresh.result_id)
        with closing(sqlite3.connect(self.path)) as connection:
            self.assertEqual(connection.execute('SELECT COUNT(*) FROM ransomware_watch_runs WHERE watch_id=?',(plan.units[2].watch.watch_id,)).fetchone()[0],1)

    def test_failed_refresh_skips_pending_members_without_old_snapshot_fallback(self):
        plan=self.ransomware_plan();session=self.begin(plan)
        self.receipt(session,'ioc-feodo');self.receipt(session,'ransomware-refresh:threatcluster','failed')
        for step in session.steps[2:]:
            token=CollectionOperationToken(session.session.id,step.id,step.target_sha256,step.depends_on_step_id)
            self.repo.stop_step_without_result(token,status='skipped',error_code='dependency_failed',finished_at=LATER)
        closed=self.repo.finish_session(session.session.id,analysis_status='complete',finished_at=LATER)
        self.assertEqual(closed.session.status,'partial')
        self.assertEqual([step.status for step in closed.steps],['complete','failed','skipped','skipped'])
        self.assertEqual(len(self.repo.resume_plan(session.session.id).units),3)

    def test_receipt_and_frozen_plan_corruption_stop_reads_and_recovery(self):
        session=self.begin();self.receipt(session,'ioc-feodo')
        with closing(sqlite3.connect(self.path)) as connection,connection:
            connection.execute("UPDATE collection_step_receipts SET summary_sha256=?",('0'*64,))
        before=self.path.read_bytes()
        for operation in (lambda:self.repo.get(session.session.id),lambda:self.repo.recover_interrupted(recorded_at=LATER)):
            with self.assertRaises(StorageError):operation()
        self.assertEqual(self.path.read_bytes(),before)

    def test_pagination_uses_sequence_and_backup_restore_keeps_source_links(self):
        first=self.begin();receipt=self.receipt(first,'ioc-feodo')
        self.repo.finish_session(first.session.id,analysis_status='pending',finished_at=NOW,stop_reason='interrupted')
        second=self.repo.begin(self.plan,started_at=EARLIER,parent_id=first.session.id)
        self.repo.finish_session(second.session.id,analysis_status='complete',finished_at=EARLIER)
        page=self.repo.list(limit=1)
        self.assertEqual(page.sessions[0].id,second.session.id)
        self.assertEqual(self.repo.list(limit=1,before=page.next_before).sessions[0].id,first.session.id)
        backup=Path(self.temp.name)/'backup.db';restored=Path(self.temp.name)/'restored.db'
        self.storage.backup(backup);SQLiteAssetRepository.restore(backup,restored)
        reread=SQLiteCollectionHistoryRepository(restored).get(second.session.id)
        self.assertEqual(reread.retained[0].receipt.result_id,receipt.result_id)
        with self.assertRaises(StorageError):SQLiteAssetRepository.restore(backup,restored)
        self.assertEqual(SQLiteAssetRepository(restored).inspect()['collection_session_count'],2)

if __name__=='__main__':unittest.main()
