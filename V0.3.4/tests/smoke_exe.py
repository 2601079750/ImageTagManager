"""Exercise the packaged updater with real EXEs and generated data only.

The fixture models a future release with the current binary, so GitHub does not
need a fake public release. No real user database or image is accessed.
"""
import argparse
import hashlib
import json
import shutil
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from PIL import Image
from imagetag.core import Catalogue
from imagetag.storage import inspect_database, update_backup, write_config
from imagetag.updates import write_plan


def wait_json(path, seconds=60):
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        if path.is_file():
            try:
                return json.loads(path.read_text(encoding="utf-8"))
            except (ValueError, OSError):
                pass
        time.sleep(.2)
    raise AssertionError(f"Timed out waiting for {path}")


def stop_fixture(pid):
    # PIDs come exclusively from this fixture's authenticated health file.
    subprocess.run(["taskkill", "/PID", str(pid), "/T", "/F"], capture_output=True)


def main():
    root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser()
    parser.add_argument("--exe", type=Path, default=root / "ImageTagManager.exe")
    exe = parser.parse_args().exe.resolve()
    base = root / ".test-output" / ("exe-update-" + time.strftime("%Y%m%d-%H%M%S"))
    base.mkdir(parents=True)
    report = []
    for external in (False, True):
        folder = base / ("custom-data" if external else "portable-data")
        folder.mkdir()
        shutil.copy2(exe, folder / exe.name)
        data = base / "external-location" if external else folder / "data"
        library = base / ("original-library-external" if external else "original-library-portable")
        catalogue = Catalogue(data, library)
        picture = library / "原图不改名.png"
        Image.new("RGB", (120, 80), "teal").save(picture)
        catalogue.import_paths([picture], "reference")
        tag = catalogue.create_tag("更新后必须保留", catalogue.groups()[0]["id"])
        catalogue.apply_tag([catalogue.rows()[0]["id"]], tag)
        removed_picture = library / 'removed-record.png'
        Image.new('RGB', (80, 65), 'coral').save(removed_picture)
        catalogue.import_paths([removed_picture], 'reference')
        removed_id = next(r['id'] for r in catalogue.rows() if r['filename'] == removed_picture.name)
        catalogue.apply_tag([removed_id], tag)
        catalogue.remove_images([removed_id])
        catalogue.set_setting('removed_retention_days', '15')
        catalogue.set_setting("library_dir", str(library))
        catalogue.set_setting("auto_sync", "0")
        catalogue.set_setting("auto_update", "0")
        appearance = {"acrylic": "1", "theme": "自定义背景", "background_layout": "自由", "background_scale": "130.0",
                      "background_x": "17.0", "background_y": "-12.0", "background_opacity": "75",
                      "custom_accent": "#a34683", "sync_seconds": "45", "sync_interval_mode": "custom",
                      "background_file": "custom.png", "background_name": "generated background"}
        for name, value in appearance.items():
            catalogue.set_setting(name, value)
        (data / "backgrounds").mkdir()
        background = data / "backgrounds" / "custom.png"
        Image.new("RGB", (240, 180), "lightblue").save(background)
        background_digest = hashlib.sha256(background.read_bytes()).hexdigest()
        write_config(folder, data, library)
        baseline = inspect_database(catalogue.db_path)
        health = folder / "initial-health.json"
        child = subprocess.Popen([str(folder / exe.name), "--update-health", str(health), "--no-startup-scan"], cwd=folder)
        running = wait_json(health)
        assert running["ok"] and Path(running["data_dir"]) == data.resolve()
        assert running["fingerprints"] == baseline["fingerprints"]
        # Stop the fixture before generating its replacement snapshot. The actual
        # helper's parent-exit wait is tested with an independent short-lived PID.
        stop_fixture(running["pid"])
        child.wait(timeout=20)
        time.sleep(.4)
        stage = data / "updates" / "fixture-new-release"
        stage.mkdir(parents=True)
        shutil.copy2(exe, stage / exe.name)
        backup = update_backup(data)
        plan_path = write_plan(stage, folder, data, library, backup)
        plan = json.loads(plan_path.read_text(encoding="utf-8"))
        parent = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(2)"])
        plan["pid"] = parent.pid
        plan_path.write_text(json.dumps(plan, ensure_ascii=False), encoding="utf-8")
        helper = stage / "updater-helper.exe"
        shutil.copy2(exe, helper)
        process = subprocess.Popen([str(helper), "--apply-update", str(plan_path)], cwd=stage)
        new_health = wait_json(stage / "health.json")
        try:
            process.wait(timeout=60)
            state = wait_json(stage / "result.json")
            assert process.returncode == 0 and state.get("healthy"), state
            assert new_health["fingerprints"] == baseline["fingerprints"]
            assert Path(new_health["library_dir"]) == library.resolve()
            assert Path(new_health["data_dir"]) == data.resolve()
            assert catalogue.rows()[0]["tags"] == {tag}
            assert catalogue.rows(True)[0]['tags'] == {tag}
            assert catalogue.rows(True)[0]['id'] == removed_id
            assert catalogue.setting('removed_retention_days') == '15'
            assert removed_picture.is_file() and catalogue.scan_rules()
            assert picture.is_file()
            assert all(catalogue.setting(name) == value for name, value in appearance.items())
            assert hashlib.sha256(background.read_bytes()).hexdigest() == background_digest
            assert (folder / "rollback" / exe.name).is_file()
            report.append({"case": "external data" if external else "portable data", "ok": True,
                           "records": new_health["counts"], "appearance_preserved": True,
                           "data_dir": str(data), "library_dir": str(library)})
        finally:
            stop_fixture(new_health["pid"])
        time.sleep(.4)
    (base / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print("Packaged EXE update passed: actual helper wait/replacement/restart/health handshake; portable and external data, tags and library preserved.")
    print(base / "report.json")


if __name__ == "__main__":
    main()
