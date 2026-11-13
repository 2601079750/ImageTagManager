"""Real install/reinstall/uninstall in an isolated fixture, never user data."""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
import time
import winreg
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from PIL import Image
from imagetag import __version__
from imagetag.core import Catalogue
from imagetag.storage import inspect_database, write_config


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser()
    parser.add_argument("--installer", type=Path,
                        default=root / "release" / f"ImageTagManager-{__version__}-Windows-x64-Setup.exe")
    options = parser.parse_args()
    key = r"Software\Microsoft\Windows\CurrentVersion\Uninstall\{55923FBF-2267-4BC7-98C2-DA9F1543767C}_is1"
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, key):
            raise SystemExit("A user installation already exists; do not modify its registration for this test.")
    except FileNotFoundError:
        pass
    base = root / ".test-output" / ("installer-" + time.strftime("%Y%m%d-%H%M%S"))
    base.mkdir(parents=True)
    report = {"scenarios": []}
    for external in (False, True):
        folder = base / ("external-installed" if external else "portable-installed")
        arguments = [str(options.installer.resolve()), "/VERYSILENT", "/SUPPRESSMSGBOXES",
                     "/NORESTART", "/SP-", "/NOICONS", "/TASKS=", f"/DIR={folder}",
                     "/GROUP=ImageTagManager Packaging Test", f"/LOG={base / 'setup.log'}"]
        subprocess.run(arguments, check=True, timeout=90)
        assert digest(folder / "ImageTagManager.exe") == digest(root / "ImageTagManager.exe")
        assert not (folder / "data").exists() and not (folder / "portable.json").exists()
        library = base / ("external-images" if external else "portable-images")
        library.mkdir()
        image = library / "fixture.png"
        Image.new("RGB", (32, 24), "#6877bd").save(image)
        data = base / "external-data" if external else folder / "data"
        catalogue = Catalogue(data, library)
        catalogue.import_paths([image], "reference")
        group = catalogue.groups()[0]["id"]
        tag = catalogue.create_tag("Installer fixture", group)
        catalogue.apply_tag([catalogue.rows()[0]["id"]], tag)
        catalogue.set_setting("theme_accent", "#6877bd")
        write_config(folder, data, library)
        for relative in ("backups/fixture.txt", "backgrounds/fixture.txt", "app.log"):
            target = data / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text("Generated installer test only", encoding="utf-8")
        protected = [folder / "portable.json", image, *[p for p in data.rglob("*") if p.is_file()]]
        before = {str(p): digest(p) for p in protected}
        snapshot = inspect_database(data / "catalogue.sqlite3")
        subprocess.run(arguments, check=True, timeout=90)
        assert {str(p): digest(p) for p in protected} == before
        assert inspect_database(data / "catalogue.sqlite3") == snapshot
        uninstaller = folder / "unins000.exe"
        subprocess.run([str(uninstaller), "/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART"],
                       check=True, timeout=90)
        deadline = time.monotonic() + 20
        while (folder / "ImageTagManager.exe").exists() and time.monotonic() < deadline:
            time.sleep(.2)
        assert not (folder / "ImageTagManager.exe").exists()
        assert {str(p): digest(p) for p in protected} == before
        assert inspect_database(data / "catalogue.sqlite3") == snapshot
        report["scenarios"].append({"external_data": external, "clean_install": True,
                                    "same_executable": True, "reinstall_preserves_data": True,
                                    "uninstall_preserves_data": True, "counts": snapshot["counts"]})
    report["ok"] = True
    target = base / "report.json"
    target.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print("Installer smoke passed: clean install, same EXE, reinstall/uninstall preserve portable and external data.")
    print(target)


if __name__ == "__main__":
    main()
