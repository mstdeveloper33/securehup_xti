import importlib.util
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from xti.adapters.brand_protection_process import (
    SANDBOX_REQUIRED,
    SANDBOX_TRUSTED_CI_FIXTURE,
    browser_sandbox_mode,
    run_worker,
)

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('xti_setup_protection',ROOT/'scripts/setup_protection.py')
setup=importlib.util.module_from_spec(spec);spec.loader.exec_module(setup)


class ProtectionInstallTests(unittest.TestCase):
    def setUp(self):
        temporary=tempfile.TemporaryDirectory();self.addCleanup(temporary.cleanup)
        self.parent=Path(temporary.name)/'tools';self.parent.mkdir(mode=0o700)
        self.destination=self.parent/setup.PACKAGES['playwright'];self.destination.mkdir(mode=0o700)
        (self.destination/'old.txt').write_text('preserved old installation')
        self.enterContext(patch.object(setup,'verify_packages'))
        manifest=self.parent/'sdk-browsers.json'
        manifest.write_text(json.dumps({'browsers':[{'name':'chromium-headless-shell','revision':setup.REVISION}]}))
        from unittest.mock import Mock
        resource=Mock();resource.joinpath.return_value=manifest
        self.enterContext(patch.object(setup.importlib.resources,'files',return_value=resource))
    def test_interrupted_download_preserves_previous_installation_and_candidate(self):
        with patch.object(setup,'run_command',side_effect=RuntimeError('controlled failure')):
            with self.assertRaises(RuntimeError):setup.install(directory=self.destination)
        self.assertEqual((self.destination/'old.txt').read_text(),'preserved old installation')
        self.assertFalse((self.parent/setup.TRANSACTION.journal_name).exists())
        self.assertEqual(len(list(self.parent.glob('.browser-failed-*'))),1)
    def test_check_failure_never_reinstalls_or_contacts_network(self):
        with patch.object(setup,'run_command') as download:
            with self.assertRaises(ValueError):setup.install(check=True,directory=self.destination)
        download.assert_not_called();self.assertTrue((self.destination/'old.txt').exists())
    def test_recovery_restores_old_directory_after_activation(self):
        data=setup.TRANSACTION.prepare(self.parent)
        candidate=setup.TRANSACTION.paths(self.parent,data['transaction'])['candidate']
        (candidate/'new.txt').write_text('unverified new installation')
        setup.TRANSACTION.activate(self.parent,data)
        self.assertFalse((self.destination/'old.txt').exists())
        result=setup.install(recover=True,directory=self.destination)
        self.assertEqual(result['state'],'recovered');self.assertTrue((self.destination/'old.txt').exists())
        self.assertFalse((self.destination/'new.txt').exists())
    def test_symlink_parent_rejected_without_download(self):
        link=self.parent.parent/'linked';link.symlink_to(self.parent,target_is_directory=True)
        with patch.object(setup,'run_command') as download:
            with self.assertRaises(ValueError):setup.install(directory=link/setup.PACKAGES['playwright'])
        download.assert_not_called()
    def test_missing_image_dependencies_are_explicit(self):
        with patch.object(setup,'verify_packages',side_effect=ImportError('controlled missing library')):
            with self.assertRaises(ImportError):setup.install(check=True,directory=self.destination)

    def test_browser_sandbox_is_required_by_default(self):
        self.assertEqual(browser_sandbox_mode({}),SANDBOX_REQUIRED)

    def test_sandbox_free_fixture_mode_is_rejected_outside_github_actions(self):
        with self.assertRaises(ValueError):
            browser_sandbox_mode({'XTI_BROWSER_SANDBOX_MODE':SANDBOX_TRUSTED_CI_FIXTURE})
        with patch.dict(os.environ,{'XTI_BROWSER_SANDBOX_MODE':SANDBOX_TRUSTED_CI_FIXTURE},clear=True):
            self.assertEqual(run_worker({},1),{'status':'browser_sandbox_policy_rejected'})

    def test_github_fixture_mode_is_explicit(self):
        self.assertEqual(browser_sandbox_mode({
            'XTI_BROWSER_SANDBOX_MODE':SANDBOX_TRUSTED_CI_FIXTURE,
            'GITHUB_ACTIONS':'true',
        }),SANDBOX_TRUSTED_CI_FIXTURE)

    def test_github_fixture_mode_rejects_every_other_page(self):
        from xti.adapters.brand_protection_worker import render
        environment={'XTI_BROWSER_SANDBOX_MODE':SANDBOX_TRUSTED_CI_FIXTURE,
                     'GITHUB_ACTIONS':'true'}
        with patch.dict(os.environ,environment,clear=True),self.assertRaisesRegex(ValueError,'fixed offline fixture'):
            render({'url':'https://public.example/','resources':{}})
