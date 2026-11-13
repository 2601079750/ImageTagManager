"""Build a clean release ZIP containing the executable and project main folder."""
from __future__ import annotations

import argparse
import hashlib
import sys
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from imagetag import __version__


def main():
    root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser()
    parser.add_argument("--exe", type=Path, default=root / "ImageTagManager.exe")
    executable = parser.parse_args().exe.resolve()
    if not executable.is_file():
        raise SystemExit("Build ImageTagManager.exe in the version folder before packaging.")
    target = root / "release"
    target.mkdir(exist_ok=True)
    archive = target / f"ImageTagManager-{__version__}-Windows-x64.zip"
    prefix = f"ImageTagManager-{__version__}"
    files = [root / name for name in (
        ".gitignore", "README.md", "README.en.md", "RELEASE_NOTES.md", "REQUIREMENTS.md",
        "TEST_REPORT.md", "main.py", "build.ps1", "requirements.txt", "requirements-build.txt")]
    for directory in ("imagetag", "tests", "tools"):
        files.extend(sorted((root / directory).rglob("*.py")))
    files.extend(sorted((root / "docs" / "screenshots").glob("*-v03.png")))
    files.extend(sorted((root / "docs").glob("*.md")))
    files.extend(sorted(path for path in (root / "assets").iterdir() if path.is_file()))
    files.extend(sorted(path for path in (root / "installer").iterdir() if path.suffix in (".iss", ".txt")))
    with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as output:
        output.write(executable, f"{prefix}/ImageTagManager.exe")
        for path in files:
            output.write(path, f"{prefix}/{path.relative_to(root).as_posix()}")
    with zipfile.ZipFile(archive) as check:
        if check.testzip() is not None:
            raise SystemExit("ZIP integrity check failed.")
        names = check.namelist()
        if any(part in name.split("/") for name in names for part in (".git", "__pycache__", ".test-output", "build", "data", "rollback", "portable.json")):
            raise SystemExit("Unexpected generated files in release ZIP.")
        if any(name.endswith((".sqlite3", ".sqlite3-wal", ".sqlite3-shm", ".log")) for name in names):
            raise SystemExit("User data found in release ZIP.")
    with archive.open("rb") as stream:
        digest = hashlib.file_digest(stream, "sha256").hexdigest()
    checksum = target / f"{archive.name}.sha256"
    checksum.write_text(f"{digest}  {archive.name}\n", encoding="ascii")
    print(f"Archive: {archive}")
    print(f"Files: {len(names)}")
    print(f"Size: {archive.stat().st_size:,} bytes")
    print(f"SHA256: {digest}")


if __name__ == "__main__":
    main()
