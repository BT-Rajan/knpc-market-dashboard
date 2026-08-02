"""Tiny additive-migration runner. This project has no Alembic -- schema
changes are almost always 'add a column with a default', so this checks
information_schema for what's missing and ALTERs it in. Never drops or
renames anything; if a migration needs more than that, do it by hand.

Runs before Base.metadata.create_all() on every startup, so it only
matters for tables that already existed on disk before the column was
added to the model -- create_all() handles brand-new tables/columns for
everyone else fine on its own.
"""
import logging

from sqlalchemy import inspect, text
from sqlalchemy.engine import Engine

logger = logging.getLogger("knpc.migrations")

# (table, column, DDL column-definition)
ADDITIVE_COLUMNS = [
    ("email_credentials", "last_success_at", "DATETIME NULL"),
    ("email_credentials", "last_failure_at", "DATETIME NULL"),
    ("email_credentials", "last_failure_message", "TEXT NULL"),
    ("email_credentials", "consecutive_failures", "INT DEFAULT 0"),
]


def run_additive_migrations(engine: Engine):
    inspector = inspect(engine)
    existing_tables = set(inspector.get_table_names())

    for table, column, ddl in ADDITIVE_COLUMNS:
        if table not in existing_tables:
            continue  # create_all() will make the whole table (with this column) from scratch
        existing_columns = {c["name"] for c in inspector.get_columns(table)}
        if column in existing_columns:
            continue
        with engine.begin() as conn:
            conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {column} {ddl}"))
        logger.info("Migration: added %s.%s", table, column)
