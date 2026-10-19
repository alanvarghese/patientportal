"""Appointment-specific video room metadata. No media or SDP is stored."""
from alembic import op
import sqlalchemy as sa
revision = '0004'
down_revision = '0003'
branch_labels = None
depends_on = None
def upgrade():
    op.create_table('video_rooms',sa.Column('id',sa.String(64),primary_key=True),sa.Column('tenant_id',sa.String(64),sa.ForeignKey('practices.id'),nullable=False),sa.Column('appointment_id',sa.String(64),nullable=False),sa.Column('created_at',sa.DateTime(timezone=True),server_default=sa.func.now(),nullable=False),sa.Column('expires_at',sa.DateTime(timezone=True),nullable=False),sa.Column('ended_at',sa.DateTime(timezone=True)),sa.ForeignKeyConstraint(['tenant_id','appointment_id'],['appointments.tenant_id','appointments.id']))
def downgrade():
    op.drop_table('video_rooms')
