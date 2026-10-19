"""Demo-only attachment storage. Files are never served from a public directory."""
from hashlib import sha256
from io import BytesIO
from pathlib import Path
import os
import re
from typing import Annotated
from urllib.parse import unquote
from uuid import uuid4
import warnings

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import FileResponse, Response
from PIL import Image, ImageOps
import pypdfium2 as pdfium
from pypdf import PdfReader
from pypdf.generic import ArrayObject, DictionaryObject, IndirectObject
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from backend.database import get_session
from backend.fixtures import DOCTOR_ID, TENANT_ID
from backend.staff import Staff, ensure_patient_access, audit
from backend.models import Patient, PatientAttachment
from backend.patient_flow import web_request

router = APIRouter(prefix="/api/records/patients", tags=["Patient attachments demo"])
Db = Annotated[Session, Depends(get_session)]
STORAGE_ROOT = Path(__file__).resolve().parents[1] / ".local" / "attachments"
MAX_BYTES = 10 * 1024 * 1024
Image.MAX_IMAGE_PIXELS = 16_000_000
EXTENSIONS = {".pdf": "application/pdf", ".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg"}


def patient_exists(session: Session, patient_id: str, actor):
    ensure_patient_access(session, actor, patient_id, clinical=True)
    if not session.get(Patient, (TENANT_ID, patient_id)):
        raise HTTPException(404, "Patient record not found")


def metadata(item: PatientAttachment):
    return {"id": item.id, "filename": item.filename, "title": item.title, "mime_type": item.mime_type,
        "size_bytes": item.size_bytes, "uploaded_at": item.uploaded_at, "uploaded_by": "Demo doctor"}


def decode_label(value: str | None, maximum: int, required: bool = True):
    try:
        label = unquote(value or "", errors="strict").strip()
    except (UnicodeError, ValueError):
        raise HTTPException(422, "File name or title is invalid")
    if (required and not label) or len(label) > maximum or any(ord(c) < 32 or ord(c) == 127 for c in label):
        raise HTTPException(422, f"Use a readable file name/title of at most {maximum} characters")
    return label


def validate_pdf(data: bytes):
    if not data.startswith(b"%PDF-") or not data.rstrip().endswith(b"%%EOF"):
        raise ValueError("Invalid PDF")
    reader = PdfReader(BytesIO(data), strict=True)
    if reader.is_encrypted:
        raise ValueError("Encrypted PDF")
    if not 1 <= len(reader.pages) <= 200:
        raise ValueError("PDF page limit")
    # Conservative demo policy: reject active content, embedded files and scripted forms.
    pending, visited = [reader.trailer], set()
    blocked = {"/JS", "/JavaScript", "/OpenAction", "/AA", "/EmbeddedFiles", "/EF", "/RichMedia", "/XFA"}
    while pending:
        obj = pending.pop()
        if isinstance(obj, IndirectObject):
            key = (obj.idnum, obj.generation)
            if key in visited:
                continue
            visited.add(key)
            if len(visited) > 20000:
                raise ValueError("PDF too complex")
            obj = obj.get_object()
        if isinstance(obj, DictionaryObject):
            if blocked.intersection(obj.keys()) or str(obj.get("/S", "")) in {"/JavaScript", "/Launch", "/SubmitForm", "/ImportData", "/GoToR"}:
                raise ValueError("Active PDF content")
            pending.extend(obj.values())
        elif isinstance(obj, ArrayObject):
            pending.extend(obj)


def validated_bytes(data: bytes, filename: str, declared: str):
    mime = EXTENSIONS.get(Path(filename).suffix.lower())
    if not mime or declared not in {mime, "application/octet-stream", ""}:
        raise HTTPException(415, "Choose a PDF, JPEG or PNG file with a matching file extension")
    try:
        if mime == "application/pdf":
            validate_pdf(data)
            return data, mime
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(BytesIO(data)) as image:
                expected = "PNG" if mime == "image/png" else "JPEG"
                if image.format != expected or getattr(image, "n_frames", 1) != 1:
                    raise ValueError("Unexpected image format")
                image.verify()
            with Image.open(BytesIO(data)) as image:
                image.load()
                oriented = ImageOps.exif_transpose(image)
                clean = oriented.convert("RGBA" if mime == "image/png" and "A" in image.getbands() else "RGB")
                output = BytesIO()
                clean.save(output, format=expected)
                result = output.getvalue()
                if len(result) > MAX_BYTES:
                    raise HTTPException(413, "The processed image exceeds 10 MB. Please choose a smaller image.")
                return result, mime
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(422, "This file could not be validated. Use a standard PDF (up to 200 pages, no password or active content), JPEG or PNG image (up to 16 megapixels).")


@router.get("/{patient_id}/attachments")
def list_attachments(patient_id: str, session: Db, actor: Staff, offset: int = Query(0, ge=0), limit: int = Query(10, ge=1, le=50)):
    patient_exists(session, patient_id, actor)
    conditions = [PatientAttachment.tenant_id == TENANT_ID, PatientAttachment.patient_id == patient_id]
    total = session.scalar(select(func.count()).select_from(PatientAttachment).where(*conditions))
    items = session.scalars(select(PatientAttachment).where(*conditions).order_by(PatientAttachment.uploaded_at.desc(), PatientAttachment.id).offset(offset).limit(limit)).all()
    return {"attachments": [metadata(item) for item in items], "total": total, "offset": offset, "limit": limit}


@router.post("/{patient_id}/attachments")
async def upload(patient_id: str, request: Request, session: Db, actor: Staff):
    web_request(request)
    patient_exists(session, patient_id, actor)
    session.rollback()  # Do not hold a database transaction while receiving bytes.
    filename = decode_label(request.headers.get("x-file-name"), 200)
    if "/" in filename or "\\" in filename or filename.startswith("."):
        raise HTTPException(422, "Choose a file name without a directory path")
    title = decode_label(request.headers.get("x-attachment-title"), 120, required=False) or filename[:120]
    declared = request.headers.get("content-type", "").split(";", 1)[0].lower()
    if Path(filename).suffix.lower() not in EXTENSIONS:
        raise HTTPException(415, "Choose a PDF, JPEG or PNG file")
    chunks, size = [], 0
    async for chunk in request.stream():
        size += len(chunk)
        if size > MAX_BYTES:
            raise HTTPException(413, "Files must be 10 MB or smaller")
        chunks.append(chunk)
    if size == 0:
        raise HTTPException(422, "This file is empty. Please choose another file.")
    content, mime = validated_bytes(b"".join(chunks), filename, declared)
    checksum = sha256(content).hexdigest()
    destination = None
    try:
        with session.begin():
            patient_exists(session, patient_id, actor)
            lock_key = f"attachment:{TENANT_ID}:{patient_id}:{checksum}"
            session.execute(text("SELECT pg_advisory_xact_lock(hashtextextended(:key, 0))"), {"key": lock_key})
            existing = session.scalar(select(PatientAttachment).where(PatientAttachment.tenant_id == TENANT_ID, PatientAttachment.patient_id == patient_id, PatientAttachment.checksum == checksum))
            if existing:
                return {"attachment": metadata(existing), "already_attached": True}
            STORAGE_ROOT.mkdir(parents=True, exist_ok=True, mode=0o700)
            key = uuid4().hex
            destination = STORAGE_ROOT / key
            with destination.open("xb") as target:
                os.chmod(destination, 0o600)
                target.write(content)
            item = PatientAttachment(id=uuid4().hex, tenant_id=TENANT_ID, patient_id=patient_id,
                filename=filename, title=title, mime_type=mime, size_bytes=len(content), checksum=checksum,
                storage_key=key, uploaded_by=actor.id)
            audit(session, actor, "attachment.upload", item.id)
            session.add(item)
            session.flush()
            result = metadata(item)
        return {"attachment": result, "already_attached": False}
    except Exception:
        if destination:
            destination.unlink(missing_ok=True)
        raise


def stored_file(patient_id: str, attachment_id: str, session: Session, actor):
    patient_exists(session, patient_id, actor)
    item = session.scalar(select(PatientAttachment).where(PatientAttachment.id == attachment_id, PatientAttachment.tenant_id == TENANT_ID, PatientAttachment.patient_id == patient_id))
    if not item or not re.fullmatch(r"[a-f0-9]{32}", item.storage_key):
        raise HTTPException(404, "Attachment not found")
    path = STORAGE_ROOT / item.storage_key
    if not path.is_file():
        raise HTTPException(404, "The attachment file is unavailable. Please contact the practice.")
    return item, path


@router.get("/{patient_id}/attachments/{attachment_id}/preview")
def pdf_preview(patient_id: str, attachment_id: str, session: Db, actor: Staff):
    item, path = stored_file(patient_id, attachment_id, session, actor)
    if item.mime_type != "application/pdf":
        raise HTTPException(415, "Preview rendering is available for PDF files")
    try:
        document = pdfium.PdfDocument(str(path))
        try:
            page = document[0]
            try:
                width, height = page.get_size()
                scale = min(1200 / max(width, 1), 1600 / max(height, 1), 2)
                bitmap = page.render(scale=scale)
                try:
                    output = BytesIO()
                    bitmap.to_pil().save(output, format="PNG")
                    image = output.getvalue()
                finally:
                    bitmap.close()
            finally:
                page.close()
        finally:
            document.close()
    except Exception:
        raise HTTPException(422, "A preview could not be generated. Please download the document instead.")
    return Response(image, media_type="image/png", headers={"Cache-Control": "no-store", "X-Content-Type-Options": "nosniff"})


@router.get("/{patient_id}/attachments/{attachment_id}/content")
def content(patient_id: str, attachment_id: str, session: Db, actor: Staff, download: bool = False):
    item, path = stored_file(patient_id, attachment_id, session, actor)
    return FileResponse(path, media_type=item.mime_type, filename=item.filename,
        content_disposition_type="attachment" if download else "inline",
        headers={"Cache-Control": "no-store", "X-Content-Type-Options": "nosniff",
            "Content-Security-Policy": "sandbox; default-src 'none'; frame-ancestors 'self'"})
