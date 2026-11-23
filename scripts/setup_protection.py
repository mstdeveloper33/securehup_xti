"""Recoverable SDK-pinned Chromium installer. Existing installations are retained."""
import argparse
import fcntl
import importlib.resources
import json
import os
from pathlib import Path
import shutil
import stat
import sys
import tempfile

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from xti.adapters.brand_protection_tools import PACKAGES,REVISION,browser_directory,binary,checksum,browser_status,smoke,verify_packages
from xti.adapters.installation_transaction import DirectoryInstallation
from xti.adapters.installation_process import run_command,interruption_handlers,ProcessCleanupError
from xti.adapters.tool_installation import ToolInstallationError

TRANSACTION=DirectoryInstallation(canonical_name=PACKAGES['playwright'],prefix='.browser',journal_name='.browser-transaction.json')


def install(*,check=False,recover=False,directory=None):
    destination=directory or browser_directory();parent=destination.parent
    verify_packages()
    if check:
        result=browser_status(destination,verify_hash=True)
        if result['state']!='ready':raise ValueError('Browser installation is not verified; run ./scripts/setup-protection')
        return {**result,'offline_check':smoke(destination)}
    parent.mkdir(parents=True,exist_ok=True,mode=0o700)
    if parent.is_symlink() or parent.stat().st_uid!=os.getuid() or parent.stat().st_mode & 0o022:raise ValueError('Browser directory must be private and owned')
    fd=os.open(parent/'.install.lock',os.O_RDWR|os.O_CREAT|os.O_NOFOLLOW,0o600)
    try:
        if not stat.S_ISREG(os.fstat(fd).st_mode) or os.fstat(fd).st_nlink!=1:raise ValueError('Invalid installer lock')
        fcntl.flock(fd,fcntl.LOCK_EX)
        if recover:
            if (parent/TRANSACTION.journal_name).exists():TRANSACTION.recover(parent)
            return {'state':'recovered'}
        if (parent/TRANSACTION.journal_name).exists():raise ValueError('Interrupted browser installation; run ./scripts/setup-protection --recover')
        if browser_status(destination,verify_hash=True)['state']=='ready':return {**browser_status(destination),'offline_check':smoke(destination)}
        data=TRANSACTION.prepare(parent);candidate=TRANSACTION.paths(parent,data['transaction'])['candidate']
        try:
            bundled=json.loads(importlib.resources.files('playwright').joinpath('driver/package/browsers.json').read_text())
            expected=next(v for v in bundled['browsers'] if v['name']=='chromium-headless-shell')
            if expected['revision']!=REVISION:raise ValueError('SDK browser revision differs')
            with tempfile.TemporaryDirectory(prefix='xti-p03-browser-') as tmp:
                staged=Path(tmp)/'browsers'
                env={'PATH':os.environ.get('PATH','/usr/bin:/bin'),'LANG':'C.UTF-8','HOME':tmp,'PLAYWRIGHT_BROWSERS_PATH':str(staged),
                    'PYTHONNOUSERSITE':'1','PYTHONPYCACHEPREFIX':str(Path(tmp)/'cache')}
                run_command([sys.executable,'-m','playwright','install','chromium','--only-shell'],cwd=tmp,lock_fd=fd,timeout=300,
                    recovery_command='./scripts/setup-protection --recover',environment=env)
                smoke(staged)
                shutil.copytree(staged,candidate,dirs_exist_ok=True,symlinks=True)
            path=binary(candidate)
            receipt={'sdk':PACKAGES['playwright'],'revision':REVISION,'binary':path.relative_to(candidate).as_posix(),
                'binary_sha256':checksum(path),'download_basis':'SDK official TLS download; archive SHA256 not separately pinned'}
            (candidate/'xti-receipt.json').write_text(json.dumps(receipt));(candidate/'xti-receipt.json').chmod(0o600)
            TRANSACTION.activate(parent,data)
            result=install(check=True,directory=destination)
            TRANSACTION.commit(parent,data)
            return result
        except ProcessCleanupError:raise
        except BaseException:
            TRANSACTION.recover(parent);raise
    finally:os.close(fd)


def main():
    parser=argparse.ArgumentParser(description='P03 Chromium kurulumu / çevrimdışı doğrulama')
    parser.add_argument('--check',action='store_true');parser.add_argument('--recover',action='store_true');args=parser.parse_args()
    try:
        with interruption_handlers():result=install(check=args.check,recover=args.recover)
        print(json.dumps(result));return 0
    except (OSError,ValueError,ToolInstallationError,ImportError) as error:
        print('P03 kurulumu tamamlanmadı: '+str(error),file=sys.stderr);return 1

if __name__=='__main__':raise SystemExit(main())
