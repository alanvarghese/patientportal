'use client';

import { FormEvent, useEffect, useRef, useState } from 'react';

type Config = { doctors:{id:string;name:string}[]; today: string; max_day: string; fee_paise: number; privacy_notice: string; booking_terms: string };
type Profile = { id: string; patient_number: string; name: string; date_of_birth: string; phone: string; email: string | null; language: string };
type Hold = { hold_id: string; expires_at: string; day: string; time: string; duration: number; fee_paise: number; visit_type: string; reason: string };
type Booking = { doctor:string; id: string; reference: string; patient: string; patient_number: string; day: string; time: string; duration: number; fee_paise: number; visit_type: string; reason: string; status: string };
const headers = { 'Content-Type': 'application/json', 'X-Practice-Client': 'portal' };
function money(paise: number) { return `₹${(paise / 100).toFixed(0)}`; }
function timeText(time: string) { const [h, m] = time.split(':').map(Number); return `${h % 12 || 12}:${String(m).padStart(2, '0')} ${h < 12 ? 'AM' : 'PM'}`; }
function dateText(day: string) { const d = new Date(`${day}T12:00:00Z`); return `${d.getUTCDate()} ${['January','February','March','April','May','June','July','August','September','October','November','December'][d.getUTCMonth()]} ${d.getUTCFullYear()}`; }
async function api(path: string, method = 'GET', body?: unknown, signal?: AbortSignal) {
  const response = await fetch(`/api/patient${path}`, { method, headers, body: body === undefined ? undefined : JSON.stringify(body), cache: 'no-store', signal });
  const data = await response.json().catch(() => ({}));
  if (!response.ok) {
    const message = typeof data.detail === 'string' ? data.detail : Array.isArray(data.detail) ? data.detail.map((e: {msg: string}) => e.msg.replace('Value error, ', '')).join('. ') : 'We could not complete that request. Please try again.';
    throw new Error(message);
  }
  return data;
}

export default function PatientBooking() {
  const [config, setConfig] = useState<Config | null>(null);
  const [loading, setLoading] = useState(true);
  const [step, setStep] = useState(0);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [phone, setPhone] = useState('');
  const [challenge, setChallenge] = useState<{ challenge_id: string; demo_code: string } | null>(null);
  const [code, setCode] = useState('');
  const [profile, setProfile] = useState<Profile | null>(null);
  const [name, setName] = useState('');
  const [birth, setBirth] = useState('');
  const [email, setEmail] = useState('');
  const [language, setLanguage] = useState('English');
  const [privacy, setPrivacy] = useState(false);
  const [doctorId,setDoctorId]=useState('demo-doctor');
  const [day, setDay] = useState('');
  const [slots, setSlots] = useState<{ time: string; available: boolean }[]>([]);
  const [slotsLoading, setSlotsLoading] = useState(false);
  const [slotsError, setSlotsError] = useState('');
  const [slotRefresh, setSlotRefresh] = useState(0);
  const [slot, setSlot] = useState('');
  const [visit, setVisit] = useState('First visit');
  const [reason, setReason] = useState('');
  const [hold, setHold] = useState<Hold | null>(null);
  const [seconds, setSeconds] = useState(0);
  const [terms, setTerms] = useState(false);
  const [booking, setBooking] = useState<Booking | null>(null);
  const [bookings, setBookings] = useState<Booking[]>([]);
  const heading = useRef<HTMLHeadingElement>(null);

  async function initialize(signal?: AbortSignal) {
    setLoading(true); setError('');
    try {
      const settings: Config = await api('/config', 'GET', undefined, signal);
      if (signal?.aborted) return;
      setConfig(settings); setDay(settings.today);setDoctorId(settings.doctors[0]?.id||'demo-doctor');
      const response = await fetch('/api/patient/me', { cache: 'no-store', signal });
      if (response.ok) { const me = await response.json(); setProfile(me.profile); setPhone(me.phone); setBookings(me.bookings); setStep(me.profile ? 2 : 1); }
      else if (response.status !== 401) throw new Error('We could not restore your session. Please try again.');
    } catch (e) { if (!signal?.aborted) setError(e instanceof Error ? e.message : 'Could not load the patient portal.'); }
    finally { if (!signal?.aborted) setLoading(false); }
  }
  useEffect(() => { const controller = new AbortController(); void initialize(controller.signal); return () => controller.abort(); }, []);
  useEffect(() => { heading.current?.focus(); }, [step]);
  useEffect(() => {
    if (!profile || !day || step !== 2) return;
    const controller = new AbortController(); setSlotsLoading(true); setSlotsError(''); setSlots([]); setSlot('');
    api(`/availability?day=${day}&practitioner_id=${doctorId}`, 'GET', undefined, controller.signal).then(data => { if (!controller.signal.aborted) setSlots(data.slots); }).catch(e => { if (!controller.signal.aborted) setSlotsError(e.message); }).finally(() => { if (!controller.signal.aborted) setSlotsLoading(false); });
    return () => controller.abort();
  }, [profile, day, step, slotRefresh,doctorId]);
  useEffect(() => {
    if (!hold || step !== 3) return;
    const tick = () => setSeconds(Math.max(0, Math.floor((new Date(hold.expires_at).getTime() - Date.now()) / 1000)));
    tick(); const timer = setInterval(tick, 1000); return () => clearInterval(timer);
  }, [hold, step]);
  async function act(action: () => Promise<void>) { setBusy(true); setError(''); try { await action(); } catch (e) { setError(e instanceof Error ? e.message : 'Please try again.'); } finally { setBusy(false); } }
  async function requestCode(e: FormEvent) { e.preventDefault(); await act(async () => { setChallenge(await api('/otp/challenges', 'POST', { phone })); setCode(''); }); }
  async function verifyCode(e: FormEvent) { e.preventDefault(); await act(async () => { const me = await api('/otp/verify', 'POST', { challenge_id: challenge?.challenge_id, code }); setProfile(me.profile); setPhone(me.phone); setStep(me.profile ? 2 : 1); const current = await api('/me'); setBookings(current.bookings); }); }
  async function register(e: FormEvent) { e.preventDefault(); await act(async () => { const p = await api('/profile', 'POST', { name, date_of_birth: birth, email, language, accept_privacy: privacy }); setProfile(p); setStep(2); }); }
  async function reserve(e: FormEvent) { e.preventDefault(); await act(async () => { try { const h: Hold = await api('/holds', 'POST', { day, start_time: slot, visit_type: visit, reason,practitioner_id:doctorId }); setHold(h); setTerms(false); setStep(3); } catch(e) { setSlotRefresh(n => n + 1); throw e; } }); }
  async function changeAppointment() { if (!hold) { setStep(2); return; } await act(async () => { await api(`/holds/${hold.hold_id}`, 'DELETE'); setHold(null); setStep(2); }); }
  async function confirm(e: FormEvent) { e.preventDefault(); await act(async () => { const result: Booking = await api(`/holds/${hold?.hold_id}/confirm`, 'POST', { accept_terms: terms }); setBooking(result); setBookings(current => [result, ...current.filter(b => b.id !== result.id)]); setStep(4); }); }
  async function signOut() { await act(async () => { if (hold && step === 3) await api(`/holds/${hold.hold_id}`, 'DELETE'); await api('/logout', 'POST'); setProfile(null); setChallenge(null); setPhone(''); setCode(''); setName(''); setBirth(''); setEmail(''); setPrivacy(false); setHold(null); setBooking(null); setBookings([]); setStep(0); }); }

  const steps = ['Verify mobile', 'Patient details', 'Choose appointment', 'Review & confirm'];
  return <div className="patient-portal">
    <header className="patient-header"><a className="brand" href="/book" aria-label="Patient portal home"><span className="brand-mark">p<span>+</span></span><span>practice<span className="brand-dot">.</span></span></a><span className="patient-header-label">YOUR CARE STARTS HERE</span><a href="/" className="secondary-button">Staff workspace ↗</a></header>
    <div className="portal-demo"><span className="demo-label">DEMO</span>Use fictional details only. Codes appear on screen; no SMS or payment is sent.</div>
    <div className="booking-layout">
      <aside className="booking-intro"><div className="eyebrow">KERALA TELEMEDICINE</div><h1>Care that fits<br />into your day.</h1><p>Register with the practice and choose a time to speak with your doctor.</p><ol className="booking-steps">{steps.map((label, i) => <li key={label} className={step === i ? 'current' : step > i ? 'done' : ''} aria-current={step === i ? 'step' : undefined}><span>{step > i ? '✓' : String(i + 1).padStart(2, '0')}</span><div>{label}<small>{['A simple mobile check','A few details about you','Pick a convenient time','All set for your visit'][i]}</small></div></li>)}</ol><div className="booking-help"><strong>A simple first visit.</strong><p>20-minute video appointments, Monday–Saturday. All appointment times are in IST.</p><small>The doctor’s specialty and practice details will be confirmed before launch.</small></div></aside>
      <main className="booking-main">
        {loading ? <div className="booking-card empty-state" role="status"><span className="loader" /><h2>Getting things ready…</h2></div> : <>
        {error && <div className="booking-error" role="alert">{error}{!config && <button onClick={() => void initialize()}>Try again</button>}</div>}
        {config && <section className="booking-card">
          <div className="booking-card-top"><span className="eyebrow">{step < 4 ? `STEP ${String(step + 1).padStart(2,'0')} OF 04` : 'BOOKING COMPLETE'}</span>{step > 0 && <button className="text-button" disabled={busy} onClick={signOut}>Sign out</button>}</div>
          {step === 0 && <><h2 tabIndex={-1} ref={heading}>{challenge ? 'Verify your mobile.' : 'Welcome to your practice.'}</h2><p className="form-intro">{challenge ? `Enter the six-digit code for ${phone}.` : 'Start with your mobile number. Returning patients can use the same number to find their profile.'}</p>
            {!challenge ? <form onSubmit={requestCode}><label className="field-label" htmlFor="phone">Mobile number</label><div className="phone-field"><span>+91</span><input id="phone" type="tel" inputMode="numeric" autoComplete="tel-national" placeholder="10-digit mobile number" pattern="[6-9][0-9]{9}" maxLength={10} required value={phone} onChange={e => setPhone(e.target.value.replace(/\D/g, ''))} /></div><p className="field-hint">One adult patient profile per mobile number in this demo.</p><button className="primary-button full-button" disabled={busy}>{busy ? 'Preparing code…' : 'Get verification code →'}</button></form>
            : <form onSubmit={verifyCode}><div className="demo-code"><span>DEMO VERIFICATION CODE</span><strong>{challenge.demo_code}</strong><p>No SMS was sent. This code expires after five minutes.</p></div><label className="field-label" htmlFor="code">Verification code</label><input className="form-input code-input" id="code" inputMode="numeric" autoComplete="one-time-code" pattern="[0-9]{6}" minLength={6} maxLength={6} required value={code} onChange={e => setCode(e.target.value.replace(/\D/g, ''))} placeholder="Enter 6-digit code" /><button className="primary-button full-button" disabled={busy}>{busy ? 'Verifying…' : 'Verify & continue →'}</button><div className="form-bottom-links"><button className="text-button" type="button" disabled={busy} onClick={() => { setChallenge(null); setCode(''); setError(''); }}>Use another number</button><button className="text-button" type="button" disabled={busy} onClick={() => void act(async () => { setChallenge(await api('/otp/challenges','POST',{phone})); setCode(''); })}>Request new code</button></div></form>}
          </>}
          {step === 1 && <><h2 tabIndex={-1} ref={heading}>Let’s get to know you.</h2><p className="form-intro">Create your adult patient profile. Your mobile number has been verified for this demo.</p><div className="verified-mobile">✓ {phone} <span>Demo verified</span></div><form onSubmit={register}>
            <label className="field-label" htmlFor="patient-name">Full name</label><input id="patient-name" className="form-input" autoComplete="name" minLength={2} maxLength={100} required placeholder="As you would like it on your record" value={name} onChange={e => setName(e.target.value)} />
            <div className="form-grid"><div><label className="field-label" htmlFor="birth">Date of birth</label><input id="birth" className="form-input" type="date" autoComplete="bday" max={config.today} required value={birth} onChange={e => setBirth(e.target.value)} /></div><div><label className="field-label" htmlFor="language">Preferred language</label><select id="language" className="form-input" value={language} onChange={e => setLanguage(e.target.value)}><option>English</option><option>Malayalam</option></select></div></div><p className="field-hint">Adult registration only. Language preference is saved; the demo interface is in English.</p>
            <label className="field-label" htmlFor="email">Email <span>(optional)</span></label><input id="email" className="form-input" type="email" autoComplete="email" placeholder="name@example.com" maxLength={254} value={email} onChange={e => setEmail(e.target.value)} />
            <label className="consent-check"><input type="checkbox" required checked={privacy} onChange={e => setPrivacy(e.target.checked)} /><span>{config.privacy_notice}</span></label><button className="primary-button full-button" disabled={busy}>{busy ? 'Saving profile…' : 'Save profile & choose a time →'}</button>
          </form></>}
          {step === 2 && profile && <><h2 tabIndex={-1} ref={heading}>Find your time for care.</h2><p className="form-intro">Choose an available appointment for {profile.name}.</p><div className="registered-profile"><span className="profile-circle">{profile.name.split(' ').map(n => n[0]).slice(0,2).join('')}</span><div><strong>{profile.name}</strong><small>{profile.patient_number} · {profile.phone}</small></div><span className="saved-profile">✓ Saved</span></div><form onSubmit={reserve}>
            <div className="form-grid"><div><label className="field-label" htmlFor="appointment-day">Appointment date</label><input className="form-input" id="appointment-day" type="date" min={config.today} max={config.max_day} value={day} required onChange={e => setDay(e.target.value)} /></div><div><label className="field-label" htmlFor="visit-type">Visit type</label><select className="form-input" id="visit-type" value={visit} onChange={e => setVisit(e.target.value)}><option>First visit</option><option>Follow-up</option></select></div></div>
            <label className="field-label" htmlFor="booking-doctor">Doctor</label><select className="form-input" id="booking-doctor" value={doctorId} onChange={e=>setDoctorId(e.target.value)}>{config.doctors.map(d=><option key={d.id} value={d.id}>{d.name}</option>)}</select><fieldset className="slot-fieldset"><legend>Available times <span>IST · 20-minute video visit</span></legend>{slotsLoading ? <p className="slot-empty" role="status">Finding available times…</p> : slotsError ? <p className="slot-empty" role="alert">{slotsError} <button type="button" className="text-button" onClick={() => setSlotRefresh(n => n + 1)}>Retry</button></p> : slots.length ? <div className="slot-grid">{slots.map(s => <label key={s.time} className={`slot-option ${!s.available ? 'unavailable' : ''} ${slot === s.time ? 'selected' : ''}`}><input type="radio" name="appointment-time" required disabled={!s.available} value={s.time} checked={slot === s.time} onChange={() => setSlot(s.time)} /><span>{timeText(s.time)}</span>{!s.available && <small>Unavailable</small>}</label>)}</div> : <p className="slot-empty">No appointments on this date. Please choose another day. The practice is closed on Sundays.</p>}</fieldset>
            <label className="field-label" htmlFor="reason">Reason for visit</label><textarea className="form-input" id="reason" minLength={3} maxLength={500} required rows={3} placeholder="A short description to help the doctor prepare. Use fictional details only." value={reason} onChange={e => setReason(e.target.value)} /><div className="booking-fee"><div><strong>{money(config.fee_paise)}</strong><span>Sample consultation fee</span></div><small>Demo booking · No payment collected</small></div><button className="primary-button full-button" disabled={busy || !slot || slotsLoading}>{busy ? 'Holding your time…' : 'Review appointment →'}</button>
          </form>{bookings.length > 0 && <div className="recent-bookings"><h3>Your saved bookings</h3>{bookings.map(b => <button key={b.id} className="saved-booking" onClick={() => { setBooking(b); setStep(4); }}><span>{dateText(b.day)} · {timeText(b.time)}<small>{b.doctor} · {b.reference}</small></span><span>View →</span></button>)}</div>}</>}
          {step === 3 && hold && profile && <><h2 tabIndex={-1} ref={heading}>Everything look right?</h2><p className="form-intro">Review your visit before confirming.</p><div className={`hold-timer ${seconds === 0 ? 'expired' : ''}`} role="status">{seconds > 0 ? `Your time is held for ${Math.floor(seconds / 60)}:${String(seconds % 60).padStart(2, '0')}` : 'Your hold has expired. Choose a time again.'}</div><dl className="review-facts"><div><dt>Patient</dt><dd>{profile.name}<small>{profile.patient_number}</small></dd></div><div><dt>Appointment</dt><dd>{dateText(hold.day)}<small>{timeText(hold.time)} IST · {hold.duration} minutes</small></dd></div><div><dt>Doctor</dt><dd>{config.doctors.find(d=>d.id===doctorId)?.name}</dd></div><div><dt>Consultation</dt><dd>{hold.visit_type} · Video</dd></div><div><dt>Reason</dt><dd>{hold.reason}</dd></div><div><dt>Sample fee</dt><dd>{money(hold.fee_paise)}<small>No payment collected</small></dd></div></dl><form onSubmit={confirm}><label className="consent-check"><input type="checkbox" required checked={terms} onChange={e => setTerms(e.target.checked)} /><span>{config.booking_terms}</span></label><button className="primary-button full-button" disabled={busy || seconds === 0}>{busy ? 'Confirming…' : 'Confirm demo appointment →'}</button><button type="button" className="secondary-button full-button" disabled={busy} onClick={changeAppointment}>Change appointment</button></form></>}
          {step === 4 && booking && <><div className="booking-success-icon">✓</div><h2 tabIndex={-1} ref={heading}>You’re booked in.</h2><p className="form-intro">Your appointment is saved with the practice. It also appears in the doctor’s schedule.</p><div className="confirmation-reference"><span>BOOKING REFERENCE</span><strong>{booking.reference}</strong></div><dl className="review-facts"><div><dt>Patient</dt><dd>{booking.patient}<small>{booking.patient_number}</small></dd></div><div><dt>Date & time</dt><dd>{dateText(booking.day)}<small>{timeText(booking.time)} IST · {booking.duration} minutes</small></dd></div><div><dt>Doctor</dt><dd>{booking.doctor}</dd></div><div><dt>Visit</dt><dd>{booking.visit_type} · Video</dd></div><div><dt>Sample fee</dt><dd>{money(booking.fee_paise)}<small>Not collected · Demo only</small></dd></div><div><dt>Status</dt><dd className="confirmation-status">{booking.status === 'waiting' ? 'Checked in' : booking.status === 'completed' ? 'Completed' : 'Confirmed'}</dd></div></dl><div className="next-steps-note"><strong>Before your visit</strong><p>Keep relevant reports ready and check your camera and microphone. Use the video link below for a demonstration call. Clinical consent will be added before real consultations.</p><small>No confirmation SMS or email was sent in this demo.</small></div><a className="primary-button full-button" href={`/consultation?appointment=${booking.id}&role=patient`}>Open video consultation →</a><button className="primary-button full-button" disabled={busy} onClick={() => { setBooking(null); setHold(null); setTerms(false); setReason(''); setStep(2); }}>Back to my appointments →</button><a className="secondary-button full-button" href={`/?day=${booking.day}`}>View in doctor workspace ↗</a></>}
        </section>}
        <p className="patient-footer">A local demonstration of your patient journey. Fictional data only.</p></>}
      </main>
    </div>
  </div>;
}
