from __future__ import annotations

import ctypes
import hashlib
import json
import os
import shutil
import sqlite3
import tempfile
import time
import uuid
from collections import defaultdict
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Iterable

from PIL import Image, ImageOps

EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".gif", ".bmp", ".tif", ".tiff", ".avif"}
SCHEMA_VERSION = 1


def path_key(path: str | Path) -> str:
    return os.path.normcase(os.path.abspath(path))


def pictures_folder() -> Path:
    """Ask Windows for the redirected Pictures folder (including OneDrive)."""
    if os.name == "nt":
        buffer = ctypes.create_unicode_buffer(32768)
        if ctypes.windll.shell32.SHGetFolderPathW(None, 0x27, None, 0, buffer) == 0:
            return Path(buffer.value)
    return Path.home() / "Pictures"


def default_data_folder() -> Path:
    return Path(os.environ.get("LOCALAPPDATA", str(Path.home() / ".local" / "share"))) / "ImageTagManager"


def file_hash(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


@dataclass
class Report:
    added: int = 0
    updated: int = 0
    recovered: int = 0
    missing: int = 0
    errors: list[str] = field(default_factory=list)
    candidates: list[tuple[int, list[str]]] = field(default_factory=list)

    def summary(self) -> str:
        text = f"新增 {self.added} · 更新 {self.updated} · 恢复关联 {self.recovered} · 原图缺失 {self.missing}"
        if self.errors:
            text += f" · {len(self.errors)} 项未完成"
        if self.candidates:
            text += f" · {len(self.candidates)} 项需选择位置"
        return text


class Catalogue:
    def __init__(self, data_dir: Path, library_dir: Path):
        self.data_dir = Path(data_dir).resolve()
        self.library_dir = Path(library_dir).resolve()
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.library_dir.mkdir(parents=True, exist_ok=True)
        self.cache_dir = self.data_dir / "thumbnails"
        self.cache_dir.mkdir(exist_ok=True)
        self.db_path = self.data_dir / "catalogue.sqlite3"
        with self.connection() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS sources (
                    id INTEGER PRIMARY KEY, path TEXT NOT NULL UNIQUE, kind TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS images (
                    id INTEGER PRIMARY KEY, path TEXT NOT NULL UNIQUE,
                    filename TEXT NOT NULL, sha256 TEXT NOT NULL,
                    bytes INTEGER NOT NULL, mtime_ns INTEGER NOT NULL,
                    width INTEGER NOT NULL, height INTEGER NOT NULL,
                    format TEXT NOT NULL, animated INTEGER NOT NULL DEFAULT 0,
                    missing INTEGER NOT NULL DEFAULT 0, added_at REAL NOT NULL);
                CREATE INDEX IF NOT EXISTS image_hash ON images(sha256);
                CREATE TABLE IF NOT EXISTS tag_groups (
                    id INTEGER PRIMARY KEY, name TEXT NOT NULL, name_key TEXT NOT NULL UNIQUE);
                CREATE TABLE IF NOT EXISTS tags (
                    id INTEGER PRIMARY KEY, group_id INTEGER NOT NULL REFERENCES tag_groups(id),
                    name TEXT NOT NULL, name_key TEXT NOT NULL,
                    UNIQUE(group_id, name_key));
                CREATE TABLE IF NOT EXISTS image_tags (
                    image_id INTEGER NOT NULL REFERENCES images(id) ON DELETE CASCADE,
                    tag_id INTEGER NOT NULL REFERENCES tags(id) ON DELETE CASCADE,
                    PRIMARY KEY(image_id, tag_id));
                CREATE INDEX IF NOT EXISTS tag_images ON image_tags(tag_id, image_id);
                PRAGMA user_version = 1;
            """)
            if not db.execute("SELECT 1 FROM settings WHERE key='groups_initialized'").fetchone():
                if not db.execute("SELECT 1 FROM tag_groups").fetchone():
                    for name in ("画师", "角色", "场景", "其他"):
                        db.execute("INSERT INTO tag_groups(name,name_key) VALUES (?,?)", (name, name.casefold()))
                db.execute("INSERT INTO settings VALUES ('groups_initialized','1')")
        self.add_source(self.library_dir, "library")

    @contextmanager
    def connection(self):
        db = sqlite3.connect(self.db_path, timeout=30)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA foreign_keys = ON")
        db.execute("PRAGMA journal_mode = WAL")
        try:
            with db:
                yield db
        finally:
            db.close()

    def add_source(self, path: Path, kind: str = "reference"):
        with self.connection() as db:
            db.execute("INSERT OR IGNORE INTO sources(path,kind) VALUES (?,?)", (path_key(path), kind))

    def sources(self) -> list[dict]:
        with self.connection() as db:
            return [dict(row) for row in db.execute("SELECT * FROM sources ORDER BY id")]

    def remove_source(self, source_id: int):
        with self.connection() as db:
            db.execute("DELETE FROM sources WHERE id=? AND kind!='library'", (source_id,))

    def rows(self) -> list[dict]:
        with self.connection() as db:
            images = [dict(row) for row in db.execute("SELECT * FROM images ORDER BY id DESC")]
            links = defaultdict(set)
            for row in db.execute("SELECT image_id,tag_id FROM image_tags"):
                links[row["image_id"]].add(row["tag_id"])
        for row in images:
            row["tags"] = links[row["id"]]
        return images

    def groups(self) -> list[dict]:
        with self.connection() as db:
            return [dict(row) for row in db.execute("SELECT * FROM tag_groups ORDER BY id")]

    def tags(self) -> list[dict]:
        with self.connection() as db:
            return [dict(row) for row in db.execute("""
                SELECT t.*, g.name AS group_name, COUNT(it.image_id) AS count
                FROM tags t JOIN tag_groups g ON g.id=t.group_id
                LEFT JOIN image_tags it ON it.tag_id=t.id
                GROUP BY t.id ORDER BY g.id, t.name COLLATE NOCASE
            """)]

    @staticmethod
    def clean_name(name: str) -> str:
        name = name.strip()
        if not name or len(name) > 100:
            raise ValueError("名称不能为空，且不能超过 100 个字符。")
        return name

    def create_group(self, name: str) -> int:
        name = self.clean_name(name)
        with self.connection() as db:
            db.execute("INSERT OR IGNORE INTO tag_groups(name,name_key) VALUES (?,?)", (name, name.casefold()))
            return db.execute("SELECT id FROM tag_groups WHERE name_key=?", (name.casefold(),)).fetchone()[0]

    def setting(self, key: str, default: str = "") -> str:
        with self.connection() as db:
            row = db.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
            return row[0] if row else default

    def set_setting(self, key: str, value: str):
        with self.connection() as db:
            db.execute("INSERT OR REPLACE INTO settings VALUES (?,?)", (key, value))

    def delete_tags(self, tag_ids: Iterable[int]):
        """Deleting a tag removes its links, never the original images."""
        with self.connection() as db:
            db.executemany("DELETE FROM tags WHERE id=?", [(int(tag),) for tag in tag_ids])

    @staticmethod
    def _move_tags(db, tag_ids, group_id):
        if not db.execute("SELECT 1 FROM tag_groups WHERE id=?", (group_id,)).fetchone():
            raise ValueError("目标分类不存在。")
        try:
            db.executemany("UPDATE tags SET group_id=? WHERE id=?", [(group_id, int(tag)) for tag in tag_ids])
        except sqlite3.IntegrityError as exc:
            raise ValueError("目标分类存在同名标签，移动已取消。请先重命名冲突标签。") from exc

    def move_tags(self, tag_ids: Iterable[int], group_id: int):
        with self.connection() as db:
            self._move_tags(db, tag_ids, group_id)

    def delete_group(self, group_id: int, target_id: int | None = None):
        with self.connection() as db:
            tags = [row[0] for row in db.execute("SELECT id FROM tags WHERE group_id=?", (group_id,))]
            if tags:
                if target_id is None or target_id == group_id:
                    raise ValueError("请先选择其他分类，保留并转移该分类中的标签。")
                self._move_tags(db, tags, target_id)
            db.execute("DELETE FROM tag_groups WHERE id=?", (group_id,))

    def rename_group(self, group_id: int, name: str):
        name = self.clean_name(name)
        with self.connection() as db:
            try:
                db.execute("UPDATE tag_groups SET name=?,name_key=? WHERE id=?", (name, name.casefold(), group_id))
            except sqlite3.IntegrityError as exc:
                raise ValueError("已存在同名分组。") from exc

    def create_tag(self, name: str, group_id: int) -> int:
        name = self.clean_name(name)
        with self.connection() as db:
            db.execute("INSERT OR IGNORE INTO tags(group_id,name,name_key) VALUES (?,?,?)", (group_id, name, name.casefold()))
            return db.execute("SELECT id FROM tags WHERE group_id=? AND name_key=?", (group_id, name.casefold())).fetchone()[0]

    def rename_tag(self, tag_id: int, name: str):
        name = self.clean_name(name)
        with self.connection() as db:
            try:
                db.execute("UPDATE tags SET name=?,name_key=? WHERE id=?", (name, name.casefold(), tag_id))
            except sqlite3.IntegrityError as exc:
                raise ValueError("该分组已有这个标签。请在图片上更换标签；第一版不提供标签合并。") from exc

    def apply_tag(self, image_ids: Iterable[int], tag_id: int, remove: bool = False):
        with self.connection() as db:
            command = "DELETE FROM image_tags WHERE image_id=? AND tag_id=?" if remove else "INSERT OR IGNORE INTO image_tags(image_id,tag_id) VALUES (?,?)"
            db.executemany(command, [(int(i), tag_id) for i in image_ids])

    def replace_tag(self, image_ids: Iterable[int], old_tag: int, new_tag: int):
        with self.connection() as db:
            for image_id in image_ids:
                linked = db.execute("SELECT 1 FROM image_tags WHERE image_id=? AND tag_id=?", (image_id, old_tag)).fetchone()
                if linked:
                    db.execute("DELETE FROM image_tags WHERE image_id=? AND tag_id=?", (image_id, old_tag))
                    db.execute("INSERT OR IGNORE INTO image_tags VALUES (?,?)", (image_id, new_tag))

    def thumb_path(self, digest: str) -> Path:
        return self.cache_dir / f"{digest}.jpg"

    def inspect(self, path: Path) -> dict:
        before = path.stat()
        digest = file_hash(path)
        with Image.open(path) as image:
            fmt = image.format or path.suffix.lstrip(".").upper()
            animated = int(getattr(image, "is_animated", False) and fmt in {"GIF", "WEBP", "PNG", "AVIF"})
            oriented = ImageOps.exif_transpose(image)
            width, height = oriented.size
            target = self.thumb_path(digest)
            if not target.exists():
                oriented.thumbnail((420, 420), Image.Resampling.LANCZOS)
                rgba = oriented.convert("RGBA")
                background = Image.new("RGB", rgba.size, "#f1f3f7")
                background.paste(rgba, mask=rgba.getchannel("A"))
                temp = target.with_suffix(f".{uuid.uuid4().hex}.tmp")
                try:
                    background.save(temp, format="JPEG", quality=86)
                    os.replace(temp, target)
                finally:
                    temp.unlink(missing_ok=True)
        after = path.stat()
        if (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
            raise OSError("文件正在变化，请稍后重新扫描")
        return {"path": path_key(path), "filename": path.name, "sha256": digest,
                "bytes": after.st_size, "mtime_ns": after.st_mtime_ns,
                "width": width, "height": height, "format": fmt, "animated": animated}

    def _store(self, meta: dict, image_id: int | None = None) -> int:
        fields = ("path", "filename", "sha256", "bytes", "mtime_ns", "width", "height", "format", "animated")
        values = [meta[field] for field in fields]
        with self.connection() as db:
            if image_id is None:
                cursor = db.execute(f"INSERT INTO images({','.join(fields)},missing,added_at) VALUES ({','.join('?' for _ in fields)},0,?)", values + [time.time()])
                return cursor.lastrowid
            db.execute(f"UPDATE images SET {','.join(f'{f}=?' for f in fields)},missing=0 WHERE id=?", values + [image_id])
            return image_id

    @staticmethod
    def enumerate_images(paths: Iterable[Path], errors: list[str]) -> list[Path]:
        found: dict[str, Path] = {}
        for root in paths:
            root = Path(root).absolute()
            if root.is_file():
                if root.suffix.lower() in EXTENSIONS:
                    found[path_key(root)] = root
            elif root.is_dir():
                def failed(exc):
                    errors.append(f"无法读取文件夹：{exc}")
                for directory, folders, files in os.walk(root, onerror=failed, followlinks=False):
                    # Do not follow junctions or directory symlinks into loops / unrelated libraries.
                    folders[:] = [f for f in folders if not Path(directory, f).is_symlink() and not Path(directory, f).is_junction()]
                    for name in files:
                        path = Path(directory, name)
                        if path.suffix.lower() in EXTENSIONS:
                            found[path_key(path)] = path
            else:
                errors.append(f"位置不可用：{root}")
        return list(found.values())

    def refresh_missing(self):
        with self.connection() as db:
            rows = db.execute("SELECT id,path FROM images").fetchall()
            db.executemany("UPDATE images SET missing=? WHERE id=?", [(int(not Path(r["path"]).is_file()), r["id"]) for r in rows])

    def scan(self, progress: Callable[[str], None] | None = None) -> Report:
        report = Report()
        roots = [Path(source["path"]) for source in self.sources()]
        known = self.rows()
        files = self.enumerate_images(roots, report.errors)
        seen = {path_key(path) for path in files}
        # Individually referenced files are also checked on every scan.
        files.extend(Path(row["path"]) for row in known if row["path"] not in seen and Path(row["path"]).is_file())
        self.refresh_missing()
        by_path = {row["path"]: row for row in known}
        missing = defaultdict(list)
        for row in known:
            if not Path(row["path"]).is_file():
                missing[row["sha256"]].append(row)
        new_files = defaultdict(list)
        for number, path in enumerate(files, 1):
            if progress:
                progress(f"检查图片 {number}/{len(files)}：{path.name}")
            try:
                old = by_path.get(path_key(path))
                stat = path.stat()
                if old and old["bytes"] == stat.st_size and old["mtime_ns"] == stat.st_mtime_ns and self.thumb_path(old["sha256"]).exists():
                    continue
                meta = self.inspect(path)
                if old:
                    self._store(meta, old["id"])
                    report.updated += 1
                else:
                    new_files[meta["sha256"]].append(meta)
            except (OSError, ValueError, Image.DecompressionBombError) as exc:
                report.errors.append(f"{path.name}：{exc}")
        for digest, metas in new_files.items():
            lost = missing.get(digest, [])
            if len(lost) == 1 and len(metas) == 1:
                self._store(metas[0], lost[0]["id"])
                report.recovered += 1
            elif lost:
                # Ambiguity is never resolved by silently picking a path.
                for row in lost:
                    report.candidates.append((row["id"], [meta["path"] for meta in metas]))
            else:
                for meta in metas:
                    self._store(meta)
                    report.added += 1
        report.missing = sum(row["missing"] for row in self.rows())
        return report

    def import_paths(self, paths: list[Path], mode: str, progress: Callable[[str], None] | None = None) -> Report:
        if mode not in {"reference", "copy", "move"}:
            raise ValueError("未知导入方式")
        report = Report()
        if mode == "reference":
            for path in paths:
                if path.is_dir():
                    self.add_source(path)
            # File references are inserted explicitly before the common scan.
            existing = {row["path"] for row in self.rows()}
            for path in paths:
                if path.is_file() and path_key(path) not in existing:
                    try:
                        self._store(self.inspect(path))
                        report.added += 1
                        existing.add(path_key(path))
                    except (OSError, ValueError, Image.DecompressionBombError) as exc:
                        report.errors.append(f"{path.name}：{exc}")
            scanned = self.scan(progress)
            scanned.added += report.added
            scanned.errors.extend(report.errors)
            return scanned

        # Resolve all inputs before creating destination directories. Nested/overlapping inputs are deduplicated.
        files = self.enumerate_images(paths, report.errors)
        original_rows = {row["path"]: row for row in self.rows()}
        roots = [p.absolute() for p in paths if p.is_dir()]
        destinations: dict[str, Path] = {}
        for source in roots:
            if source == self.library_dir or self.library_dir.is_relative_to(source):
                raise ValueError("导入来源不能包含图片库本身，请选择其他文件夹或使用“保留原位置”。")
            destination = self.library_dir / source.name
            if destination.exists() or destination in destinations.values():
                destination = self.library_dir / f"{source.name}_{uuid.uuid4().hex[:8]}"
            destinations[path_key(source)] = destination

        for index, source in enumerate(files, 1):
            if progress:
                progress(f"{'移动' if mode == 'move' else '复制'} {index}/{len(files)}：{source.name}")
            temp: Path | None = None
            try:
                if source.resolve().is_relative_to(self.library_dir):
                    continue
                root = next((p for p in roots if source.is_relative_to(p)), None)
                target = destinations[path_key(root)] / source.relative_to(root) if root else self.library_dir / source.name
                target.parent.mkdir(parents=True, exist_ok=True)
                if target.exists():
                    target = target.with_name(f"{target.stem}_{uuid.uuid4().hex[:8]}{target.suffix}")
                # Validate/decode before making any changes to a source file.
                source_meta = self.inspect(source)
                temp = target.with_name(f".{target.name}.{uuid.uuid4().hex}.importing")
                shutil.copy2(source, temp)
                if file_hash(temp) != source_meta["sha256"] or file_hash(source) != source_meta["sha256"]:
                    raise OSError("复制校验失败，源文件已保留")
                # Windows rename fails if a competing process created the destination.
                temp.rename(target)
                temp = None
                meta = dict(source_meta, path=path_key(target), filename=target.name)
                old = original_rows.get(path_key(source))
                image_id = self._store(meta, old["id"] if old and mode == "move" else None)
                if old and mode == "copy":
                    with self.connection() as db:
                        db.execute("INSERT OR IGNORE INTO image_tags SELECT ?,tag_id FROM image_tags WHERE image_id=?", (image_id, old["id"]))
                report.added += int(not old or mode == "copy")
                report.updated += int(bool(old) and mode == "move")
                if mode == "move":
                    # Only delete an explicitly selected source after destination + database have succeeded.
                    if file_hash(source) != source_meta["sha256"]:
                        raise OSError("源文件发生变化，已保留源文件及图片库副本")
                    source.unlink()
            except (OSError, ValueError, Image.DecompressionBombError) as exc:
                report.errors.append(f"{source}：{exc}")
            finally:
                if temp:
                    temp.unlink(missing_ok=True)
        self.refresh_missing()
        report.missing = sum(row["missing"] for row in self.rows())
        return report

    def relink(self, image_id: int, target: Path, allow_changed: bool = False):
        meta = self.inspect(target)
        with self.connection() as db:
            old = db.execute("SELECT * FROM images WHERE id=?", (image_id,)).fetchone()
            owner = db.execute("SELECT id FROM images WHERE path=? AND id!=?", (meta["path"], image_id)).fetchone()
            if owner:
                raise ValueError("这个文件已关联到其他图片记录，请选择另一个位置。")
            if not old:
                raise ValueError("图片记录不存在。")
            if old["sha256"] != meta["sha256"] and not allow_changed:
                raise ValueError("内容指纹不同。请确认是否将原有标签关联到这个文件。")
        self._store(meta, image_id)

    def relocate_source(self, source_id: int, new_root: Path, progress=None) -> Report:
        source = next((s for s in self.sources() if s["id"] == source_id), None)
        if not source:
            raise ValueError("来源文件夹不存在。")
        report = self.recover([new_root], progress, old_root=Path(source["path"]))
        # Keep the old source until every missing record under it has been accounted for.
        remaining = [row for row in self.rows() if row["missing"] and Path(row["path"]).is_relative_to(Path(source["path"]))]
        if source["kind"] != "library" and not remaining:
            self.remove_source(source_id)
        self.add_source(new_root)
        return report

    def recover(self, roots: list[Path], progress=None, old_root: Path | None = None) -> Report:
        self.refresh_missing()
        report = Report()
        rows = self.rows()
        lost = [r for r in rows if r["missing"] and (old_root is None or Path(r["path"]).is_relative_to(old_root))]
        hashes = {row["sha256"] for row in lost}
        owned = {row["path"] for row in rows}
        candidates = defaultdict(list)
        files = self.enumerate_images(roots, report.errors)
        sizes = {row["bytes"] for row in lost}
        for index, path in enumerate(files, 1):
            if progress:
                progress(f"查找原图 {index}/{len(files)}：{path.name}")
            try:
                if path_key(path) in owned or path.stat().st_size not in sizes:
                    continue
                digest = file_hash(path)
                if digest in hashes:
                    candidates[digest].append(path)
            except OSError as exc:
                report.errors.append(f"{path}：{exc}")
        lost_by_hash = defaultdict(list)
        for row in lost:
            lost_by_hash[row["sha256"]].append(row)
        for digest, group in lost_by_hash.items():
            options = candidates[digest]
            if len(group) == 1 and len(options) == 1:
                try:
                    self.relink(group[0]["id"], options[0])
                    report.recovered += 1
                except (OSError, ValueError, Image.DecompressionBombError) as exc:
                    report.errors.append(str(exc))
            elif options:
                for row in group:
                    report.candidates.append((row["id"], [str(path) for path in options]))
        report.missing = sum(row["missing"] for row in self.rows())
        return report

    def backup(self, target: Path):
        if target.resolve() == self.db_path.resolve():
            raise ValueError("备份位置不能是当前数据库。")
        with self.connection() as db:
            payload = {"application": "ImageTagManager", "version": SCHEMA_VERSION,
                       "created_at": time.time(), "library_path": str(self.library_dir)}
            for table in ("sources", "images", "tag_groups", "tags", "image_tags"):
                payload[table] = [dict(row) for row in db.execute(f"SELECT * FROM {table}")]
        temp = target.with_name(f".{target.name}.{uuid.uuid4().hex}.tmp")
        try:
            temp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
            os.replace(temp, target)
        finally:
            temp.unlink(missing_ok=True)

    def restore(self, source: Path) -> Path:
        payload = json.loads(source.read_text(encoding="utf-8"))
        if payload.get("application") != "ImageTagManager" or payload.get("version") != SCHEMA_VERSION:
            raise ValueError("这不是兼容的 ImageTagManager 备份。")
        tables = {
            "sources": ("id", "path", "kind"),
            "images": ("id", "path", "filename", "sha256", "bytes", "mtime_ns", "width", "height", "format", "animated", "missing", "added_at"),
            "tag_groups": ("id", "name", "name_key"),
            "tags": ("id", "group_id", "name", "name_key"),
            "image_tags": ("image_id", "tag_id"),
        }
        for table, columns in tables.items():
            if not isinstance(payload.get(table), list):
                raise ValueError(f"备份缺少有效的 {table} 数据。")
            for row in payload[table]:
                if not isinstance(row, dict) or any(column not in row for column in columns):
                    raise ValueError(f"备份中的 {table} 记录不完整。")
        # Validate constraints in an isolated DB before touching the active catalogue.
        with tempfile.TemporaryDirectory(prefix="imagetag-restore-") as temporary:
            check = Catalogue(Path(temporary) / "data", Path(temporary) / "library")
            check._restore_tables(payload, tables)
        recovery = self.data_dir / "backups" / f"before-restore-{time.strftime('%Y%m%d-%H%M%S')}-{uuid.uuid4().hex[:6]}.json"
        recovery.parent.mkdir(exist_ok=True)
        self.backup(recovery)
        self._restore_tables(payload, tables)
        self.add_source(self.library_dir, "library")
        self.refresh_missing()
        return recovery

    def _restore_tables(self, payload, tables):
        with self.connection() as db:
            for table in reversed(tables):
                db.execute(f"DELETE FROM {table}")
            for table, columns in tables.items():
                db.executemany(f"INSERT INTO {table}({','.join(columns)}) VALUES ({','.join('?' for _ in columns)})", [[row[c] for c in columns] for row in payload[table]])
            violations = db.execute("PRAGMA foreign_key_check").fetchall()
            if violations:
                raise ValueError("备份的标签关联数据不完整。")


def filter_images(rows: list[dict], tags: list[dict], query="", search_mode="全部", selected_tags=None,
                  intersection=True, scope="全部图片", source=None, sort="导入时间", descending=True) -> list[dict]:
    selected_tags = set(selected_tags or ())
    tag_names = {tag["id"]: (tag["group_name"] + ":" + tag["name"]).casefold() for tag in tags}
    query = query.strip().casefold()
    result = []
    for row in rows:
        attached = row["tags"]
        if scope == "未打标签" and attached:
            continue
        if scope == "原图缺失" and not row["missing"]:
            continue
        if source and not Path(row["path"]).is_relative_to(Path(source)):
            continue
        if selected_tags and not (selected_tags <= attached if intersection else bool(selected_tags & attached)):
            continue
        if query:
            filename_match = query in row["filename"].casefold()
            tag_match = any(query in tag_names.get(tag, "") for tag in attached)
            if search_mode == "文件名" and not filename_match:
                continue
            if search_mode == "标签" and not tag_match:
                continue
            if search_mode == "全部" and not (filename_match or tag_match):
                continue
        result.append(row)
    keys = {"文件名": lambda r: r["filename"].casefold(), "修改时间": lambda r: r["mtime_ns"],
            "图片分辨率": lambda r: r["width"] * r["height"], "文件大小": lambda r: r["bytes"],
            "导入时间": lambda r: r["added_at"]}
    return sorted(result, key=keys.get(sort, keys["导入时间"]), reverse=descending)
