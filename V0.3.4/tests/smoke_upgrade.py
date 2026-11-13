"""Real v0.3 helper -> v0.3.4 binary, with an authentic isolated v1 database."""
import json
import shutil
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from imagetag.storage import inspect_database, update_backup, write_config
from imagetag.updates import write_plan
from smoke_exe import wait_json, stop_fixture


def main():
    root = Path(__file__).resolve().parents[1]
    previous = root.parent / 'V0.3'
    if not (previous / 'ImageTagManager.exe').is_file():
        raise SystemExit('Adjacent archived V0.3 EXE is required for the migration test.')
    base = root / '.test-output' / ('upgrade-v03-' + time.strftime('%Y%m%d-%H%M%S'))
    base.mkdir(parents=True)
    results = []
    for external in (False, True):
        folder = base / ('external' if external else 'portable')
        folder.mkdir()
        data = base / 'external-data' if external else folder / 'data'
        library = base / ('external-library' if external else 'portable-library')
        # -B prevents writes into archived source folders.
        code = '''import sys
from pathlib import Path
sys.path.insert(0, sys.argv[1])
from imagetag.core import Catalogue
from PIL import Image
c=Catalogue(Path(sys.argv[2]),Path(sys.argv[3]))
p=c.library_dir/'original.png'
Image.new('RGB',(80,60),'teal').save(p)
c.import_paths([p],'reference')
t=c.create_tag('old-version-tag',c.groups()[0]['id'])
c.apply_tag([c.rows()[0]['id']],t)
c.set_settings({'library_dir':str(c.library_dir),'auto_sync':'0','auto_update':'0','theme':'深色','sync_seconds':'300'})
'''
        subprocess.run([sys.executable, '-B', '-c', code, str(previous), str(data), str(library)], check=True)
        baseline = inspect_database(data / 'catalogue.sqlite3')
        write_config(folder, data, library)
        shutil.copy2(previous / 'ImageTagManager.exe', folder / 'ImageTagManager.exe')
        stage = data / 'updates' / 'fixture'
        stage.mkdir(parents=True)
        shutil.copy2(root / 'ImageTagManager.exe', stage / 'ImageTagManager.exe')
        backup = update_backup(data)
        plan_path = write_plan(stage, folder, data, library, backup)
        plan = json.loads(plan_path.read_text(encoding='utf-8'))
        parent = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(2)'])
        plan['pid'] = parent.pid
        plan_path.write_text(json.dumps(plan), encoding='utf-8')
        helper = stage / 'updater-helper.exe'
        shutil.copy2(previous / 'ImageTagManager.exe', helper)
        process = subprocess.Popen([str(helper), '--apply-update', str(plan_path)], cwd=stage)
        health = wait_json(stage / 'health.json')
        try:
            process.wait(timeout=60)
            state = wait_json(stage / 'result.json')
            assert process.returncode == 0 and state.get('healthy'), state
            assert health['fingerprints'] == baseline['fingerprints']
            assert inspect_database(data / 'catalogue.sqlite3', legacy=True)['fingerprints'] == baseline['fingerprints']
            assert 'scan_rules' in inspect_database(data / 'catalogue.sqlite3')['fingerprints']
            assert list((data / 'backups').glob('before-v0.3.4-*.sqlite3'))
            assert (library / 'original.png').is_file()
            results.append({'case': 'external' if external else 'portable', 'ok': True, 'old_helper_verified_data': True, 'schema_upgraded': True})
        finally:
            stop_fixture(health['pid'])
        time.sleep(.4)
    (base / 'report.json').write_text(json.dumps(results, indent=2), encoding='utf-8')
    print('Actual v0.3 -> v0.3.4 upgrade passed:', base / 'report.json')


if __name__ == '__main__':
    main()
