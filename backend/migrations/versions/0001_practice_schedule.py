"""Initial demo practice schedule. Schema frozen here independently of ORM changes."""
from alembic import op
import sqlalchemy as sa

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    op.create_table("practices", sa.Column("id", sa.String(64), primary_key=True), sa.Column("name", sa.String(160), nullable=False), sa.Column("timezone", sa.String(64), nullable=False))
    op.create_table("practitioners", sa.Column("tenant_id", sa.String(64), sa.ForeignKey("practices.id"), primary_key=True), sa.Column("id", sa.String(64), primary_key=True), sa.Column("name", sa.String(160), nullable=False))
    op.create_table("patients", sa.Column("tenant_id", sa.String(64), sa.ForeignKey("practices.id"), primary_key=True), sa.Column("id", sa.String(64), primary_key=True), sa.Column("patient_number", sa.String(32), nullable=False), sa.Column("name", sa.String(160), nullable=False), sa.Column("demo_age", sa.Integer, nullable=False), sa.Column("initials", sa.String(8), nullable=False), sa.Column("color", sa.String(16), nullable=False), sa.UniqueConstraint("tenant_id", "patient_number", name="uq_patient_number"), sa.CheckConstraint("demo_age >= 0 AND demo_age <= 130", name="ck_patient_demo_age"))
    op.create_table("appointments",
        sa.Column("tenant_id", sa.String(64), sa.ForeignKey("practices.id"), primary_key=True), sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("patient_id", sa.String(64), nullable=False), sa.Column("practitioner_id", sa.String(64), nullable=False),
        sa.Column("day", sa.Date, nullable=False), sa.Column("start_time", sa.Time, nullable=False), sa.Column("duration", sa.Integer, nullable=False),
        sa.Column("visit_type", sa.String(32), nullable=False), sa.Column("reason", sa.Text, nullable=False), sa.Column("status", sa.String(20), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id", "patient_id"], ["patients.tenant_id", "patients.id"]),
        sa.ForeignKeyConstraint(["tenant_id", "practitioner_id"], ["practitioners.tenant_id", "practitioners.id"]),
        sa.UniqueConstraint("tenant_id", "practitioner_id", "day", "start_time", name="uq_doctor_slot"),
        sa.CheckConstraint("status IN ('confirmed', 'waiting', 'completed')", name="ck_appointment_status"),
        sa.CheckConstraint("duration > 0 AND duration <= 240", name="ck_appointment_duration"))
    op.create_index("ix_appointments_tenant_day", "appointments", ["tenant_id", "day"])


def downgrade():
    op.drop_table("appointments")
    op.drop_table("patients")
    op.drop_table("practitioners")
    op.drop_table("practices")
