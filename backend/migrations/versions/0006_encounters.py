"""Appointment consent, versioned notes, finalization and attributed addenda."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB
revision='0006'
down_revision='0005'
branch_labels=None
depends_on=None

def upgrade():
    op.create_table('consultation_consents',sa.Column('id',sa.String(64),primary_key=True),
        sa.Column('tenant_id',sa.String(64),sa.ForeignKey('practices.id'),nullable=False),
        sa.Column('appointment_id',sa.String(64),nullable=False),sa.Column('patient_id',sa.String(64),nullable=False),
        sa.Column('method',sa.String(32),nullable=False),sa.Column('scope_key',sa.String(64),nullable=False),
        sa.Column('account_id',sa.String(64),sa.ForeignKey('patient_accounts.id')),sa.Column('room_id',sa.String(64),sa.ForeignKey('video_rooms.id')),
        sa.Column('notice_version',sa.String(64),nullable=False),sa.Column('wording',sa.Text(),nullable=False),
        sa.Column('accepted_at',sa.DateTime(timezone=True),server_default=sa.func.now(),nullable=False),
        sa.ForeignKeyConstraint(['tenant_id','appointment_id'],['appointments.tenant_id','appointments.id']),
        sa.ForeignKeyConstraint(['tenant_id','patient_id'],['patients.tenant_id','patients.id']),
        sa.UniqueConstraint('tenant_id','appointment_id','method','scope_key','notice_version',name='uq_consultation_consent'),
        sa.CheckConstraint("method IN ('patient_session','demo_guest')",name='ck_consultation_consent_method'))
    op.create_table('encounters',sa.Column('tenant_id',sa.String(64),sa.ForeignKey('practices.id'),primary_key=True),
        sa.Column('appointment_id',sa.String(64),primary_key=True),sa.Column('version',sa.Integer(),nullable=False),sa.Column('data',JSONB(),nullable=False),
        sa.Column('finalized_at',sa.DateTime(timezone=True)),sa.Column('finalized_by',sa.String(64),sa.ForeignKey('staff_users.id')),
        sa.Column('updated_at',sa.DateTime(timezone=True),server_default=sa.func.now(),nullable=False),
        sa.ForeignKeyConstraint(['tenant_id','appointment_id'],['appointments.tenant_id','appointments.id']),sa.CheckConstraint('version > 0',name='ck_encounter_version'))
    op.create_table('encounter_revisions',sa.Column('id',sa.String(64),primary_key=True),sa.Column('tenant_id',sa.String(64),nullable=False),
        sa.Column('appointment_id',sa.String(64),nullable=False),sa.Column('version',sa.Integer(),nullable=False),sa.Column('kind',sa.String(32),nullable=False),
        sa.Column('author_id',sa.String(64),sa.ForeignKey('staff_users.id'),nullable=False),sa.Column('data',JSONB(),nullable=False),
        sa.Column('created_at',sa.DateTime(timezone=True),server_default=sa.func.now(),nullable=False),
        sa.ForeignKeyConstraint(['tenant_id','appointment_id'],['encounters.tenant_id','encounters.appointment_id']),
        sa.UniqueConstraint('tenant_id','appointment_id','version',name='uq_encounter_revision'),sa.CheckConstraint("kind IN ('draft','finalized','addendum')",name='ck_encounter_revision_kind'))

def downgrade():
    op.drop_table('encounter_revisions');op.drop_table('encounters');op.drop_table('consultation_consents')
