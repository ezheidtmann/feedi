"""Add Entry.queued and User.last_digest_status

Revision ID: 8b1f3d4a2c5e
Revises: f411849d887d
Create Date: 2026-05-10 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '8b1f3d4a2c5e'
down_revision: Union[str, None] = 'f411849d887d'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table('entries', schema=None) as batch_op:
        batch_op.add_column(sa.Column('queued', sa.TIMESTAMP(), nullable=True))
        batch_op.create_index(batch_op.f('ix_entries_queued'), ['queued'], unique=False)

    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.add_column(sa.Column('last_digest_status', sa.String(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.drop_column('last_digest_status')

    with op.batch_alter_table('entries', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_entries_queued'))
        batch_op.drop_column('queued')
