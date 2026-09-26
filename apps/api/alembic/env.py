from pathlib import Path

from alembic import context
from app.config import settings
from app.db.models import Base
from sqlalchemy import engine_from_config, pool
from sqlalchemy.engine import make_url

config = context.config
# Keep migrations on the same configured database as the application. Escape
# percent signs because Config uses ConfigParser interpolation internally.
database_url = config.attributes.get("database_url", settings.database_url)
parsed_url = make_url(database_url)
if parsed_url.get_backend_name() == "sqlite" and parsed_url.database not in (None, ":memory:"):
    Path(parsed_url.database).expanduser().resolve().parent.mkdir(parents=True, exist_ok=True)
config.set_main_option("sqlalchemy.url", database_url.replace("%", "%%"))
target_metadata = Base.metadata
connectable = engine_from_config(
    config.get_section(config.config_ini_section), prefix="sqlalchemy.", poolclass=pool.NullPool
)
with connectable.connect() as connection:
    context.configure(connection=connection, target_metadata=target_metadata, compare_type=True)
    with context.begin_transaction():
        context.run_migrations()
