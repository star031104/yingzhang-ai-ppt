import importlib.util
import sqlite3
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "repair-local-database.py"
spec = importlib.util.spec_from_file_location("repair_local_database", SCRIPT)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def make_database(path: Path, *, unexpected: bool = False) -> None:
    with sqlite3.connect(path) as connection:
        connection.executescript(
            """
            CREATE TABLE slide_specs (id TEXT PRIMARY KEY);
            CREATE TABLE slide_versions (
              id TEXT PRIMARY KEY, slide_id TEXT REFERENCES slide_specs(id)
            );
            CREATE TABLE slide_candidates (
              id TEXT PRIMARY KEY, slide_id TEXT REFERENCES slide_specs(id)
            );
            INSERT INTO slide_specs VALUES ('kept');
            INSERT INTO slide_versions VALUES ('version-kept', 'kept');
            INSERT INTO slide_versions VALUES ('version-orphan', 'deleted');
            INSERT INTO slide_candidates VALUES ('candidate-orphan', 'deleted');
            """
        )
        if unexpected:
            connection.executescript(
                """
                CREATE TABLE other_child (
                  id TEXT PRIMARY KEY, slide_id TEXT REFERENCES slide_specs(id)
                );
                INSERT INTO other_child VALUES ('other-orphan', 'deleted');
                """
            )


def test_repairs_only_known_orphans_after_complete_backup(tmp_path):
    database = tmp_path / "workspace.sqlite3"
    make_database(database)

    backup, counts = module.repair_database(database, tmp_path / "backups")

    assert counts == {"slide_candidates": 1, "slide_versions": 1}
    assert backup.is_file()
    with sqlite3.connect(backup) as snapshot:
        assert len(snapshot.execute("PRAGMA foreign_key_check").fetchall()) == 2
        assert snapshot.execute("SELECT COUNT(*) FROM slide_versions").fetchone() == (2,)
    with sqlite3.connect(database) as connection:
        assert connection.execute("PRAGMA foreign_key_check").fetchall() == []
        assert connection.execute("SELECT id FROM slide_versions").fetchall() == [("version-kept",)]
        assert connection.execute("SELECT id FROM slide_specs").fetchall() == [("kept",)]
    assert module.repair_database(database, tmp_path / "backups") == (None, {})


def test_refuses_other_foreign_key_damage(tmp_path):
    database = tmp_path / "workspace.sqlite3"
    make_database(database, unexpected=True)
    with pytest.raises(RuntimeError, match="其他类型"):
        module.repair_database(database, tmp_path / "backups")
    with sqlite3.connect(database) as connection:
        assert len(connection.execute("PRAGMA foreign_key_check").fetchall()) == 3
    assert not (tmp_path / "backups").exists()
