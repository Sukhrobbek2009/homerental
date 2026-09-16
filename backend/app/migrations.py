from sqlalchemy import inspect, text
from sqlalchemy.engine import Engine

# SQLite has no migration framework wired up yet. Base.metadata.create_all only
# creates tables that don't exist, so columns added to an already-existing
# table (like "listings") need to be patched in by hand here.
_LISTING_COLUMNS = {
    "verified": "BOOLEAN NOT NULL DEFAULT 0",
    "guest_favorite": "BOOLEAN NOT NULL DEFAULT 0",
    "amenities": "TEXT",
    "available_from": "DATE",
    "available_to": "DATE",
}

_REVIEW_COLUMNS = {
    "host_reply": "TEXT",
    "flagged": "BOOLEAN NOT NULL DEFAULT 0",
}

_USER_COLUMNS = {
    "verified": "BOOLEAN NOT NULL DEFAULT 0",
    "verification_requested": "BOOLEAN NOT NULL DEFAULT 0",
}


def _add_missing_columns(engine: Engine, table: str, columns: dict[str, str]) -> None:
    inspector = inspect(engine)
    if table not in inspector.get_table_names():
        return

    existing = {col["name"] for col in inspector.get_columns(table)}
    missing = {name: ddl for name, ddl in columns.items() if name not in existing}
    if not missing:
        return

    with engine.begin() as conn:
        for name, ddl in missing.items():
            conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {name} {ddl}"))


def ensure_listing_columns(engine: Engine) -> None:
    _add_missing_columns(engine, "listings", _LISTING_COLUMNS)


def ensure_review_columns(engine: Engine) -> None:
    _add_missing_columns(engine, "reviews", _REVIEW_COLUMNS)


def ensure_user_columns(engine: Engine) -> None:
    _add_missing_columns(engine, "users", _USER_COLUMNS)
