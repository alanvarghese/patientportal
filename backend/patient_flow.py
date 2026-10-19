"""Local demo patient journey. OTP delivery is deliberately simulated, never SMS."""
from datetime import date, datetime, time, timedelta, timezone
from hashlib import sha256
from hmac import compare_digest
import re
import os
import secrets
from typing import Annotated, Literal
from uuid import uuid4
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from backend.database import get_session
from backend.fixtures import DOCTOR_ID, TENANT_ID
from backend.models import Practitioner, StaffUser, AppointmentRecord, ConsentRecord, OtpChallenge, Patient, PatientAccount, PatientSession, SlotHold

router = APIRouter(prefix="/api/patient", tags=["Patient demo"])
Db = Annotated[Session, Depends(get_session)]
COOKIE = "practice_patient"
FEE = 50000
NOTICE_VERSION = "demo-privacy-v1"
NOTICE = "I agree to save my fictional profile and booking details for this local practice demonstration. This is not consent to treatment."
TERMS_VERSION = "demo-booking-v1"
TERMS = "This is a demo video appointment. The sample fee is INR 500; no payment is collected. Contact the practice for changes. Consultation consent will be requested separately before a visit."


def now():
    return datetime.now(timezone.utc)


def today():
    return now().astimezone(ZoneInfo("Asia/Kolkata")).date()


def digest(value: str):
    return sha256(value.encode()).hexdigest()


def web_request(request: Request):
    if request.headers.get("x-practice-client") != "portal":
        raise HTTPException(403, "Please use the patient portal")


def account_for(request: Request, session: Session):
    token = request.cookies.get(COOKIE)
    login = session.get(PatientSession, digest(token)) if token else None
    if not login or login.expires_at <= now():
        raise HTTPException(401, "Your session has expired. Please verify your mobile number again.")
    account = session.get(PatientAccount, login.account_id)
    if not account or account.tenant_id != TENANT_ID:
        raise HTTPException(401, "Please verify your mobile number again")
    return account


def profile_of(account: PatientAccount, session: Session):
    patient = session.get(Patient, (TENANT_ID, account.patient_id)) if account.patient_id else None
    return None if not patient else {"id": patient.id, "patient_number": patient.patient_number, "name": patient.name, "date_of_birth": patient.date_of_birth, "phone": patient.phone, "email": patient.email, "language": patient.language}


class PhoneInput(BaseModel):
    phone: str

    @field_validator("phone")
    @classmethod
    def normalize_phone(cls, value):
        value = re.sub(r"[\s()-]", "", value)
        if value.startswith("+91"):
            value = value[3:]
        if not re.fullmatch(r"[6-9][0-9]{9}", value):
            raise ValueError("Enter a valid 10-digit Indian mobile number")
        return "+91" + value


class VerifyInput(BaseModel):
    challenge_id: str = Field(max_length=64)
    code: str = Field(pattern=r"^[0-9]{6}$")


class ProfileInput(BaseModel):
    name: str = Field(min_length=2, max_length=100)
    date_of_birth: date
    email: str = Field(default="", max_length=254)
    language: Literal["English", "Malayalam"] = "English"
    accept_privacy: bool

    @field_validator("name")
    @classmethod
    def name_check(cls, value):
        value = " ".join(value.split())
        if len(value) < 2 or not any(c.isalpha() for c in value):
            raise ValueError("Enter the patient's full name")
        return value

    @field_validator("email")
    @classmethod
    def email_check(cls, value):
        value = value.strip()
        if value and not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", value):
            raise ValueError("Enter a valid email address or leave it blank")
        return value

    @field_validator("date_of_birth")
    @classmethod
    def birth_check(cls, value):
        current = today()
        age = current.year - value.year - ((current.month, current.day) < (value.month, value.day))
        if age < 18 or age > 120 or value > current:
            raise ValueError("This demo supports adults aged 18–120. Guardian registration is a later section.")
        return value


class HoldInput(BaseModel):
    practitioner_id: str = Field(default=DOCTOR_ID, max_length=64)
    day: date
    start_time: str = Field(pattern=r"^\d{2}:\d{2}$")
    visit_type: Literal["First visit", "Follow-up"]
    reason: str = Field(min_length=3, max_length=500)

    @field_validator("reason")
    @classmethod
    def reason_check(cls, value):
        value = value.strip()
        if len(value) < 3:
            raise ValueError("Add a short reason for the visit")
        return value


class ConfirmInput(BaseModel):
    accept_terms: bool


def slot_times(day: date):
    if day < today() or day > today() + timedelta(days=30) or day.weekday() == 6:
        return []
    return [time(hour, minute) for hour in range(9, 13) for minute in (0, 30)
            if datetime.combine(day, time(hour, minute), ZoneInfo("Asia/Kolkata")) > now()]


def lock_slot(session: Session, day: date, start: time, practitioner_id: str = DOCTOR_ID):
    key = f"{TENANT_ID}:{practitioner_id}:{day}:{start}"
    session.execute(text("SELECT pg_advisory_xact_lock(hashtextextended(:key, 0))"), {"key": key})


def booking_view(record: AppointmentRecord, session: Session):
    patient = session.get(Patient, (TENANT_ID, record.patient_id))
    doctor = session.get(Practitioner, (TENANT_ID, record.practitioner_id))
    return {"practitioner_id": record.practitioner_id, "doctor": doctor.name, "id": record.id, "reference": record.booking_reference, "patient": patient.name,
        "patient_number": patient.patient_number, "day": record.day, "time": record.start_time.strftime("%H:%M"),
        "timezone": "Asia/Kolkata", "duration": record.duration, "visit_type": record.visit_type,
        "reason": record.reason, "status": record.status, "fee_paise": record.fee_paise,
        "payment_status": record.payment_status}


@router.get("/config")
def config(session: Db):
    doctors = session.scalars(select(Practitioner).join(StaffUser, (StaffUser.tenant_id == Practitioner.tenant_id) & (StaffUser.practitioner_id == Practitioner.id)).where(Practitioner.tenant_id == TENANT_ID, StaffUser.active.is_(True)).order_by(Practitioner.name)).all()
    return {"doctors": [{"id": d.id, "name": d.name} for d in doctors], "today": today(), "max_day": today() + timedelta(days=30), "fee_paise": FEE,
        "privacy_notice": NOTICE, "privacy_version": NOTICE_VERSION, "booking_terms": TERMS,
        "terms_version": TERMS_VERSION, "otp_delivery": "demo_on_screen", "timezone": "Asia/Kolkata"}


@router.post("/otp/challenges")
def challenge(payload: PhoneInput, request: Request, session: Db):
    web_request(request)
    code, key = f"{secrets.randbelow(1000000):06d}", uuid4().hex
    with session.begin():
        session.execute(text("SELECT pg_advisory_xact_lock(hashtextextended(:key, 0))"), {"key": "otp:" + payload.phone})
        recent = session.scalars(select(OtpChallenge).where(OtpChallenge.tenant_id == TENANT_ID, OtpChallenge.phone == payload.phone, OtpChallenge.created_at > now() - timedelta(hours=1)).order_by(OtpChallenge.created_at.desc())).all()
        if recent and (recent[0].created_at > now() - timedelta(seconds=30) or len(recent) >= 5):
            raise HTTPException(429, "Please wait before requesting another code (30-second cooldown; 5 per hour).")
        for old in recent:
            old.consumed = True
        session.add(OtpChallenge(id=key, tenant_id=TENANT_ID, phone=payload.phone, code_hash=digest(key + code), expires_at=now() + timedelta(minutes=5), attempts=0, consumed=False))
    return {"challenge_id": key, "expires_in": 300, "demo_code": code, "delivery": "Demo only — no SMS was sent"}


@router.post("/otp/verify")
def verify(payload: VerifyInput, request: Request, response: Response, session: Db):
    web_request(request)
    error = None
    token = secrets.token_urlsafe(32)
    with session.begin():
        item = session.scalar(select(OtpChallenge).where(OtpChallenge.id == payload.challenge_id, OtpChallenge.tenant_id == TENANT_ID).with_for_update())
        if not item or item.consumed or item.expires_at <= now() or item.attempts >= 5:
            error = "This code has expired or was already used. Request a new code."
        elif not compare_digest(item.code_hash, digest(item.id + payload.code)):
            item.attempts += 1
            error = "That code is incorrect. Try again (maximum 5 attempts)."
        else:
            item.consumed = True
            session.execute(text("SELECT pg_advisory_xact_lock(hashtextextended(:key, 0))"), {"key": "account:" + item.phone})
            account = session.scalar(select(PatientAccount).where(PatientAccount.tenant_id == TENANT_ID, PatientAccount.phone == item.phone))
            if not account:
                account = PatientAccount(id=uuid4().hex, tenant_id=TENANT_ID, phone=item.phone)
                session.add(account)
                session.flush()
            # Rotate the current browser session after successful verification.
            previous_token = request.cookies.get(COOKIE)
            if previous_token:
                previous = session.get(PatientSession, digest(previous_token))
                if previous:
                    session.delete(previous)
            session.add(PatientSession(token_hash=digest(token), account_id=account.id, expires_at=now() + timedelta(hours=2)))
            profile = profile_of(account, session)
    if error:
        raise HTTPException(400, error)
    response.set_cookie(COOKIE, token, httponly=True, samesite="lax", max_age=7200, path="/api/patient", secure=os.environ.get('DEMO_SECURE_COOKIES') == '1')
    return {"profile": profile, "phone": account.phone}


@router.get("/me")
def me(request: Request, session: Db):
    account = account_for(request, session)
    bookings = session.scalars(select(AppointmentRecord).where(AppointmentRecord.tenant_id == TENANT_ID, AppointmentRecord.patient_id == account.patient_id, AppointmentRecord.booking_reference.is_not(None)).order_by(AppointmentRecord.day.desc(), AppointmentRecord.start_time.desc()).limit(20)).all() if account.patient_id else []
    return {"profile": profile_of(account, session), "phone": account.phone, "bookings": [booking_view(a, session) for a in bookings]}


@router.post("/logout")
def logout(request: Request, response: Response, session: Db):
    web_request(request)
    with session.begin():
        token = request.cookies.get(COOKIE)
        item = session.get(PatientSession, digest(token)) if token else None
        if item:
            session.delete(item)
    response.delete_cookie(COOKIE, path="/api/patient")
    return {"status": "signed_out"}


@router.post("/profile")
def register(payload: ProfileInput, request: Request, session: Db):
    web_request(request)
    if not payload.accept_privacy:
        raise HTTPException(422, "Please accept the demo privacy notice to continue")
    with session.begin():
        account = account_for(request, session)
        session.refresh(account, with_for_update=True)
        if account.patient_id:
            existing = profile_of(account, session)
            if existing["name"] == payload.name and existing["date_of_birth"] == payload.date_of_birth and (existing["email"] or "") == payload.email and existing["language"] == payload.language:
                return existing
            raise HTTPException(409, "This mobile already has a patient profile. Profile editing and dependent accounts are later sections.")
        patient_id = uuid4().hex
        current = today()
        age = current.year - payload.date_of_birth.year - ((current.month, current.day) < (payload.date_of_birth.month, payload.date_of_birth.day))
        patient = Patient(tenant_id=TENANT_ID, id=patient_id, patient_number=f"PT-{session.scalar(text("SELECT nextval('patient_number_seq')")):06d}", name=payload.name,
            demo_age=age, date_of_birth=payload.date_of_birth, phone=account.phone, email=payload.email or None,
            language=payload.language, initials="".join(p[0] for p in payload.name.split()[:2]).upper(), color="blue")
        session.add(patient)
        session.flush()
        account.patient_id = patient_id
        session.add(ConsentRecord(id=uuid4().hex, tenant_id=TENANT_ID, patient_id=patient_id, account_id=account.id, purpose="demo_registration", version=NOTICE_VERSION, wording=NOTICE))
        session.flush()
        result = profile_of(account, session)
    return result


@router.get("/availability")
def availability(day: date, request: Request, session: Db, practitioner_id: str = DOCTOR_ID):
    if not session.scalar(select(StaffUser.id).where(StaffUser.tenant_id == TENANT_ID, StaffUser.practitioner_id == practitioner_id, StaffUser.active.is_(True))): raise HTTPException(422, "Choose an available doctor")
    account = account_for(request, session)
    if not account.patient_id:
        raise HTTPException(409, "Complete your profile before booking")
    booked = set(session.scalars(select(AppointmentRecord.start_time).where(AppointmentRecord.tenant_id == TENANT_ID, AppointmentRecord.practitioner_id == practitioner_id, AppointmentRecord.day == day)))
    held = set(session.scalars(select(SlotHold.start_time).where(SlotHold.tenant_id == TENANT_ID, SlotHold.practitioner_id == practitioner_id, SlotHold.day == day, SlotHold.expires_at > now(), SlotHold.appointment_id.is_(None), SlotHold.account_id != account.id)))
    return {"day": day, "slots": [{"time": t.strftime("%H:%M"), "available": t not in booked and t not in held} for t in slot_times(day)], "duration": 20, "fee_paise": FEE}


@router.post("/holds")
def hold(payload: HoldInput, request: Request, session: Db):
    web_request(request)
    try:
        start = time.fromisoformat(payload.start_time)
    except ValueError:
        raise HTTPException(422, "Choose a valid appointment time")
    if start not in slot_times(payload.day):
        raise HTTPException(422, "Choose an available future slot within the next 30 days")
    with session.begin():
        if not session.scalar(select(StaffUser.id).where(StaffUser.tenant_id == TENANT_ID, StaffUser.practitioner_id == payload.practitioner_id, StaffUser.active.is_(True))): raise HTTPException(422, "Choose an available doctor")
        account = account_for(request, session)
        if not account.patient_id:
            raise HTTPException(409, "Complete your profile before booking")
        lock_slot(session, payload.day, start, payload.practitioner_id)
        occupied = session.scalar(select(AppointmentRecord.id).where(AppointmentRecord.tenant_id == TENANT_ID, AppointmentRecord.practitioner_id == payload.practitioner_id, AppointmentRecord.day == payload.day, AppointmentRecord.start_time == start))
        existing = session.scalar(select(SlotHold).where(SlotHold.tenant_id == TENANT_ID, SlotHold.practitioner_id == payload.practitioner_id, SlotHold.day == payload.day, SlotHold.start_time == start))
        if occupied or (existing and existing.expires_at > now() and existing.account_id != account.id):
            raise HTTPException(409, "That time was just taken. Please choose another slot.")
        if existing and existing.account_id == account.id and existing.expires_at > now() and existing.reason == payload.reason and existing.visit_type == payload.visit_type:
            item = existing
        else:
            item = existing or SlotHold(id=uuid4().hex, tenant_id=TENANT_ID, practitioner_id=payload.practitioner_id, day=payload.day, start_time=start)
            item.token, item.account_id = uuid4().hex, account.id
            item.expires_at, item.visit_type, item.reason = now() + timedelta(minutes=10), payload.visit_type, payload.reason
            item.fee_paise, item.appointment_id = FEE, None
            session.add(item)
        session.flush()
        result = {"hold_id": item.token, "expires_at": item.expires_at, "day": item.day, "time": item.start_time.strftime("%H:%M"), "duration": 20, "fee_paise": item.fee_paise, "visit_type": item.visit_type, "reason": item.reason}
    return result


@router.delete("/holds/{token}")
def release_hold(token: str, request: Request, session: Db):
    web_request(request)
    with session.begin():
        account = account_for(request, session)
        item = session.scalar(select(SlotHold).where(SlotHold.token == token, SlotHold.account_id == account.id, SlotHold.tenant_id == TENANT_ID))
        if item:
            lock_slot(session, item.day, item.start_time, item.practitioner_id)
            session.refresh(item)
            if item.token == token and not item.appointment_id:
                item.expires_at = now()
    return {"status": "released"}


@router.post("/holds/{token}/confirm")
def confirm(token: str, payload: ConfirmInput, request: Request, session: Db):
    web_request(request)
    if not payload.accept_terms:
        raise HTTPException(422, "Please accept the demo booking terms")
    with session.begin():
        account = account_for(request, session)
        item = session.scalar(select(SlotHold).where(SlotHold.token == token, SlotHold.account_id == account.id, SlotHold.tenant_id == TENANT_ID))
        if not item:
            raise HTTPException(404, "Booking hold not found")
        lock_slot(session, item.day, item.start_time, item.practitioner_id)
        session.refresh(item)
        if not session.scalar(select(StaffUser.id).where(StaffUser.tenant_id == TENANT_ID, StaffUser.practitioner_id == item.practitioner_id, StaffUser.active.is_(True))): raise HTTPException(409, "This doctor is no longer available")
        if item.token != token or item.account_id != account.id:
            raise HTTPException(409, "This hold has expired. Please choose another time.")
        if item.appointment_id:
            return booking_view(session.get(AppointmentRecord, (TENANT_ID, item.appointment_id)), session)
        if item.expires_at <= now() or item.start_time not in slot_times(item.day):
            raise HTTPException(409, "This hold has expired. Please choose another time.")
        if session.scalar(select(AppointmentRecord.id).where(AppointmentRecord.tenant_id == TENANT_ID, AppointmentRecord.practitioner_id == item.practitioner_id, AppointmentRecord.day == item.day, AppointmentRecord.start_time == item.start_time)):
            raise HTTPException(409, "This appointment is no longer available. Choose another time.")
        record = AppointmentRecord(id=uuid4().hex, tenant_id=TENANT_ID, patient_id=account.patient_id, practitioner_id=item.practitioner_id,
            day=item.day, start_time=item.start_time, duration=20, visit_type=item.visit_type, reason=item.reason,
            status="confirmed", booking_reference=f"BK-{item.day:%Y%m%d}-{session.scalar(text("SELECT nextval('booking_number_seq')")):06d}", fee_paise=item.fee_paise, payment_status="not_collected_demo", terms_version=TERMS_VERSION)
        session.add(record)
        session.flush()
        item.appointment_id = record.id
        session.add(ConsentRecord(id=uuid4().hex, tenant_id=TENANT_ID, patient_id=account.patient_id, account_id=account.id, purpose="demo_booking_terms", version=TERMS_VERSION, wording=TERMS))
        result = booking_view(record, session)
    return result
