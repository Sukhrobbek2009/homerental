"""prevent overlapping bookings per listing

Revision ID: c7e4a1d9b2f5
Revises: b3c1f2a9d4e7
Create Date: 2026-09-29 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c7e4a1d9b2f5'
down_revision: Union[str, None] = 'b3c1f2a9d4e7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

CONSTRAINT_NAME = 'bookings_no_overlapping_dates'


def upgrade() -> None:
    # Exclusion constraints are Postgres-only; SQLite (local dev/tests) relies
    # on the endpoint's own overlap checks instead.
    if op.get_bind().dialect.name != 'postgresql':
        return

    # Fail with the offending rows rather than a bare constraint error, and
    # leave it to a person to decide which booking to cancel.
    conflicts = op.get_bind().execute(sa.text(
        """
        SELECT a.id, b.id FROM bookings a
        JOIN bookings b
          ON a.listing_id = b.listing_id
         AND a.id < b.id
         AND daterange(a.start_date, a.end_date, '[)') && daterange(b.start_date, b.end_date, '[)')
        WHERE a.status <> 'cancelled' AND b.status <> 'cancelled'
        """
    )).fetchall()
    if conflicts:
        pairs = ', '.join(f'{a} / {b}' for a, b in conflicts)
        raise RuntimeError(
            f'Cannot add {CONSTRAINT_NAME}: these bookings overlap on the same listing. '
            f'Cancel one booking in each pair, then rerun the migration: {pairs}'
        )

    op.execute('CREATE EXTENSION IF NOT EXISTS btree_gist')
    # End dates are checkout days, so '[)' lets one stay end the day the next begins.
    op.execute(
        f"""
        ALTER TABLE bookings ADD CONSTRAINT {CONSTRAINT_NAME}
        EXCLUDE USING gist (
            listing_id WITH =,
            daterange(start_date, end_date, '[)') WITH &&
        ) WHERE (status <> 'cancelled')
        """
    )


def downgrade() -> None:
    if op.get_bind().dialect.name != 'postgresql':
        return
    op.execute(f'ALTER TABLE bookings DROP CONSTRAINT IF EXISTS {CONSTRAINT_NAME}')
