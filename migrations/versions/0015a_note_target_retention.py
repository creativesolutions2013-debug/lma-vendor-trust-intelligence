"""Retain SQLite note targets without depending on connection FK pragmas.

Only trigger metadata is added; existing notes/history/parents stay unchanged.
PostgreSQL already enforces the target foreign keys and needs no new DDL.
"""
from alembic import context, op
import sqlalchemy as sa


revision = "0015a_note_target_retention"
down_revision = "0015_analyst_note_revisions"
branch_labels = None
depends_on = None


def upgrade() -> None:
    connection = op.get_bind()
    if connection.dialect.name != "sqlite":
        return
    from src.db import install_note_revision_guards, note_revision_guard_statements
    if context.is_offline_mode():
        for statement in note_revision_guard_statements(connection.dialect):
            op.execute(statement)
    else:
        install_note_revision_guards(sa.Table("analyst_note_revisions", sa.MetaData()), connection)


def downgrade() -> None:
    raise RuntimeError("Note target guard downgrade requires an independently reviewed data-retention and rollback plan; no guards were removed.")
