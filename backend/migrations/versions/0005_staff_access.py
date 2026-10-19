"""Individual staff accounts, sessions and administrative change audit."""
from alembic import op
import sqlalchemy as sa

revision = '0005'
down_revision = '0004'
branch_labels = None
depends_on = None

def upgrade():
    op.create_table('staff_users',
        sa.Column('id',sa.String(64),primary_key=True),
        sa.Column('tenant_id',sa.String(64),sa.ForeignKey('practices.id'),nullable=False),
        sa.Column('username',sa.String(64),nullable=False),sa.Column('name',sa.String(160),nullable=False),
        sa.Column('role',sa.String(32),nullable=False),sa.Column('practitioner_id',sa.String(64)),
        sa.Column('password_hash',sa.Text(),nullable=False),sa.Column('active',sa.Boolean(),nullable=False),
        sa.Column('failed_logins',sa.Integer(),nullable=False),sa.Column('locked_until',sa.DateTime(timezone=True)),
        sa.UniqueConstraint('tenant_id','username',name='uq_staff_username'),
        sa.UniqueConstraint('tenant_id','practitioner_id',name='uq_staff_practitioner'),
        sa.ForeignKeyConstraint(['tenant_id','practitioner_id'],['practitioners.tenant_id','practitioners.id']),
        sa.CheckConstraint("role IN ('doctor','medical_admin','nurse')",name='ck_staff_role'),
        sa.CheckConstraint("(role = 'doctor') = (practitioner_id IS NOT NULL)",name='ck_staff_doctor'))
    op.create_table('staff_sessions',sa.Column('token_hash',sa.String(64),primary_key=True),
        sa.Column('user_id',sa.String(64),sa.ForeignKey('staff_users.id'),nullable=False),
        sa.Column('expires_at',sa.DateTime(timezone=True),nullable=False))
    op.create_table('staff_audit',sa.Column('id',sa.String(64),primary_key=True),
        sa.Column('tenant_id',sa.String(64),sa.ForeignKey('practices.id'),nullable=False),
        sa.Column('user_id',sa.String(64),sa.ForeignKey('staff_users.id'),nullable=False),
        sa.Column('action',sa.String(64),nullable=False),sa.Column('target_id',sa.String(64),nullable=False),
        sa.Column('created_at',sa.DateTime(timezone=True),server_default=sa.func.now(),nullable=False))

def downgrade():
    op.drop_table('staff_audit')
    op.drop_table('staff_sessions')
    op.drop_table('staff_users')
