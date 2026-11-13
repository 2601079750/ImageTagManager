"""Portable startup configuration and verified, non-destructive data migration."""
from __future__ import annotations

import json
import os
import shutil
import sqlite3
import sys
import time
import uuid
import hashlib
from contextlib import closing
from pathlib import Path

CONFIG_NAME = "portable.json"


def program_dir() -> Path:
    return Path(sys.executable).resolve().parent if getattr(sys, "frozen", False) else Path(__file__).resolve().parents[1]


def read_config(folder: Path) -> dict:
    path = folder / CONFIG_NAME
    if not path.exists():
        return {}
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict) or value.get("format") != 1:
        raise ValueError("启动配置无法识别，请保留 portable.json 并从备份恢复配置。")
    return value


def configured_data(folder: Path, config: dict) -> Path:
    value = Path(config.get("data_dir", "data"))
    return (value if value.is_absolute() else folder / value).resolve()


class StartupCancelled(Exception):
    pass


def validate_locations(data: Path, library: Path):
    data, library = data.resolve(), library.resolve()
    if data == library or data in library.parents or library in data.parents:
        raise ValueError("应用数据目录与图片库不能相同或互相包含，请选择独立文件夹。")


def resolve_startup(folder: Path, choose_library, confirm_legacy, choose_existing,
                    data_override=None, library_override=None, legacy_dir=None):
    """First-run UI is injected so persistence/migration is independently testable."""
    folder = folder.resolve()
    config = read_config(folder)
    data = Path(data_override).resolve() if data_override else configured_data(folder, config)
    library = str(library_override or config.get("library_dir", ""))
    database = data / "catalogue.sqlite3"
    if config and not data_override and not database.is_file():
        recovered = choose_existing(data)
        if not recovered:
            raise StartupCancelled()
        data = Path(recovered).resolve()
        database = data / "catalogue.sqlite3"
        details = inspect_database(database)
        library = str(library_override or details["library_dir"])
    if not config and not data_override and not database.is_file() and legacy_dir:
        legacy = Path(legacy_dir).resolve()
        if legacy != data and (legacy / "catalogue.sqlite3").is_file():
            details = inspect_database(legacy / "catalogue.sqlite3")
            if not confirm_legacy(legacy, data, details):
                raise StartupCancelled()
            migrate_data(legacy, data)
            library = str(library_override or details["library_dir"])
    if database.is_file():
        details = inspect_database(database)
        if not library:
            library = details["library_dir"]
    if not library or (not library_override and not Path(library).is_dir()):
        library = choose_library(library)
        if not library:
            raise StartupCancelled()
    library = Path(library).resolve()
    validate_locations(data, library)
    # Do not commit the pointer here. main() first opens and validates the
    # Catalogue, then commits the config. Cancelled startup creates no empty DB.
    return data, library


def write_config(folder: Path, data_dir: Path, library_dir: Path):
    data_dir, library_dir = data_dir.resolve(), library_dir.resolve()
    try:
        location = str(data_dir.relative_to(folder.resolve()))
    except ValueError:
        location = str(data_dir)
    value = {"format": 1, "data_dir": location, "library_dir": str(library_dir)}
    path = folder / CONFIG_NAME
    temporary = folder / (CONFIG_NAME + ".tmp")
    with temporary.open("w", encoding="utf-8") as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2)
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary, path)


def inspect_database(path: Path, legacy=False) -> dict:
    """Read-only validation, including tag links; never create a missing database."""
    if not path.is_file():
        raise ValueError(f"找不到原来的数据库：\n{path}\n\n请重新连接数据目录，或恢复备份。")
    with closing(sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True)) as db:
        if db.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
            raise ValueError("数据库完整性检查未通过，已停止切换。")
        version = db.execute("PRAGMA user_version").fetchone()[0]
        if version not in (1, 2):
            raise ValueError(f"不支持的数据版本 {version}，请使用兼容的程序。")
        if db.execute("PRAGMA foreign_key_check").fetchone():
            raise ValueError("数据库标签关联不完整，已停止切换。")
        counts = {name: db.execute(f"SELECT COUNT(*) FROM {name}").fetchone()[0]
                  for name in ("images", "tags", "tag_groups", "image_tags", "sources", "settings")}
        fingerprints = {name: hashlib.sha256(json.dumps(db.execute(f"SELECT * FROM {name} ORDER BY 1,2").fetchall(),
                                                       ensure_ascii=False).encode()).hexdigest()
                        for name in ("images", "tags", "tag_groups", "image_tags", "sources")}
        if version >= 2 and legacy:
            # Preserve v0.3 helpers' exact column verification during migration.
            columns = {'sources': 'id,path,kind',
                       'images': 'id,path,filename,sha256,bytes,mtime_ns,width,height,format,animated,missing,added_at'}
            for name, names in columns.items():
                fingerprints[name] = hashlib.sha256(json.dumps(db.execute(f'SELECT {names} FROM {name} ORDER BY 1,2').fetchall(), ensure_ascii=False).encode()).hexdigest()
        if version >= 2 and not legacy:
            counts['scan_rules'] = db.execute('SELECT COUNT(*) FROM scan_rules').fetchone()[0]
            fingerprints['scan_rules'] = hashlib.sha256(json.dumps(db.execute('SELECT * FROM scan_rules ORDER BY path,kind').fetchall(), ensure_ascii=False).encode()).hexdigest()
        library = db.execute("SELECT value FROM settings WHERE key='library_dir'").fetchone()
        if library is None:
            library = db.execute("SELECT path FROM sources WHERE kind='library' ORDER BY id LIMIT 1").fetchone()
        return {"counts": counts, "fingerprints": fingerprints, "library_dir": library[0] if library else ""}


def snapshot_database(source: Path, destination: Path) -> dict:
    before = inspect_database(source)
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists():
        raise ValueError("备份目标已存在。")
    with closing(sqlite3.connect(source.resolve().as_uri() + "?mode=ro", uri=True)) as origin:
        with closing(sqlite3.connect(destination)) as target:
            origin.backup(target)
    after = inspect_database(destination)
    if before != after:
        raise ValueError("备份校验不一致，原数据库保持不变。")
    return after


def migrate_data(source: Path, target: Path) -> dict:
    source, target = source.resolve(), target.resolve()
    if source == target or source in target.parents or target in source.parents:
        raise ValueError("新数据目录不能与旧目录相同，也不能互相包含。")
    if target.exists() and any(target.iterdir()):
        raise ValueError("迁移目标必须是空文件夹；如需打开已有数据库，请选择“使用已有数据”。")
    target.parent.mkdir(parents=True, exist_ok=True)
    stage = target.parent / (".imagetag-migrate-" + uuid.uuid4().hex)
    stage.mkdir()
    try:
        result = snapshot_database(source / "catalogue.sqlite3", stage / "catalogue.sqlite3")
        for name in ("thumbnails", "backups", "backgrounds"):
            if (source / name).is_dir():
                shutil.copytree(source / name, stage / name)
        if (source / "app.log").is_file():
            shutil.copy2(source / "app.log", stage / "app.log")
        if target.exists():
            target.rmdir()  # Only the verified empty directory, never user content.
        stage.rename(target)
        return result
    finally:
        if stage.exists():
            shutil.rmtree(stage)


def update_backup(data_dir: Path) -> Path:
    target = data_dir / "backups" / (time.strftime("before-update-%Y%m%d-%H%M%S-") + uuid.uuid4().hex[:6] + ".sqlite3")
    snapshot_database(data_dir / "catalogue.sqlite3", target)
    return target
