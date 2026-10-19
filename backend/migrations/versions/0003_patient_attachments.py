"""Patient attachment metadata; bytes live outside the public web root."""
from alembic import op
import sqlalchemy as sa

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table("patient_attachments",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("tenant_id", sa.String(64), sa.ForeignKey("practices.id"), nullable=False),
        sa.Column("patient_id", sa.String(64), nullable=False),
        sa.Column("filename", sa.String(200), nullable=False), sa.Column("title", sa.String(120), nullable=False),
        sa.Column("mime_type", sa.String(32), nullable=False), sa.Column("size_bytes", sa.Integer(), nullable=False),
        sa.Column("checksum", sa.String(64), nullable=False), sa.Column("storage_key", sa.String(64), nullable=False, unique=True),
        sa.Column("uploaded_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("uploaded_by", sa.String(64), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id", "patient_id"], ["patients.tenant_id", "patients.id"]),
        sa.UniqueConstraint("tenant_id", "patient_id", "checksum", name="uq_patient_attachment_checksum"),
        sa.CheckConstraint("size_bytes > 0 AND size_bytes <= 10485760", name="ck_attachment_size"))
    op.create_index("ix_attachments_patient", "patient_attachments", ["tenant_id", "patient_id", "uploaded_at"])


def downgrade():
    op.drop_table("patient_attachments")
