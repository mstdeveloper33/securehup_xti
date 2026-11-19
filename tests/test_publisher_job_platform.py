"""The same publisher workflow and review delivery use the scoped JSON surface."""
import unittest
from unittest.mock import patch

from tests import test_source_jobs_platform as base
from tests import test_publisher_documents as publisher


class PublisherPlatformTests(unittest.TestCase):
    def setUp(self):
        self.f = base.SourceJobPlatformTests(); self.f.setUp(); self.addCleanup(self.f.doCleanups)

    def test_scoped_submission_worker_document_and_notification_fence(self):
        self.assertEqual(self.f.invoke('provision', company='beta')[0], 0)
        options = dict(indicator_type='ipv4', value='192.0.2.10', sources=['publisher', 'relationship-notify'],
            publisher_documents=[{'provider': 'cert-fr', 'url': publisher.URL}], max_requests=4)
        with patch('xti.adapters.publisher_documents.PublisherDocumentSource.fetch', return_value=publisher.document()) as fetch:
            code, submitted = self.f.submit(**options)
            self.assertEqual(code, 0, submitted)
            self.assertEqual(fetch.call_count, 0)
            job_id = submitted['data']['job_id']
            code, done = self.f.invoke('worker', extra=('--job-id', job_id))
            self.assertEqual(code, 0, done)
            self.assertEqual(done['data']['status'], 'complete')
            doc = done['data']['steps'][0]['receipt']['document']
            self.assertEqual(self.f.invoke(operation='reports.show', parameters={'identifier': doc['id']})[0], 0)
            code, foreign = self.f.invoke(company='beta', operation='reports.show', parameters={'identifier': doc['id']})
            self.assertNotEqual(code, 0)
            self.assertEqual(foreign['error']['code'], 'not_found')
            params = {'indicator_type': 'ipv4', 'value': '192.0.2.10', 'expected_workspace_id': self.f.context.workspace_id}
            code, wrong = self.f.invoke(company='beta', operation='relationships.notify', parameters=params)
            self.assertNotEqual(code, 0)
            self.assertEqual(wrong['error']['code'], 'scope_mismatch')
            self.assertEqual(self.f.invoke(operation='relationships.notify', parameters=params)[1]['data']['created_count'], 0)
            self.assertEqual(fetch.call_count, 1)

    def test_manifest_reports_current_execution_and_selected_document_limits(self):
        code, response = self.f.invoke(extra=('--describe',))
        self.assertEqual(code, 0)
        manifest = response['data']['source_jobs']
        self.assertEqual(manifest['execution_version'], 5)
        self.assertEqual(manifest['schema_version'], 3)
        self.assertEqual(manifest['max_execution_steps'], 6)
        self.assertEqual(manifest['max_publisher_documents'], 5)
        self.assertIn('relationships.notify', response['data']['operations'])

    def test_terminal_plan_expands_selected_documents_without_network(self):
        from contextlib import redirect_stdout, redirect_stderr
        from io import StringIO
        import json
        from xti.interfaces.cli import main
        from xti.interfaces.source_jobs import source_job_lines
        output, errors = StringIO(), StringIO()
        with redirect_stdout(output), redirect_stderr(errors), patch('xti.adapters.publisher_documents.PublisherDocumentSource.fetch', side_effect=AssertionError('Plan must stay offline')):
            code = main(['--json', 'source-jobs', 'plan', 'example.com', '--type', 'domain',
                '--source', 'publisher', '--source', 'relationship-notify', '--document', 'cert-fr', publisher.URL])
        self.assertEqual((code, errors.getvalue()), (0, ''))
        plan = json.loads(output.getvalue())['data']
        self.assertEqual(plan['step_order'], ['publisher:1', 'relationship-notify'])
        self.assertIn(publisher.URL, '\n'.join(source_job_lines(plan)))
