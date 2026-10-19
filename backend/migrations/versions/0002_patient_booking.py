"""Patient registration, demo OTP sessions, consent and slot holds."""
from alembic import op
import sqlalchemy as sa

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("CREATE SEQUENCE patient_number_seq START WITH 7")
    op.execute("CREATE SEQUENCE booking_number_seq START WITH 1")
    for name, column_type in [("date_of_birth", sa.Date()), ("phone", sa.String(16)), ("email", sa.String(254)), ("language", sa.String(16))]:
        op.add_column("patients", sa.Column(name, column_type))
    for name, column_type in [("booking_reference", sa.String(32)), ("fee_paise", sa.Integer()), ("payment_status", sa.String(32)), ("terms_version", sa.String(32))]:
        op.add_column("appointments", sa.Column(name, column_type))
    op.create_unique_constraint("appointments_booking_reference_key", "appointments", ["booking_reference"])
    op.create_table("patient_accounts", sa.Column("id", sa.String(64), primary_key=True), sa.Column("tenant_id", sa.String(64), sa.ForeignKey("practices.id"), nullable=False), sa.Column("phone", sa.String(16), nullable=False), sa.Column("patient_id", sa.String(64)), sa.UniqueConstraint("tenant_id", "phone", name="uq_account_phone"), sa.ForeignKeyConstraint(["tenant_id", "patient_id"], ["patients.tenant_id", "patients.id"]))
    op.create_table("otp_challenges", sa.Column("id", sa.String(64), primary_key=True), sa.Column("tenant_id", sa.String(64), sa.ForeignKey("practices.id"), nullable=False), sa.Column("phone", sa.String(16), nullable=False), sa.Column("code_hash", sa.String(64), nullable=False), sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False), sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False), sa.Column("attempts", sa.Integer(), nullable=False), sa.Column("consumed", sa.Boolean(), nullable=False))
    op.create_index("ix_otp_challenges_phone", "otp_challenges", ["phone"])
    op.create_table("patient_sessions", sa.Column("token_hash", sa.String(64), primary_key=True), sa.Column("account_id", sa.String(64), sa.ForeignKey("patient_accounts.id"), nullable=False), sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False))
    op.create_table("consent_records", sa.Column("id", sa.String(64), primary_key=True), sa.Column("tenant_id", sa.String(64), sa.ForeignKey("practices.id"), nullable=False), sa.Column("patient_id", sa.String(64), nullable=False), sa.Column("account_id", sa.String(64), sa.ForeignKey("patient_accounts.id"), nullable=False), sa.Column("purpose", sa.String(32), nullable=False), sa.Column("version", sa.String(32), nullable=False), sa.Column("wording", sa.Text(), nullable=False), sa.Column("accepted_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False), sa.ForeignKeyConstraint(["tenant_id", "patient_id"], ["patients.tenant_id", "patients.id"]))
    op.create_table("slot_holds", sa.Column("id", sa.String(64), primary_key=True), sa.Column("token", sa.String(64), nullable=False, unique=True), sa.Column("tenant_id", sa.String(64), sa.ForeignKey("practices.id"), nullable=False), sa.Column("practitioner_id", sa.String(64), nullable=False), sa.Column("account_id", sa.String(64), sa.ForeignKey("patient_accounts.id"), nullable=False), sa.Column("day", sa.Date(), nullable=False), sa.Column("start_time", sa.Time(), nullable=False), sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False), sa.Column("visit_type", sa.String(32), nullable=False), sa.Column("reason", sa.Text(), nullable=False), sa.Column("fee_paise", sa.Integer(), nullable=False), sa.Column("appointment_id", sa.String(64)), sa.UniqueConstraint("tenant_id", "practitioner_id", "day", "start_time", name="uq_hold_slot"), sa.ForeignKeyConstraint(["tenant_id", "practitioner_id"], ["practitioners.tenant_id", "practitioners.id"]), sa.ForeignKeyConstraint(["tenant_id", "appointment_id"], ["appointments.tenant_id", "appointments.id"]))


def downgrade():
    op.execute("DROP SEQUENCE booking_number_seq")
    op.execute("DROP SEQUENCE patient_number_seq")
    for table in ["slot_holds", "consent_records", "patient_sessions", "otp_challenges", "patient_accounts"]:
        op.drop_table(table)
    op.drop_constraint("appointments_booking_reference_key", "appointments", type_="unique")
    for column in ["booking_reference", "fee_paise", "payment_status", "terms_version"]:
        op.drop_column("appointments", column)
    for column in ["date_of_birth", "phone", "email", "language"]:
        op.drop_column("patients", column)
