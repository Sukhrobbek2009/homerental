from sqlalchemy import inspect, text
from sqlalchemy.engine import Engine

# SQLite has no migration framework wired up yet. Base.metadata.create_all only
# creates tables that don't exist, so columns added to an already-existing
# table (like "listings") need to be patched in by hand here.
_LISTING_COLUMNS = {
    "rating": "FLOAT",
    "verified": "BOOLEAN NOT NULL DEFAULT 0",
    "guest_favorite": "BOOLEAN NOT NULL DEFAULT 0",
}


def ensure_listing_columns(engine: Engine) -> None:
    inspector = inspect(engine)
    if "listings" not in inspector.get_table_names():
        return

    existing = {col["name"] for col in inspector.get_columns("listings")}
    missing = {name: ddl for name, ddl in _LISTING_COLUMNS.items() if name not in existing}
    if not missing:
        return

    with engine.begin() as conn:
        for name, ddl in missing.items():
            conn.execute(text(f"ALTER TABLE listings ADD COLUMN {name} {ddl}"))
