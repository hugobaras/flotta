"""flotte conducteurs idempotence

Revision ID: 358be3581093
Revises: 64b1f9b861c8
Create Date: 2026-10-23 10:25:49.756297

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '358be3581093'
down_revision: Union[str, None] = '64b1f9b861c8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table('drivers',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('company_id', sa.Integer(), nullable=False),
    sa.Column('nom', sa.String(length=100), nullable=False),
    sa.Column('pin_hash', sa.String(length=64), nullable=False),
    sa.Column('vehicule_habituel_id', sa.Integer(), nullable=True),
    sa.Column('actif', sa.Boolean(), server_default=sa.true(), nullable=False),
    sa.ForeignKeyConstraint(['company_id'], ['companies.id'], ),
    sa.ForeignKeyConstraint(['vehicule_habituel_id'], ['vehicles.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('company_id', 'pin_hash', name='uq_driver_pin')
    )
    op.create_index(op.f('ix_drivers_company_id'), 'drivers', ['company_id'], unique=False)

    # batch_alter_table : SQLite ne sait pas ajouter une contrainte, Postgres reçoit de vrais ALTER.
    with op.batch_alter_table('checks') as batch:
        batch.add_column(sa.Column('conducteur_id', sa.Integer(), nullable=True))
        batch.add_column(sa.Column('client_id', sa.String(length=64), nullable=True))
        batch.add_column(sa.Column('recu_le', sa.DateTime(timezone=True), nullable=True))
        batch.create_foreign_key('fk_checks_conducteur', 'drivers', ['conducteur_id'], ['id'])
        batch.create_unique_constraint('uq_check_client', ['company_id', 'client_id'])
    op.execute("UPDATE checks SET recu_le = created_at")  # les anciens contrôles ont été reçus quand ils ont été faits
    with op.batch_alter_table('checks') as batch:
        batch.alter_column('recu_le', existing_type=sa.DateTime(timezone=True), nullable=False)

    with op.batch_alter_table('vehicles') as batch:
        batch.add_column(sa.Column('actif', sa.Boolean(), server_default=sa.true(), nullable=False))
        batch.add_column(sa.Column('hauteur_m', sa.Float(), nullable=True))
        batch.add_column(sa.Column('largeur_m', sa.Float(), nullable=True))
        batch.add_column(sa.Column('longueur_m', sa.Float(), nullable=True))
        batch.add_column(sa.Column('ptac_kg', sa.Integer(), nullable=True))
        batch.add_column(sa.Column('charge_utile_kg', sa.Integer(), nullable=True))
        batch.add_column(sa.Column('essieux', sa.Integer(), nullable=True))
        batch.add_column(sa.Column('palettes', sa.Integer(), nullable=True))
        batch.add_column(sa.Column('capacite_kg', sa.Integer(), nullable=True))
        batch.add_column(sa.Column('capacite_m3', sa.Float(), nullable=True))
        batch.add_column(sa.Column('adr', sa.Boolean(), server_default=sa.false(), nullable=False))
        batch.add_column(sa.Column('frigo', sa.Boolean(), server_default=sa.false(), nullable=False))
        batch.create_unique_constraint('uq_vehicle_plaque', ['company_id', 'plaque'])


def downgrade() -> None:
    with op.batch_alter_table('vehicles') as batch:
        batch.drop_constraint('uq_vehicle_plaque', type_='unique')
        for c in ('frigo', 'adr', 'capacite_m3', 'capacite_kg', 'palettes', 'essieux', 'charge_utile_kg', 'ptac_kg',
                  'longueur_m', 'largeur_m', 'hauteur_m', 'actif'):
            batch.drop_column(c)
    with op.batch_alter_table('checks') as batch:
        batch.drop_constraint('uq_check_client', type_='unique')
        batch.drop_constraint('fk_checks_conducteur', type_='foreignkey')
        for c in ('recu_le', 'client_id', 'conducteur_id'):
            batch.drop_column(c)
    op.drop_index(op.f('ix_drivers_company_id'), table_name='drivers')
    op.drop_table('drivers')
