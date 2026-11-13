"""Compile the explicit-file-list per-user Windows installer with Inno Setup."""
from __future__ import annotations

import argparse
import hashlib
import shutil
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from imagetag import __version__


def main():
    root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser()
    parser.add_argument("--iscc", type=Path, help="Path to official Inno Setup 7 ISCC.exe")
    options = parser.parse_args()
    compiler = str(options.iscc.resolve()) if options.iscc else shutil.which("ISCC.exe")
    if not compiler or not Path(compiler).is_file():
        raise SystemExit("Install Inno Setup 7 from jrsoftware.org and pass --iscc <ISCC.exe>.")
    if not (root / "ImageTagManager.exe").is_file():
        raise SystemExit("Build ImageTagManager.exe before packaging the installer.")
    subprocess.run([compiler, "/Qp", f"/DAppVersion={__version__}",
                    str(root / "installer" / "ImageTagManager.iss")], cwd=root, check=True)
    target = root / "release" / f"ImageTagManager-{__version__}-Windows-x64-Setup.exe"
    digest = hashlib.sha256(target.read_bytes()).hexdigest()
    target.with_name(target.name + ".sha256").write_text(f"{digest}  {target.name}\n", encoding="ascii")
    print(f"Installer: {target}")
    print(f"Size: {target.stat().st_size:,} bytes")
    print(f"SHA256: {digest}")


if __name__ == "__main__":
    main()
