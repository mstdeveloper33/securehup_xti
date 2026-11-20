"""Frozen positive/negative/unknown page examples must remain distinguishable."""
import importlib.util
from pathlib import Path
import unittest
from unittest.mock import patch


class SocialQualityTests(unittest.TestCase):
    def test_fixed_corpus_without_network_and_without_ownership_inference(self):
        path = Path(__file__).resolve().parents[1] / 'scripts/check-social-quality.py'
        spec = importlib.util.spec_from_file_location('social_quality_acceptance', path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        with patch('socket.create_connection', side_effect=AssertionError('offline corpus')):
            report = module.run()
        self.assertEqual(report['counts'].get('failed', 0), 0, [r for r in report['results'] if not r['passed']])
        self.assertGreaterEqual(report['counts']['label_found'], 6)
        self.assertGreaterEqual(report['counts']['label_not_found'], 5)
        self.assertGreaterEqual(report['counts']['label_inconclusive'], 15)
        self.assertEqual(report['counts'].get('false_presence', 0), 0)
        self.assertEqual(report['counts'].get('false_absence', 0), 0)
        self.assertEqual(report['network_requests'], 0)
