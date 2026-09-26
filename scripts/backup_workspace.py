"""Create, verify, and restore consistent workspace backups."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import secrets
import shutil
import sqlite3
import sys
import tempfile
import zipfile
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath, PureWindowsPath
from shutil import copyfileobj

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "apps" / "api"))

from app.config import settings
from app.runtime.process_guard import ServiceProcessGuard

MAX_ARCHIVE_FILES = 200_000
MAX_MANIFEST_BYTES = 16 * 1024 * 1024
MAX_RESTORE_BYTES = 100 * 1024 * 1024 * 1024
COPY_CHUNK_BYTES = 1024 * 1024
WINDOWS_RESERVED_NAMES = {"CON", "PRN", "AUX", "NUL", *(f"COM{i}" for i in range(1, 10)), *(f"LPT{i}" for i in range(1, 10))}


def _targets() -> tuple[Path, Path]:
    url = settings.database_url
    if not url.startswith("sqlite:///") or url.endswith(":memory:"):
        raise ValueError("工作区备份目前要求使用文件型 SQLite 数据库")
    raw_path = url.removeprefix("sqlite:///")
    database = Path(raw_path)
    if not database.is_absolute():
        database = (Path.cwd() / database).resolve()
    return database, settings.artifact_root.resolve()


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _sqlite_snapshot(database: Path, target: Path) -> None:
    if not database.is_file():
        raise FileNotFoundError(f"数据库不存在：{database}")
    source = sqlite3.connect(database, timeout=30)
    destination = sqlite3.connect(target)
    try:
        source.backup(destination)
        result = destination.execute("PRAGMA integrity_check").fetchone()
        if not result or result[0] != "ok":
            raise RuntimeError(f"数据库快照完整性检查失败：{result}")
    finally:
        destination.close()
        source.close()


def create_backup(archive: Path) -> None:
    database, artifacts = _targets()
    with ServiceProcessGuard(artifacts):
        _create_backup_locked(archive, database, artifacts)


def _create_backup_locked(archive: Path, database: Path, artifacts: Path) -> None:
    archive = archive.resolve()
    archive.parent.mkdir(parents=True, exist_ok=True)
    if archive == database or database in archive.parents or archive == artifacts or artifacts in archive.parents:
        raise ValueError("备份包必须保存在数据库和产物目录之外")
    with tempfile.TemporaryDirectory(prefix="yingzhang-backup-") as temp_name:
        temp = Path(temp_name)
        db_copy = temp / "database.sqlite3"
        _sqlite_snapshot(database, db_copy)
        files = {"database/yingzhang.sqlite3": db_copy}
        if artifacts.exists():
            for path in artifacts.rglob("*"):
                if (
                    path.is_file()
                    and not path.is_symlink()
                    and path.name not in {".service-instance.lock", ".personal-memory.lock"}
                ):
                    files[(PurePosixPath("artifacts") / path.relative_to(artifacts).as_posix()).as_posix()] = path
        manifest = {
            "format": "yingzhang-workspace-backup-v1",
            "createdAt": datetime.now(UTC).isoformat(),
            "files": {name: _sha256(path) for name, path in sorted(files.items())},
        }
        descriptor, temporary_name = tempfile.mkstemp(
            prefix=f".{archive.name}.", suffix=".tmp", dir=archive.parent
        )
        os.close(descriptor)
        temporary_archive = Path(temporary_name)
        try:
            with zipfile.ZipFile(temporary_archive, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as bundle:
                for name, path in files.items():
                    bundle.write(path, name)
                bundle.writestr("manifest.json", json.dumps(manifest, ensure_ascii=False, indent=2))
            os.replace(temporary_archive, archive)
        finally:
            temporary_archive.unlink(missing_ok=True)
    print(f"备份完成：{archive}（{len(files)} 个文件）")


def verify_backup(archive: Path) -> dict:
    with zipfile.ZipFile(archive) as bundle:
        entries = bundle.infolist()
        if len(entries) > MAX_ARCHIVE_FILES:
            raise ValueError("备份包含过多文件")
        names = [entry.filename for entry in entries]
        if (
            len(names) != len(set(names))
            or len(names) != len({name.casefold() for name in names})
            or names.count("manifest.json") != 1
        ):
            raise ValueError("备份包含重复文件名或缺少唯一清单")
        manifest_entry = bundle.getinfo("manifest.json")
        if manifest_entry.file_size > MAX_MANIFEST_BYTES:
            raise ValueError("备份清单过大")
        manifest = json.loads(bundle.read(manifest_entry))
        if not isinstance(manifest, dict):
            raise TypeError("备份清单格式错误")
        if manifest.get("format") != "yingzhang-workspace-backup-v1":
            raise ValueError("不支持的备份格式")
        expected = manifest.get("files")
        if (
            not isinstance(expected, dict)
            or any(not isinstance(name, str) or not isinstance(digest, str) for name, digest in expected.items())
            or set(expected) | {"manifest.json"} != set(names)
        ):
            raise ValueError("备份清单与压缩包内容不一致")
        total_uncompressed = 0
        for name, digest in expected.items():
            if len(digest) != 64 or any(character not in "0123456789abcdef" for character in digest):
                raise ValueError(f"备份清单中的 SHA-256 摘要格式错误：{name}")
            path = PurePosixPath(name)
            windows_path = PureWindowsPath(name)
            windows_parts = path.parts[1:]
            invalid_windows_component = any(
                part.endswith((".", " "))
                or any(ord(character) < 32 or character in '<>"|?*' for character in part)
                or part.split(".", 1)[0].upper() in WINDOWS_RESERVED_NAMES
                for part in windows_parts
            )
            if (
                "\\" in name
                or ":" in name
                or "\x00" in name
                or path.as_posix() != name
                or path.is_absolute()
                or windows_path.is_absolute()
                or bool(windows_path.drive)
                or invalid_windows_component
                or ".." in path.parts
                or not path.parts
                or path.parts[0] not in {"database", "artifacts"}
                or name != "database/yingzhang.sqlite3" and path.parts[0] == "database"
            ):
                raise ValueError(f"备份包含非法路径：{name}")
            info = bundle.getinfo(name)
            if info.is_dir() or info.flag_bits & 0x1:
                raise ValueError(f"不支持加密备份成员：{name}")
            total_uncompressed += info.file_size
            if total_uncompressed > MAX_RESTORE_BYTES:
                raise ValueError("备份解压后超过 100 GiB 安全上限")
            hasher = hashlib.sha256()
            with bundle.open(info) as stream:
                for chunk in iter(lambda: stream.read(COPY_CHUNK_BYTES), b""):
                    hasher.update(chunk)
            if hasher.hexdigest() != digest:
                raise ValueError(f"备份文件校验失败：{name}")
        if "database/yingzhang.sqlite3" not in expected:
            raise ValueError("备份缺少数据库")
        return manifest


def restore_backup(archive: Path) -> None:
    database, artifacts = _targets()
    with ServiceProcessGuard(artifacts):
        _restore_backup_locked(archive, database, artifacts)


def _restore_backup_locked(archive: Path, database: Path, artifacts: Path) -> None:
    manifest = verify_backup(archive)
    archive = archive.resolve()
    if archive == database or archive == artifacts or artifacts in archive.parents:
        raise ValueError("备份包不能位于将被恢复覆盖的数据目录中")
    database.parent.mkdir(parents=True, exist_ok=True)
    artifacts.parent.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ") + "-" + secrets.token_hex(4)
    safety_archive = archive.with_name(f"{archive.stem}.before-restore-{stamp}{archive.suffix}")
    if database.exists():
        _create_backup_locked(safety_archive, database, artifacts)
    with tempfile.TemporaryDirectory(prefix="yingzhang-restore-") as temp_name:
        staging = Path(temp_name)
        with zipfile.ZipFile(archive) as bundle:
            for name in manifest["files"]:
                target = staging.joinpath(*PurePosixPath(name).parts)
                target.parent.mkdir(parents=True, exist_ok=True)
                with bundle.open(name) as source, target.open("wb") as destination:
                    copyfileobj(source, destination, COPY_CHUNK_BYTES)
        staged_db = staging / "database" / "yingzhang.sqlite3"
        with sqlite3.connect(staged_db) as connection:
            check = connection.execute("PRAGMA integrity_check").fetchone()
            if not check or check[0] != "ok":
                raise RuntimeError("备份数据库完整性检查失败")
        staged_artifacts = staging / "artifacts"
        staged_artifacts.mkdir(exist_ok=True)
        old_db = database.with_name(database.name + f".before-restore-{stamp}")
        old_artifacts = artifacts.with_name(artifacts.name + f".before-restore-{stamp}")
        sidecars = {
            suffix: Path(str(database) + suffix)
            for suffix in ("-wal", "-shm", "-journal")
        }
        saved_sidecars = {
            suffix: Path(str(old_db) + suffix) for suffix in sidecars
        }
        with (
            tempfile.TemporaryDirectory(prefix=".yingzhang-db-restore-", dir=database.parent) as db_stage_name,
            tempfile.TemporaryDirectory(prefix=".yingzhang-artifact-restore-", dir=artifacts.parent) as artifact_stage_name,
        ):
            new_db = Path(db_stage_name) / database.name
            new_artifacts = Path(artifact_stage_name) / artifacts.name
            shutil.copy2(staged_db, new_db)
            shutil.copytree(staged_artifacts, new_artifacts)
            moved_sidecars: set[str] = set()
            moved_db = moved_artifacts = installed_db = installed_artifacts = False
            try:
                if database.exists():
                    os.replace(database, old_db)
                    moved_db = True
                for suffix, sidecar in sidecars.items():
                    if sidecar.exists():
                        os.replace(sidecar, saved_sidecars[suffix])
                        moved_sidecars.add(suffix)
                if artifacts.exists():
                    os.replace(artifacts, old_artifacts)
                    moved_artifacts = True
                os.replace(new_db, database)
                installed_db = True
                os.replace(new_artifacts, artifacts)
                installed_artifacts = True
            except Exception:
                if installed_artifacts and artifacts.exists():
                    shutil.rmtree(artifacts)
                if installed_db and database.exists():
                    database.unlink()
                if moved_db and old_db.exists():
                    os.replace(old_db, database)
                for suffix in moved_sidecars:
                    if saved_sidecars[suffix].exists():
                        os.replace(saved_sidecars[suffix], sidecars[suffix])
                if moved_artifacts and old_artifacts.exists():
                    os.replace(old_artifacts, artifacts)
                raise
    print(f"恢复完成：{database}；旧数据安全副本：{safety_archive if safety_archive.exists() else '未生成'}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    create = commands.add_parser("create", help="生成数据库和产物的一致备份")
    create.add_argument("archive", type=Path)
    verify = commands.add_parser("verify", help="校验备份包及全部文件摘要")
    verify.add_argument("archive", type=Path)
    restore = commands.add_parser("restore", help="恢复数据库和产物；会先保存现有工作区")
    restore.add_argument("archive", type=Path)
    restore.add_argument("--confirm", action="store_true", help="确认覆盖当前工作区")
    args = parser.parse_args()
    try:
        if args.command == "create":
            create_backup(args.archive)
        elif args.command == "verify":
            manifest = verify_backup(args.archive)
            print(f"备份有效：{manifest['createdAt']}，{len(manifest['files'])} 个文件")
        elif not args.confirm:
            parser.error("恢复会替换当前工作区；请增加 --confirm 明确确认")
        else:
            restore_backup(args.archive)
    except (OSError, ValueError, TypeError, RuntimeError, zipfile.BadZipFile, json.JSONDecodeError) as exc:
        print(f"失败：{exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
