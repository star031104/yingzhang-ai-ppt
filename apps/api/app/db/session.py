from pathlib import Path

from app.config import settings
from sqlalchemy import UniqueConstraint, create_engine, event, inspect
from sqlalchemy.orm import sessionmaker

if settings.database_url.startswith("sqlite:///") and ":memory:" not in settings.database_url:
    Path(settings.database_url.removeprefix("sqlite:///")).resolve().parent.mkdir(
        parents=True, exist_ok=True
    )
engine = create_engine(
    settings.database_url,
    connect_args={"check_same_thread": False} if settings.database_url.startswith("sqlite") else {},
)
SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)


if settings.database_url.startswith("sqlite"):
    @event.listens_for(engine, "connect")
    def enable_secure_delete(connection, _record):
        # Ordinary memory rows must not remain in SQLite free pages after DELETE.
        connection.execute("PRAGMA secure_delete=ON")
        connection.execute("PRAGMA foreign_keys=ON")


def get_db():
    with SessionLocal() as session:
        yield session


def create_schema():
    """Apply checked-in revisions and refuse to run against an un-migrated model."""
    from alembic import command
    from alembic.config import Config
    from app.config import settings

    config_path = Path(__file__).resolve().parents[2] / "alembic.ini"
    config = Config(str(config_path))
    if settings.migrate_on_startup:
        command.upgrade(config, "head")
    else:
        from alembic.script import ScriptDirectory

        heads = set(ScriptDirectory.from_config(config).get_heads())
        inspector = inspect(engine)
        if not inspector.has_table("alembic_version"):
            raise RuntimeError("数据库尚未迁移；请先执行 Alembic upgrade head。")
        with engine.connect() as connection:
            current = set(connection.exec_driver_sql("SELECT version_num FROM alembic_version").scalars())
        if current != heads:
            raise RuntimeError(
                f"数据库迁移版本 {sorted(current)} 与应用版本 {sorted(heads)} 不一致。"
            )
    assert_schema_compatible()


def assert_schema_compatible():
    """Fail at startup with an actionable error when a model change lacks a migration."""
    from app.db.models import Base

    inspector = inspect(engine)
    if engine.dialect.name == "sqlite":
        with engine.connect() as connection:
            violations = connection.exec_driver_sql("PRAGMA foreign_key_check").fetchmany(10)
        if violations:
            raise RuntimeError(
                "数据库已有外键不一致记录，应用已停止启动以避免继续扩大数据问题。"
                f" 请先检查并修复这些记录：{violations}"
            )
    database_tables = set(inspector.get_table_names())
    missing_tables = sorted(set(Base.metadata.tables) - database_tables)
    drift = {}
    for name, table in Base.metadata.tables.items():
        if name not in database_tables:
            continue
        expected = {column.name for column in table.columns}
        actual = {column["name"] for column in inspector.get_columns(name)}
        missing_indexes = {
            index.name for index in table.indexes
        } - {index["name"] for index in inspector.get_indexes(name)}
        expected_foreign_keys = {
            (tuple(column.name for column in key.columns), key.elements[0].target_fullname)
            for key in table.foreign_key_constraints
        }
        actual_foreign_keys = {
            (tuple(key.get("constrained_columns") or ()),
             f"{key.get('referred_table')}.{(key.get('referred_columns') or [''])[0]}")
            for key in inspector.get_foreign_keys(name)
        }
        missing_foreign_keys = expected_foreign_keys - actual_foreign_keys
        expected_unique = {
            frozenset(column.name for column in constraint.columns)
            for constraint in table.constraints
            if isinstance(constraint, UniqueConstraint)
        }
        actual_unique = {
            frozenset(item.get("column_names") or ())
            for item in inspector.get_unique_constraints(name)
        }
        missing_unique = expected_unique - actual_unique
        if expected != actual or missing_indexes or missing_foreign_keys or missing_unique:
            drift[name] = {
                "missingColumns": sorted(expected - actual),
                "extraColumns": sorted(actual - expected),
                "missingIndexes": sorted(missing_indexes),
                "missingForeignKeys": sorted(map(str, missing_foreign_keys)),
                "missingUniqueConstraints": sorted(map(str, missing_unique)),
            }
    if missing_tables or drift:
        raise RuntimeError(
            "数据库结构与当前应用不兼容；请先创建并执行 Alembic 迁移。"
            f" 缺少数据表: {missing_tables}; 字段差异: {drift}"
        )
