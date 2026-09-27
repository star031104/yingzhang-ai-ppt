"""Back up and remove legacy slide children whose parent slide no longer exists."""

from __future__ import annotations

import argparse
import sqlite3
import sys
import uuid
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path

REPAIRABLE = {("slide_candidates", "slide_specs"), ("slide_versions", "slide_specs")}
ORPHAN_QUERIES = {
    "slide_candidates": "DELETE FROM slide_candidates WHERE NOT EXISTS "
    "(SELECT 1 FROM slide_specs WHERE slide_specs.id = slide_candidates.slide_id)",
    "slide_versions": "DELETE FROM slide_versions WHERE NOT EXISTS "
    "(SELECT 1 FROM slide_specs WHERE slide_specs.id = slide_versions.slide_id)",
}


def repair_database(database: Path, backup_dir: Path) -> tuple[Path | None, dict[str, int]]:
    if not database.is_file():
        return None, {}
    connection = sqlite3.connect(database, timeout=30)
    try:
        connection.execute("PRAGMA foreign_keys=ON")
        if connection.execute("PRAGMA integrity_check").fetchone() != ("ok",):
            raise RuntimeError("数据库文件完整性检查失败；未修改数据")
        violations = connection.execute("PRAGMA foreign_key_check").fetchall()
        if not violations:
            return None, {}
        unexpected = [(table, parent) for table, _, parent, _ in violations
                      if (table, parent) not in REPAIRABLE]
        if unexpected:
            raise RuntimeError(f"发现其他类型的外键异常 {sorted(set(unexpected))}；未修改数据")

        counts = dict(Counter(table for table, _, _, _ in violations))
        backup_dir.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
        backup = backup_dir / f"yingzhang-before-orphan-repair-{stamp}-{uuid.uuid4().hex[:8]}.sqlite3"
        snapshot = sqlite3.connect(backup)
        try:
            connection.backup(snapshot)
            if snapshot.execute("PRAGMA integrity_check").fetchone() != ("ok",):
                raise RuntimeError("数据库备份校验失败；未修改数据")
        finally:
            snapshot.close()

        try:
            connection.execute("BEGIN IMMEDIATE")
            if connection.execute("PRAGMA foreign_key_check").fetchall() != violations:
                raise RuntimeError("数据库在备份后发生变化；未修改数据，请重试")
            for table, query in ORPHAN_QUERIES.items():
                removed = connection.execute(query).rowcount
                if removed != counts.get(table, 0):
                    raise RuntimeError(f"{table} 孤立记录数量发生变化；未修改数据")
            if connection.execute("PRAGMA foreign_key_check").fetchone():
                raise RuntimeError("修复后仍存在外键异常；未修改数据")
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        return backup, counts
    finally:
        connection.close()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database", type=Path, help="SQLite database for an isolated repair")
    parser.add_argument("--backup-dir", type=Path)
    args = parser.parse_args()
    if args.database:
        database = args.database.resolve()
    else:
        sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "apps" / "api"))
        from app.config import settings

        if not settings.database_url.startswith("sqlite:///") or settings.database_url.endswith(":memory:"):
            print("No local SQLite database to repair.")
            return 0
        database = Path(settings.database_url.removeprefix("sqlite:///")).resolve()
    backup, counts = repair_database(database, (args.backup_dir or database.parent / "backups").resolve())
    if backup:
        print(f"Repaired legacy orphan slide records: {counts}. Database backup: {backup}")
    else:
        print("Local database integrity check passed.")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, sqlite3.Error, RuntimeError) as exc:
        print(f"Local database repair failed: {exc}", file=sys.stderr)
        raise SystemExit(1)
