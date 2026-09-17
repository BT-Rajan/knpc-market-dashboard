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
    ("news_items", "category", "VARCHAR(40) NULL"),
    ("news_items", "sentiment", "VARCHAR(10) NULL"),
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

    _drop_price_history_unique_constraint(engine, inspector, existing_tables)


def _drop_price_history_unique_constraint(engine: Engine, inspector, existing_tables):
    """One-time cleanup: price_history used to have a UNIQUE(item_id,
    price_date) key, which made every scrape after the first one that day
    silently overwrite the earlier reading. Scraping is now append-only (see
    app/scraper/runner.py), so that constraint has to go -- otherwise the
    second insert on the same day just raises an IntegrityError. Replaced by
    a plain (non-unique) index of the same shape for query performance,
    added via create_all()/the model's __table_args__."""
    if "price_history" not in existing_tables:
        return
    existing_index_names = {ix["name"] for ix in inspector.get_indexes("price_history")}
    if "uq_item_price_date" not in existing_index_names:
        return
    with engine.begin() as conn:
        conn.execute(text("ALTER TABLE price_history DROP INDEX uq_item_price_date"))
    logger.info("Migration: dropped price_history.uq_item_price_date (scraping is now append-only)")
