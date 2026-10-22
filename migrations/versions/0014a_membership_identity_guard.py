"""Serialize the issuer/subject membership predicate through metadata issuance.

No rows, columns, identities or privileges are rewritten/backfilled. PostgreSQL
adds an identity-specific mutation trigger; SQLite uses its writer reservation.
"""
from alembic import context, op
import sqlalchemy as sa

from src.membership_identity_guard import (
    install_membership_identity_guard, membership_identity_guard_statements,
)


revision = "0014a_membership_identity_guard"
down_revision = "0014_organization_engagement_authorization"
branch_labels = None
depends_on = None


def upgrade() -> None:
    if context.is_offline_mode():
        for statement in membership_identity_guard_statements(op.get_bind().dialect):
            op.execute(statement)
    else:
        # Keep the migration independent of a future ORM model definition.
        table = sa.Table("organization_memberships", sa.MetaData())
        install_membership_identity_guard(table, op.get_bind())


def downgrade() -> None:
    raise RuntimeError("Membership guard downgrade requires an independently reviewed authorization rollback plan; no guard was removed.")
