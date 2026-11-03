"""Alembic environment: runs the migrations in ``versions/`` against the SQLite database given by
``sqlalchemy.url`` (set by ``app.db.init_db``; the command line uses ``alembic.ini``)."""

from __future__ import annotations

from alembic import context
from sqlalchemy import create_engine, pool

config = context.config


def run_migrations() -> None:
    url = config.get_main_option("sqlalchemy.url")
    engine = create_engine(url, poolclass=pool.NullPool, connect_args={"timeout": 30})
    with engine.connect() as connection:
        context.configure(connection=connection, target_metadata=None, render_as_batch=True)
        with context.begin_transaction():
            context.run_migrations()
    engine.dispose()


run_migrations()
