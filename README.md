# Kerala Telemedicine Patient Portal

A fictional telemedicine and practice-management demo built with React/Next.js, Python/FastAPI and PostgreSQL 17. Python dependencies run in a project-root `.venv`. SQLite is not supported.

## Implemented

- Patients: mobile demo-OTP registration, adult profiles, doctor selection, conflict-safe slot holds and appointment booking/history.
- Doctors: individual sign-in, assigned schedules and patients, reports, video consultations, consultation notes and visit completion.
- Medical Admins: registration, contact edits, doctor schedules, booking and check-in; clinical reports and notes are restricted.
- Nurses: schedules, check-in, patient records and report uploads; no staff administration, doctor notes or prescribing.
- Private PDF/JPEG/PNG attachments, validation, duplicate detection, previews and downloads.
- Two-party WebRTC with FastAPI signaling, STUN/static TURN or temporary Cloudflare TURN credentials, reconnect and synthetic test video.
- Appointment-specific consent evidence, autosaved/versioned doctor drafts, conflict protection, explicit finalization and attributed addenda.

All demonstration patients, accounts and records are fictional. Original sample appointments are on **19 October 2026**, with appointment times in **Asia/Kolkata (IST)**. New bookings use the current practice date and a 30-day booking window.

## Local setup

Prerequisites: Python 3.12, a Node.js version supported by the installed Next.js release, npm, and Docker Desktop. Run commands from the project root.

```sh
python3.12 -m venv .venv
source .venv/bin/activate
pip install -r backend/requirements.lock
cp .env.example .env
```

Choose a local database password in `.env`; use the same value in `POSTGRES_PASSWORD` and `DATABASE_URL`. URL-encode special characters in the connection URL. Existing installations should preserve their `.env` instead of copying over it.

```sh
docker compose up -d --wait db
python -m alembic upgrade head
python scripts/provision_demo_staff.py
python -m uvicorn backend.main:app --host 127.0.0.1 --port 8000
```

The provisioning script initializes the fictional practice, two doctors, one Medical Admin and one nurse. It is idempotent and does not reset existing passwords. Individually generated login details are saved privately in `.local/staff-logins.txt` and `.local/staff-demo-accounts.json`. Do not commit or share these files publicly.

In another terminal:

```sh
npm ci
npm run dev
```

Open [staff sign-in](http://127.0.0.1:3000/login) or [patient booking](http://127.0.0.1:3000/book). Local API documentation: <http://127.0.0.1:8000/docs>. New local installs do not require the optional shared website password.

Next.js proxies `/api/*` to FastAPI. Set `API_ORIGIN` when building/running Next.js if the backend address changes. Keep both services on loopback for the local demo. PostgreSQL is exposed only at `127.0.0.1:5433` by default.

## Demo review

1. Sign in as Medical Admin (`admin`), register a fictional adult and book with a doctor.
2. Sign out and sign in as that doctor (`dr.asha` or `dr.faisal`); only assigned patients/appointments are visible.
3. Open a video consultation and its demo patient link in a second tab/device. Select test video to avoid accessing cameras and microphones.
4. On the patient page, explicitly accept the demonstration consultation notice before joining.
5. Save doctor notes, record identity-check attestation and remote-care suitability, then review and complete the visit.
6. Completion locks the note, completes the appointment and ends video invitations. Addenda preserve the finalized snapshot.

A completed appointment and a released prescription are separate concepts. Prescriptions and patient follow-up are not implemented yet.

Staff sessions use hashed passwords, random server-side sessions, HttpOnly cookies, eight-hour expiry and username lockout after repeated failures. Staff role/assignment checks apply to backend APIs, document retrieval and doctor video tokens. Medical Admins cannot accept patient consent or read clinician notes. Patient sign-in remains simulated: verification codes appear on screen and no SMS is sent.

## PostgreSQL and persistence

Alembic migrations are in `backend/migrations/versions`. Apply them before starting a new API version. API startup seeds the original practice only when absent. `scripts/provision_demo_staff.py` explicitly provisions staff.

The named Docker volume `kerala-telemedicine_postgres_data` preserves data through container recreation. Avoid deleting it or running `docker compose down -v` unless intentionally discarding the local database. A password change in `.env` does not rotate the password of an already initialized PostgreSQL user.

The admin-only demo reset restores original fixture records; it preserves new registrations/bookings and does not reopen finalized clinical encounters.

Records use immutable IDs. Email is optional contact information, never a primary key. Composite foreign keys and doctor-slot uniqueness protect practice references and fixed-slot booking integrity. Multiple doctors currently belong to one fixed practice; independent-practice SaaS onboarding and database row-level security are not implemented.

## Reports and consultation records

Attachments accept standard PDF/JPEG/PNG files up to 10 MiB. Images are normalized; PDFs with unsupported active content or encryption are rejected. Bytes are stored under private opaque keys in `.local/attachments`, with metadata in PostgreSQL. PDF previews use pypdfium2. Validation is not malware scanning: production quarantine, antivirus, retention and managed object storage remain future work.

Patient-account consultation consent is verified against appointment ownership. Shared guest-link acknowledgements are clearly labeled as unverified demo guests and are scoped to their room. Exact notice text/version, method, scope and timestamp are retained. The consent wording is a fictional demonstration draft requiring clinical/legal review before real use.

Only the assigned doctor can access encounter notes. Draft saves create versioned snapshots with concurrency checks. Conflicts retain local text for explicit reconciliation; unsaved changes receive a navigation warning. Finalization requires consent, identity attestation, suitability, assessment and plan. Finalized notes cannot be overwritten; attributed addenda preserve corrections. The screen shows the latest 30 versions; older snapshots remain stored. Clinical text is not saved in browser localStorage.

## TURN and video

Set `WEBRTC_STUN_URLS` to approved comma-separated STUN URLs. Static TURN is supported through `WEBRTC_TURN_URLS`, `WEBRTC_TURN_USERNAME` and `WEBRTC_TURN_CREDENTIAL`.

Alternatively, configure Cloudflare Realtime TURN using `CLOUDFLARE_TURN_KEY_ID` and `CLOUDFLARE_TURN_API_TOKEN` in `.env` or an owner-readable `.local/turn.env`. The private TURN file takes precedence. Never use `NEXT_PUBLIC_*` variables for secrets. Restart FastAPI after credential changes.

The backend requests temporary two-hour ICE credentials after validating a call invitation; the provider token never reaches the browser. Credentials are cached briefly per room/role. Review provider pricing/billing before activation. The relay-only prejoin option supports backup-connection testing; leave it unchecked for normal direct connections with relay fallback.

Media is encrypted in transit; no recording is implemented. Signaling is bounded, in-memory, and supports one API worker. API restarts require call reconnection. Other devices require HTTPS and a reachable application origin. India/UAE network reliability must be validated on target devices; transport tests are not a substitute for real audio/video testing.

Cloudflare documentation: [temporary credentials](https://developers.cloudflare.com/realtime/turn/generate-credentials/) and [pricing/FAQ](https://developers.cloudflare.com/realtime/turn/faq/).

## Optional password-protected public demo

The existing operator deployment uses a dedicated Cloudflare tunnel pointing to a separate Next.js service on loopback port 3001, with FastAPI on loopback port 8001. Tunnel credentials, machine-specific service definitions and passwords are intentionally excluded from this repository. Provision your own tunnel/DNS and service manager when deploying elsewhere; do not overwrite an existing website's routes.

`proxy.ts` protects all pages/assets/API requests when `DEMO_GATE_ENABLED=1`. Configure `DEMO_GATE_USER` and `DEMO_GATE_PASSWORD` in private `.local/portal.env`. The hostname `patientportal.lemmanet.com` also requires gate configuration and fails closed when missing. Use HTTPS; the public API launcher enables Secure patient/staff cookies. The shared outer password is separate from individual staff credentials.

Build the dedicated public frontend separately from development:

```sh
NEXT_BUILD_DIR=.next-public API_ORIGIN=http://127.0.0.1:8001 npm run build
.venv/bin/python scripts/run_public_demo.py api
# In another terminal, with node available on PATH:
.venv/bin/python scripts/run_public_demo.py web
```

Both processes, PostgreSQL and a properly configured tunnel must remain running. This is a controlled demo gate, not a production identity/deployment system.

## Verification

```sh
source .venv/bin/activate
python -m unittest discover -s backend/tests -t . -v
python -m alembic check
npm run build
```

The locked Python environment includes test dependencies; `backend/requirements.txt` and `requirements-dev.txt` describe the direct runtime/development dependencies. Tests use real PostgreSQL in uniquely named temporary schemas, migrate from scratch and clean up afterward. They do not reset the live demo database.

The 27 tests cover booking races, ownership, staff permissions, attachments, video signaling, temporary TURN credentials, consultation consent, concurrent note edits, finalization, addenda and persistence. Production builds and migration checks passed. Browser review verified the fictional registration-to-consultation-completion flow using synthetic video.

## Remaining scope

Real SMS verification, MFA/recovery and staff-management screens; configurable availability and cancellation/rescheduling; prescriptions and patient follow-up; Indian payments/refunds/receipts; notifications; Malayalam workflows; production storage/scanning; comprehensive audit/retention/export; backups and restore drills; India-region hosting and operational monitoring; clinical/legal approval. Remote monitoring and full multi-practice SaaS are later phases.

Use fictional information only. Do not use this proof of concept for actual clinical care.
