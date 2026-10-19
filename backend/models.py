"""The first persistent slice: practice, practitioner, patient and appointment."""
from datetime import date, datetime, time

from sqlalchemy import Boolean, CheckConstraint, Date, DateTime, ForeignKey, ForeignKeyConstraint, Index, Integer, String, Text, Time, UniqueConstraint, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy.dialects.postgresql import JSONB


class Base(DeclarativeBase):
    pass


class Practice(Base):
    __tablename__ = "practices"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    name: Mapped[str] = mapped_column(String(160))
    timezone: Mapped[str] = mapped_column(String(64), default="Asia/Kolkata")


class Practitioner(Base):
    __tablename__ = "practitioners"
    tenant_id: Mapped[str] = mapped_column(ForeignKey("practices.id"), primary_key=True)
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    name: Mapped[str] = mapped_column(String(160))


class StaffUser(Base):
    __tablename__ = 'staff_users'
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(ForeignKey('practices.id'))
    username: Mapped[str] = mapped_column(String(64))
    name: Mapped[str] = mapped_column(String(160))
    role: Mapped[str] = mapped_column(String(32))
    practitioner_id: Mapped[str | None] = mapped_column(String(64))
    password_hash: Mapped[str] = mapped_column(Text)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    failed_logins: Mapped[int] = mapped_column(Integer, default=0)
    locked_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    __table_args__ = (
        UniqueConstraint('tenant_id', 'username', name='uq_staff_username'),
        UniqueConstraint('tenant_id', 'practitioner_id', name='uq_staff_practitioner'),
        ForeignKeyConstraint(['tenant_id', 'practitioner_id'], ['practitioners.tenant_id', 'practitioners.id']),
        CheckConstraint("role IN ('doctor','medical_admin','nurse')", name='ck_staff_role'),
        CheckConstraint("(role = 'doctor') = (practitioner_id IS NOT NULL)", name='ck_staff_doctor'),
    )


class StaffSession(Base):
    __tablename__ = 'staff_sessions'
    token_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[str] = mapped_column(ForeignKey('staff_users.id'))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class StaffAudit(Base):
    __tablename__ = 'staff_audit'
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(ForeignKey('practices.id'))
    user_id: Mapped[str] = mapped_column(ForeignKey('staff_users.id'))
    action: Mapped[str] = mapped_column(String(64))
    target_id: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Patient(Base):
    __tablename__ = "patients"
    tenant_id: Mapped[str] = mapped_column(ForeignKey("practices.id"), primary_key=True)
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    patient_number: Mapped[str] = mapped_column(String(32))
    name: Mapped[str] = mapped_column(String(160))
    demo_age: Mapped[int] = mapped_column(Integer)  # Synthetic fixture age, not a clinical DOB.
    initials: Mapped[str] = mapped_column(String(8))
    color: Mapped[str] = mapped_column(String(16))
    date_of_birth: Mapped[date | None] = mapped_column(Date)
    phone: Mapped[str | None] = mapped_column(String(16))
    email: Mapped[str | None] = mapped_column(String(254))
    language: Mapped[str | None] = mapped_column(String(16))
    __table_args__ = (
        UniqueConstraint("tenant_id", "patient_number", name="uq_patient_number"),
        CheckConstraint("demo_age >= 0 AND demo_age <= 130", name="ck_patient_demo_age"),
    )


class AppointmentRecord(Base):
    __tablename__ = "appointments"
    tenant_id: Mapped[str] = mapped_column(ForeignKey("practices.id"), primary_key=True)
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    patient_id: Mapped[str] = mapped_column(String(64))
    practitioner_id: Mapped[str] = mapped_column(String(64))
    day: Mapped[date] = mapped_column(Date)
    start_time: Mapped[time] = mapped_column(Time)
    duration: Mapped[int] = mapped_column(Integer)
    visit_type: Mapped[str] = mapped_column(String(32))
    reason: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(20))
    booking_reference: Mapped[str | None] = mapped_column(String(32), unique=True)
    fee_paise: Mapped[int | None] = mapped_column(Integer)
    payment_status: Mapped[str | None] = mapped_column(String(32))
    terms_version: Mapped[str | None] = mapped_column(String(32))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    __table_args__ = (
        ForeignKeyConstraint(["tenant_id", "patient_id"], ["patients.tenant_id", "patients.id"]),
        ForeignKeyConstraint(["tenant_id", "practitioner_id"], ["practitioners.tenant_id", "practitioners.id"]),
        UniqueConstraint("tenant_id", "practitioner_id", "day", "start_time", name="uq_doctor_slot"),
        CheckConstraint("status IN ('confirmed', 'waiting', 'completed')", name="ck_appointment_status"),
        CheckConstraint("duration > 0 AND duration <= 240", name="ck_appointment_duration"),
        Index("ix_appointments_tenant_day", "tenant_id", "day"),
    )


class PatientAccount(Base):
    __tablename__ = "patient_accounts"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(ForeignKey("practices.id"))
    phone: Mapped[str] = mapped_column(String(16))
    patient_id: Mapped[str | None] = mapped_column(String(64))
    __table_args__ = (UniqueConstraint("tenant_id", "phone", name="uq_account_phone"), ForeignKeyConstraint(["tenant_id", "patient_id"], ["patients.tenant_id", "patients.id"]))


class OtpChallenge(Base):
    __tablename__ = "otp_challenges"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(ForeignKey("practices.id"))
    phone: Mapped[str] = mapped_column(String(16), index=True)
    code_hash: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    consumed: Mapped[bool] = mapped_column(Boolean, default=False)


class PatientSession(Base):
    __tablename__ = "patient_sessions"
    token_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    account_id: Mapped[str] = mapped_column(ForeignKey("patient_accounts.id"))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class ConsentRecord(Base):
    __tablename__ = "consent_records"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(ForeignKey("practices.id"))
    patient_id: Mapped[str] = mapped_column(String(64))
    account_id: Mapped[str] = mapped_column(ForeignKey("patient_accounts.id"))
    purpose: Mapped[str] = mapped_column(String(32))
    version: Mapped[str] = mapped_column(String(32))
    wording: Mapped[str] = mapped_column(Text)
    accepted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    __table_args__ = (ForeignKeyConstraint(["tenant_id", "patient_id"], ["patients.tenant_id", "patients.id"]),)


class SlotHold(Base):
    __tablename__ = "slot_holds"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    token: Mapped[str] = mapped_column(String(64), unique=True)
    tenant_id: Mapped[str] = mapped_column(ForeignKey("practices.id"))
    practitioner_id: Mapped[str] = mapped_column(String(64))
    account_id: Mapped[str] = mapped_column(ForeignKey("patient_accounts.id"))
    day: Mapped[date] = mapped_column(Date)
    start_time: Mapped[time] = mapped_column(Time)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    visit_type: Mapped[str] = mapped_column(String(32))
    reason: Mapped[str] = mapped_column(Text)
    fee_paise: Mapped[int] = mapped_column(Integer)
    appointment_id: Mapped[str | None] = mapped_column(String(64))
    __table_args__ = (
        UniqueConstraint("tenant_id", "practitioner_id", "day", "start_time", name="uq_hold_slot"),
        ForeignKeyConstraint(["tenant_id", "practitioner_id"], ["practitioners.tenant_id", "practitioners.id"]),
        ForeignKeyConstraint(["tenant_id", "appointment_id"], ["appointments.tenant_id", "appointments.id"]),
    )


class PatientAttachment(Base):
    __tablename__ = "patient_attachments"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(ForeignKey("practices.id"))
    patient_id: Mapped[str] = mapped_column(String(64))
    filename: Mapped[str] = mapped_column(String(200))
    title: Mapped[str] = mapped_column(String(120))
    mime_type: Mapped[str] = mapped_column(String(32))
    size_bytes: Mapped[int] = mapped_column(Integer)
    checksum: Mapped[str] = mapped_column(String(64))
    storage_key: Mapped[str] = mapped_column(String(64), unique=True)
    uploaded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    uploaded_by: Mapped[str] = mapped_column(String(64))
    __table_args__ = (
        ForeignKeyConstraint(["tenant_id", "patient_id"], ["patients.tenant_id", "patients.id"]),
        UniqueConstraint("tenant_id", "patient_id", "checksum", name="uq_patient_attachment_checksum"),
        CheckConstraint("size_bytes > 0 AND size_bytes <= 10485760", name="ck_attachment_size"),
        Index("ix_attachments_patient", "tenant_id", "patient_id", "uploaded_at"),
    )


class VideoRoom(Base):
    __tablename__ = "video_rooms"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(ForeignKey("practices.id"))
    appointment_id: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    __table_args__ = (ForeignKeyConstraint(["tenant_id", "appointment_id"], ["appointments.tenant_id", "appointments.id"]),)


class ConsultationConsent(Base):
    __tablename__ = 'consultation_consents'
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(ForeignKey('practices.id'))
    appointment_id: Mapped[str] = mapped_column(String(64))
    patient_id: Mapped[str] = mapped_column(String(64))
    method: Mapped[str] = mapped_column(String(32))
    scope_key: Mapped[str] = mapped_column(String(64))
    account_id: Mapped[str | None] = mapped_column(ForeignKey('patient_accounts.id'))
    room_id: Mapped[str | None] = mapped_column(ForeignKey('video_rooms.id'))
    notice_version: Mapped[str] = mapped_column(String(64))
    wording: Mapped[str] = mapped_column(Text)
    accepted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    __table_args__ = (
        ForeignKeyConstraint(['tenant_id','appointment_id'],['appointments.tenant_id','appointments.id']),
        ForeignKeyConstraint(['tenant_id','patient_id'],['patients.tenant_id','patients.id']),
        UniqueConstraint('tenant_id','appointment_id','method','scope_key','notice_version',name='uq_consultation_consent'),
        CheckConstraint("method IN ('patient_session','demo_guest')",name='ck_consultation_consent_method'),
    )


class Encounter(Base):
    __tablename__ = 'encounters'
    tenant_id: Mapped[str] = mapped_column(ForeignKey('practices.id'), primary_key=True)
    appointment_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    version: Mapped[int] = mapped_column(Integer)
    data: Mapped[dict] = mapped_column(JSONB)
    finalized_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finalized_by: Mapped[str | None] = mapped_column(ForeignKey('staff_users.id'))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    __table_args__ = (ForeignKeyConstraint(['tenant_id','appointment_id'],['appointments.tenant_id','appointments.id']),
        CheckConstraint('version > 0',name='ck_encounter_version'))


class EncounterRevision(Base):
    __tablename__ = 'encounter_revisions'
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(64))
    appointment_id: Mapped[str] = mapped_column(String(64))
    version: Mapped[int] = mapped_column(Integer)
    kind: Mapped[str] = mapped_column(String(32))
    author_id: Mapped[str] = mapped_column(ForeignKey('staff_users.id'))
    data: Mapped[dict] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    __table_args__ = (ForeignKeyConstraint(['tenant_id','appointment_id'],['encounters.tenant_id','encounters.appointment_id']),
        UniqueConstraint('tenant_id','appointment_id','version',name='uq_encounter_revision'),
        CheckConstraint("kind IN ('draft','finalized','addendum')",name='ck_encounter_revision_kind'))
