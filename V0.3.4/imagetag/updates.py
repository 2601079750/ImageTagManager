"""GitHub release discovery and transactional portable executable updates."""
from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import time
import urllib.request
import uuid
import zipfile
from pathlib import Path, PurePosixPath

from .storage import inspect_database, read_config, configured_data, snapshot_database

REPOSITORY = "2601079750/ImageTagManager"
PROJECT_URL = "https://github.com/" + REPOSITORY
LATEST_URL = "https://api.github.com/repos/" + REPOSITORY + "/releases/latest"
MAX_DOWNLOAD = 400 * 1024 * 1024


def version_key(value: str) -> tuple:
    match = re.fullmatch(r"v?(\d+)\.(\d+)(?:\.(\d+))?", value.strip())
    if not match:
        raise ValueError("版本号格式不正确。")
    return tuple(int(part or 0) for part in match.groups())


def request(url: str):
    from urllib.parse import urlparse
    parsed = urlparse(url)
    if parsed.scheme != "https" or parsed.hostname not in ("github.com", "api.github.com"):
        raise ValueError("更新地址不属于项目发布源。")
    return urllib.request.urlopen(urllib.request.Request(url, headers={
        "User-Agent": "ImageTagManager-Updater", "Accept": "application/vnd.github+json"}), timeout=20)


def discover(current: str) -> dict:
    with request(LATEST_URL) as response:
        raw = response.read(2 * 1024 * 1024 + 1)
    if len(raw) > 2 * 1024 * 1024:
        raise ValueError("更新信息过大。")
    release = json.loads(raw)
    latest = release["tag_name"]
    if release.get("draft") or release.get("prerelease") or version_key(latest) <= version_key(current):
        return {"available": False, "version": latest}
    name = f"ImageTagManager-{latest.removeprefix('v')}-Windows-x64.zip"
    assets = {asset["name"]: asset for asset in release.get("assets", [])}
    asset = assets.get(name)
    if not asset:
        raise ValueError("发现新版本，但 Windows x64 发布包尚未上传完成。")
    digest = asset.get("digest") or ""
    if digest.startswith("sha256:"):
        digest = digest[7:]
    else:
        checksum = assets.get(name + ".sha256")
        if not checksum:
            raise ValueError("发布包缺少校验信息，已停止下载。")
        with request(checksum["browser_download_url"]) as response:
            digest = response.read(4096).decode("ascii").split()[0]
    if not re.fullmatch(r"[0-9a-fA-F]{64}", digest):
        raise ValueError("发布包校验信息不正确。")
    return {"available": True, "version": latest, "notes": release.get("body") or "暂无更新说明。",
            "url": asset["browser_download_url"], "sha256": digest.lower(), "name": name}


def prepare(release: dict, data_dir: Path, progress=lambda message: None) -> Path:
    stage = data_dir / "updates" / uuid.uuid4().hex
    stage.mkdir(parents=True)
    archive = stage / "download.zip"
    try:
        digest = hashlib.sha256()
        total = 0
        with request(release["url"]) as response, archive.open("wb") as output:
            expected = int(response.headers.get("Content-Length", 0))
            if expected > MAX_DOWNLOAD:
                raise ValueError("更新包超出大小限制。")
            while block := response.read(256 * 1024):
                total += len(block)
                if total > MAX_DOWNLOAD:
                    raise ValueError("更新包超出大小限制。")
                digest.update(block)
                output.write(block)
                progress(f"正在下载更新：{total / 1048576:.1f} MB" + (f" / {expected / 1048576:.1f} MB" if expected else ""))
        if digest.hexdigest() != release["sha256"]:
            raise ValueError("下载校验失败，当前程序和用户数据未被修改。")
        prefix = "ImageTagManager-" + release["version"].removeprefix("v")
        with zipfile.ZipFile(archive) as bundle:
            # The frozen executable contains all runtime assets and code. Only replace
            # this single runtime file; portable.json and data can never be ZIP targets.
            members = [item for item in bundle.infolist() if item.filename == prefix + "/ImageTagManager.exe"]
            if len(members) != 1 or members[0].file_size > MAX_DOWNLOAD or members[0].is_dir():
                raise ValueError("更新包中没有唯一且有效的主程序。")
            with bundle.open(members[0]) as origin, (stage / "ImageTagManager.exe").open("wb") as output:
                shutil.copyfileobj(origin, output)
        with (stage / "ImageTagManager.exe").open("rb") as stream:
            if stream.read(2) != b"MZ":
                raise ValueError("更新包中的主程序不是 Windows EXE。")
        (stage / "release.json").write_text(json.dumps(release, ensure_ascii=False), encoding="utf-8")
        archive.unlink()
        return stage
    except BaseException:
        shutil.rmtree(stage)
        raise


def write_plan(stage: Path, folder: Path, data_dir: Path, library_dir: Path, backup: Path) -> Path:
    executable = folder / "ImageTagManager.exe"
    new = stage / "ImageTagManager.exe"
    if not executable.is_file() or not new.is_file():
        raise ValueError("请在打包后的 EXE 中执行重启更新。")
    with new.open("rb") as stream:
        digest = hashlib.file_digest(stream, "sha256").hexdigest()
    snapshot = inspect_database(data_dir / "catalogue.sqlite3")
    plan = {"format": 1, "pid": os.getpid(), "folder": str(folder.resolve()),
            "data_dir": str(data_dir.resolve()), "library_dir": str(library_dir.resolve()),
            "backup": str(backup.resolve()), "counts": snapshot["counts"],
            "fingerprints": snapshot["fingerprints"], "new_sha256": digest}
    path = stage / "plan.json"
    path.write_text(json.dumps(plan, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def wait_process(pid: int, seconds=90):
    if os.name != "nt":
        return
    import ctypes
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.OpenProcess.restype = ctypes.c_void_p
    kernel.OpenProcess.argtypes = [ctypes.c_ulong, ctypes.c_int, ctypes.c_ulong]
    kernel.WaitForSingleObject.argtypes = [ctypes.c_void_p, ctypes.c_ulong]
    kernel.CloseHandle.argtypes = [ctypes.c_void_p]
    handle = kernel.OpenProcess(0x00100000, False, pid)
    if handle:
        try:
            if kernel.WaitForSingleObject(handle, int(seconds * 1000)) != 0:
                raise RuntimeError("旧程序未能退出，已取消更新。")
        finally:
            kernel.CloseHandle(handle)


def install_plan(path: Path, wait=True, restart=True, replace=os.replace):
    """Helper mode. No Tk startup and no application mutex while waiting."""
    plan = json.loads(path.read_text(encoding="utf-8"))
    stage = path.resolve().parent
    folder = Path(plan["folder"]).resolve()
    data = Path(plan["data_dir"]).resolve()
    old = folder / "ImageTagManager.exe"
    candidate = stage / "ImageTagManager.exe"
    helper = stage / "updater-helper.exe"
    result = stage / "result.json"
    rollback = folder / "rollback" / "ImageTagManager.exe"
    replaced = False
    try:
        if plan.get("format") != 1 or old.resolve() == candidate.resolve():
            raise ValueError("无效的更新计划。")
        if wait:
            wait_process(int(plan["pid"]))
        with candidate.open("rb") as stream:
            if hashlib.file_digest(stream, "sha256").hexdigest() != plan["new_sha256"]:
                raise ValueError("暂存程序校验失败。")
        config = read_config(folder)
        if not config or configured_data(folder, config) != data or Path(config["library_dir"]).resolve() != Path(plan["library_dir"]).resolve():
            raise ValueError("更新前后数据定位不一致，已停止替换。")
        if inspect_database(data / "catalogue.sqlite3")["fingerprints"] != plan["fingerprints"]:
            raise ValueError("数据库在更新准备后发生变化，已停止替换。")
        inspect_database(Path(plan["backup"]))
        rollback.parent.mkdir(exist_ok=True)
        shutil.copy2(old, rollback)
        # Also store the exact matching database/config so manual rollback is possible.
        shutil.copy2(Path(plan["backup"]), rollback.parent / "catalogue.sqlite3")
        shutil.copy2(folder / "portable.json", rollback.parent / "portable.json")
        (rollback.parent / "README.txt").write_text(
            "退出拾图后，可将此处的 ImageTagManager.exe 复制回程序目录。\n"
            "catalogue.sqlite3 是更新前数据库；如新版已升级数据格式，请先备份当前数据，"
            "再将此文件恢复到 portable.json 指向的数据目录。原图不受更新影响。\n", encoding="utf-8")
        temporary = folder / "ImageTagManager.update.exe"
        shutil.copy2(candidate, temporary)
        for attempt in range(30):
            try:
                replace(temporary, old)
                replaced = True
                break
            except PermissionError:
                if attempt == 29:
                    raise
                time.sleep(0.3)
        # Validate data and pointer again after replacement, before starting the new UI.
        if configured_data(folder, read_config(folder)) != data:
            raise ValueError("数据目录配置发生变化。")
        inspect_database(data / "catalogue.sqlite3")
        result.write_text(json.dumps({"ok": True, "data_dir": str(data), "library_dir": plan["library_dir"]}), encoding="utf-8")
        if restart:
            health = stage / "health.json"
            health.unlink(missing_ok=True)
            child = subprocess.Popen([str(old), "--updated", "--update-health", str(health), "--no-startup-scan"], cwd=folder)
            deadline = time.monotonic() + 45
            try:
                while time.monotonic() < deadline:
                    if health.is_file():
                        try:
                            state = json.loads(health.read_text(encoding="utf-8"))
                        except (OSError, ValueError):
                            time.sleep(.2)
                            continue
                        if (state.get("ok") and Path(state["data_dir"]).resolve() == data and
                                Path(state["library_dir"]).resolve() == Path(plan["library_dir"]).resolve() and
                                state.get("fingerprints") == plan["fingerprints"]):
                            break
                        raise RuntimeError("新版读取的数据与更新前不一致，已停止更新。")
                    if child.poll() is not None:
                        raise RuntimeError("新版程序启动失败。")
                    time.sleep(.2)
                else:
                    raise RuntimeError("新版未能确认已读取原数据。")
            except BaseException:
                if child.poll() is None:
                    # Terminate only the child launched for this update, before any
                    # startup scan/import, then restore the pre-update DB snapshot.
                    if os.name == "nt":
                        subprocess.run(["taskkill", "/PID", str(child.pid), "/T", "/F"], capture_output=True)
                    else:
                        child.terminate()
                    child.wait(timeout=15)
                raise
            result.write_text(json.dumps({"ok": True, "healthy": True, "data_dir": str(data), "library_dir": plan["library_dir"]}), encoding="utf-8")
        return True
    except Exception as exc:
        if replaced and rollback.is_file():
            shutil.copy2(rollback, old)
            # A failed new process may have changed schema/settings before its
            # health handshake. Preserve that DB too, then restore the matching one.
            current = data / "catalogue.sqlite3"
            if current.is_file():
                shutil.copy2(current, stage / "failed-startup.sqlite3")
                for suffix in ("-wal", "-shm"):
                    sidecar = Path(str(current) + suffix)
                    if sidecar.is_file():
                        shutil.copy2(sidecar, stage / ("failed-startup.sqlite3" + suffix))
                        sidecar.unlink()
            shutil.copy2(Path(plan["backup"]), current)
            shutil.copy2(rollback.parent / "portable.json", folder / "portable.json")
        result.write_text(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False), encoding="utf-8")
        if restart and old.is_file():
            subprocess.Popen([str(old), "--update-failed", str(result)], cwd=folder)
        raise


def launch_helper(stage: Path, plan: Path):
    # Run a separate copy, so both the existing and downloaded EXEs can be moved.
    helper = stage / "updater-helper.exe"
    shutil.copy2(sys.executable, helper)
    subprocess.Popen([str(helper), "--apply-update", str(plan)], cwd=stage,
                     creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
