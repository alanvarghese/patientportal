'use client';

import { useCallback, useEffect, useRef, useState } from 'react';
import { Icon } from './components/icons';
import { useStaff } from './components/staff-access';
import { WorkspaceSidebar } from './components/workspace-sidebar';
import type { IconName } from './components/icons';

type Appointment = { id: string; patient_id: string; patient: string; age: number; visit_type: string; time: string; duration: number; status: 'confirmed' | 'waiting' | 'completed'; reason: string; doctor?:string; practitioner_id?:string; initials: string; color: string; patient_number: string };
type Dashboard = { practice: string; doctor: string; date: string; demo_date: string; timezone: string; doctors:{id:string;name:string}[]; appointments: Appointment[] };
function timeLabel(time: string) { const [h, m] = time.split(':').map(Number); return `${h % 12 || 12}:${String(m).padStart(2, '0')}`; }
function meridiem(time: string) { return Number(time.split(':')[0]) < 12 ? 'AM' : 'PM'; }
function Status({ status }: { status: Appointment['status'] }) { return <span className={`status ${status}`}><span />{status === 'waiting' ? 'Waiting' : status === 'completed' ? 'Completed' : 'Confirmed'}</span>; }
function Avatar({ appointment, large = false }: { appointment: Appointment; large?: boolean }) { return <span className={`avatar ${appointment.color} ${large ? 'large' : ''}`}>{appointment.initials}</span>; }

export default function Home() {
  const user=useStaff();
  const [doctorFilter,setDoctorFilter]=useState('');
  const [day, setDay] = useState('2026-10-19');
  const [data, setData] = useState<Dashboard | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [filter, setFilter] = useState('All appointments');
  const [search, setSearch] = useState('');
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState('');
  const dialogRef = useRef<HTMLDialogElement>(null);
  const load = useCallback(async (signal?: AbortSignal) => {
    setLoading(true); setError('');
    try {
      const response = await fetch(`/api/dashboard?day=${day}&practitioner_id=${encodeURIComponent(doctorFilter)}`, { signal, cache: 'no-store' });
      if(response.status===401){location.assign('/login');return;}
      if (!response.ok) throw new Error('The schedule could not be loaded. Check that the Python backend is running.');
      const result: Dashboard = await response.json();
      if (!signal?.aborted) setData(result);
    } catch (e) { if (!signal?.aborted) { setData(null); setError(e instanceof Error ? e.message : 'Unable to connect to the practice server.'); } }
    finally { if (!signal?.aborted) setLoading(false); }
  }, [day,doctorFilter]);
  useEffect(() => { const queryDay = new URLSearchParams(window.location.search).get('day'); if (queryDay && /^\d{4}-\d{2}-\d{2}$/.test(queryDay) && !Number.isNaN(Date.parse(queryDay))) setDay(queryDay); }, []);
  useEffect(() => { const controller = new AbortController(); void load(controller.signal); return () => controller.abort(); }, [load]);
  useEffect(() => { if (selectedId) dialogRef.current?.showModal(); else dialogRef.current?.close(); }, [selectedId]);
  const appointments = data?.appointments || [];
  const selected = appointments.find(a => a.id === selectedId);
  const waiting = appointments.filter(a => a.status === 'waiting');
  const completed = appointments.filter(a => a.status === 'completed');
  const next = waiting[0] || appointments.find(a => a.status === 'confirmed');
  const filtered = appointments.filter(a => (filter === 'All appointments' || (filter === 'Upcoming' ? a.status === 'confirmed' : a.status === filter.toLowerCase())) && `${a.patient} ${a.patient_number}`.toLowerCase().includes(search.toLowerCase()));
  // Explicit formatting keeps Node and browser locale versions consistent on hydration.
  const date = new Date(`${day}T12:00:00Z`);
  const weekday = ['Sunday', 'Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday'][date.getUTCDay()];
  const month = ['January', 'February', 'March', 'April', 'May', 'June', 'July', 'August', 'September', 'October', 'November', 'December'][date.getUTCMonth()];
  const shortDate = `${date.getUTCDate()} ${month.slice(0, 3)}`;
  const prettyDate = `${weekday}, ${date.getUTCDate()} ${month} ${date.getUTCFullYear()}`;
  function changeDay(amount: number) { const d = new Date(`${day}T12:00:00Z`); d.setUTCDate(d.getUTCDate() + amount); setDay(d.toISOString().slice(0, 10)); setSelectedId(null); setNotice(''); }
  async function checkIn(id: string) {
    setBusy(true); setNotice('');
    try {
      const response = await fetch(`/api/appointments/${id}/check-in`, { method: 'POST',headers:{'X-Practice-Client':'portal'} });
      if(response.status===401){location.assign('/login');return;}
      if (!response.ok) throw new Error('Check-in failed. Please try again.');
      const updated: Appointment = await response.json();
      setData(current => current ? { ...current, appointments: current.appointments.map(a => a.id === id ? {...a,...updated} : a) } : null);
      setNotice(`${updated.patient} is now in the waiting queue.`);
    } catch (e) { setNotice(e instanceof Error ? e.message : 'Check-in failed.'); }
    finally { setBusy(false); }
  }
  async function reset() {
    setBusy(true);
    try { const response = await fetch('/api/demo/reset', { method: 'POST',headers:{'X-Practice-Client':'portal'} }); if (!response.ok) throw new Error(); setSelectedId(null); setSearch(''); setFilter('All appointments'); setNotice('Sample appointments reset. Registered patients and their bookings are kept.'); if (day === '2026-10-19') await load(); else setDay('2026-10-19'); }
    catch { setNotice('Could not reset the demo. Check the backend connection.'); }
    finally { setBusy(false); }
  }
  return <div className="workspace">
    <WorkspaceSidebar active="today" />
    <div className="main-shell">
      <header className="topbar"><div><span className="breadcrumb">Workspace</span><span className="breadcrumb-slash">/</span><strong>Today</strong></div><div><a className="portal-link" href="/book"><Icon name="calendar" size={15} />Patient booking ↗</a><span className="demo-pill" style={{display:"inline-flex"}}><span /> Customer demo</span></div></header>
      <main>
        <div className="page-heading"><div><div className="eyebrow">YOUR PRACTICE, AT A GLANCE</div><h1>A little more clarity.<br className="mobile-break" /> A better day.</h1><p>{user?.name}{user?.role!=='doctor'&&` · ${data?.doctor||'Practice schedule'}`} </p></div><div className="date-badge"><Icon name="calendar" /><div><strong>{shortDate}</strong><span>{weekday}, {date.getUTCFullYear()}</span></div></div></div>
        <div className="demo-banner"><span className="demo-label">DEMO</span><span>Fictional patients · Demo changes are saved · All times IST</span>{user?.role==='medical_admin'&&<button onClick={reset} disabled={busy}><Icon name="refresh" size={14} />Reset demo</button>}</div>
        {notice && <div className="notice" role="status">{notice}<button aria-label="Dismiss notification" onClick={() => setNotice('')}><Icon name="close" size={16} /></button></div>}
        {error ? <div className="error-state" role="alert"><h2>We couldn’t load your schedule.</h2><p>{error}</p><button className="primary-button" onClick={() => void load()}>Try again</button></div> : <>
        <section className="stats" aria-label="Daily overview" aria-busy={loading}>
          {[{ name: 'Appointments', value: appointments.length, sub: 'Scheduled for the day', icon: 'calendar' }, { name: 'In the waiting room', value: waiting.length, sub: waiting.length ? 'Ready for your attention' : 'No patients waiting', icon: 'patients' }, { name: 'Completed', value: completed.length, sub: 'Visits wrapped up', icon: 'check' }].map((stat, i) => <div className="stat-card" key={stat.name}><div className="stat-title">{stat.name}<span className={`stat-icon stat-${i}`}><Icon name={stat.icon as IconName} size={18} /></span></div><div className="stat-value">{loading ? '—' : String(stat.value).padStart(2, '0')}</div><p>{stat.sub}</p></div>)}
        </section>
        {!loading && next && <section className="next-visit" aria-label="Next appointment"><div className="next-left"><span className="next-symbol"><Icon name="video" size={24} /></span><div><div className="next-label">{next.status === 'waiting' ? <><span className="live-dot" />PATIENT WAITING</> : 'NEXT APPOINTMENT'}</div><h2>{next.patient}<span>{next.visit_type}</span></h2><p><Icon name="clock" size={14} />{timeLabel(next.time)} {meridiem(next.time)} · {next.duration} min · Video consultation</p></div></div><button className="light-button" onClick={() => setSelectedId(next.id)}>Review appointment<Icon name="arrow" size={18} /></button></section>}
        <section className="schedule" aria-labelledby="schedule-title">
          <div className="schedule-heading"><div><h2 id="schedule-title">Your schedule <span>{loading ? '…' : appointments.length}</span></h2><p>{prettyDate}</p></div><div className="date-controls">{user?.role!=='doctor'&&<select className="form-input" aria-label="Filter by doctor" value={doctorFilter} onChange={e=>setDoctorFilter(e.target.value)}><option value="">All doctors</option>{data?.doctors.map(d=><option key={d.id} value={d.id}>{d.name}</option>)}</select>}<input className="schedule-date" type="date" aria-label="Schedule date" value={day} onChange={e => { if (e.target.value) setDay(e.target.value); }} /><button aria-label="Previous day" onClick={() => changeDay(-1)}><span className="rotate"><Icon name="chevron" size={17} /></span></button><button onClick={() => setDay('2026-10-19')} className="sample-day">Sample day</button><button aria-label="Next day" onClick={() => changeDay(1)}><Icon name="chevron" size={17} /></button></div></div>
          <div className="table-tools"><div className="filters" aria-label="Filter appointments">{['All appointments', 'Waiting', 'Upcoming', 'Completed'].map(f => <button key={f} aria-pressed={filter === f} className={filter === f ? 'chosen' : ''} onClick={() => setFilter(f)}>{f}{f === 'Waiting' && waiting.length > 0 && <span>{waiting.length}</span>}</button>)}</div><label className="search"><Icon name="search" size={17} /><input aria-label="Search patients" placeholder="Search patient…" value={search} onChange={e => setSearch(e.target.value)} /></label></div>
          <div className="table-scroll"><table><thead><tr><th scope="col">TIME</th><th scope="col">PATIENT</th><th scope="col">VISIT TYPE</th><th scope="col">STATUS</th><th scope="col"><span className="sr-only">Action</span></th></tr></thead><tbody>
            {!loading && filtered.map(a => <tr key={a.id} className={a.status === 'waiting' ? 'waiting-row' : ''}><td><strong className="time">{timeLabel(a.time)}<small>{meridiem(a.time)}</small></strong><span className="duration">{a.duration} min</span></td><td><div className="patient-cell"><Avatar appointment={a} /><div><strong>{a.patient}</strong><span>{a.age} years · {a.patient_number}</span></div></div></td><td><span className="visit-type"><Icon name="video" size={14} />{a.visit_type}</span><small className="record-contact">{a.doctor}</small></td><td><Status status={a.status} /></td><td><button className="row-button" aria-label={`View ${a.patient}'s appointment`} onClick={() => setSelectedId(a.id)}>View<Icon name="arrow" size={16} /></button></td></tr>)}
          </tbody></table></div>
          {loading && <div className="empty-state" role="status"><span className="loader" /><h3>Loading your day…</h3></div>}
          {!loading && !filtered.length && <div className="empty-state"><Icon name="calendar" size={30} /><h3>{appointments.length ? 'No matching appointments' : 'A clear schedule'}</h3><p>{appointments.length ? 'Try another name or status filter.' : 'Choose another date or open Patient booking to add an appointment.'}</p>{appointments.length > 0 && <button className="row-button" onClick={() => { setSearch(''); setFilter('All appointments'); }}>Clear filters</button>}</div>}
          <footer className="table-footer"><span>{loading ? 'Loading…' : `${filtered.length} of ${appointments.length} appointments`}</span><span><Icon name="video" size={14} /> Video appointments</span></footer>
        </section></>}
        <footer className="page-footer"><span className="footer-mark">p+</span><span>Made for a more personal practice.</span><span>Proof of concept · Registration & booking</span></footer>
      </main>
    </div>
    <dialog ref={dialogRef} className="appointment-dialog" onCancel={() => setSelectedId(null)} onClose={() => setSelectedId(null)} onClick={e => { if (e.target === e.currentTarget) setSelectedId(null); }}>
      {selected && <div className="dialog-content"><div className="dialog-heading"><span className="eyebrow">APPOINTMENT DETAILS</span><button aria-label="Close appointment details" onClick={() => setSelectedId(null)}><Icon name="close" /></button></div><div className="dialog-patient"><Avatar appointment={selected} large /><h2>{selected.patient}</h2><p>{selected.age} years · {selected.patient_number} · Fictional patient</p><Status status={selected.status} /></div><dl className="appointment-facts"><div><dt>Date</dt><dd>{prettyDate}</dd></div><div><dt>Time</dt><dd>{timeLabel(selected.time)} {meridiem(selected.time)} IST · {selected.duration} minutes</dd></div><div><dt>Visit</dt><dd>{selected.visit_type} · Video</dd></div></dl><div className="reason"><h3>Reason for visit</h3><p>{selected.reason}</p></div><div className="scope-note"><Icon name="heart" size={18} /><p>Open the consultation record to save notes and complete the visit. Prescriptions and patient follow-up are the next section.</p></div><div className="dialog-actions">{selected.status === 'confirmed' && <button className="primary-button" disabled={busy} onClick={() => void checkIn(selected.id)}>{busy ? 'Checking in…' : 'Check in patient'}<Icon name="check" size={17} /></button>}{selected.status === 'waiting' && <div className="waiting-message"><span className="live-dot" />Patient is in the demo waiting queue.</div>}{selected.status === 'completed' && <div className="waiting-message"><Icon name="check" size={18} />This sample appointment is completed.</div>}{user?.role==='doctor'&&<a className="primary-button" href={`/encounter?appointment=${encodeURIComponent(selected.id)}`}>{selected.status==='completed'?'View consultation record →':'Consultation notes →'}</a>}{user?.role==='doctor' && selected.status !== 'completed' && <a className="primary-button" href={`/consultation?appointment=${encodeURIComponent(selected.id)}`}>Open video consultation →</a>}<a className="secondary-button" href={`/patients?patient=${encodeURIComponent(selected.patient_id)}`}>Open patient record →</a><button className="secondary-button" onClick={() => setSelectedId(null)}>Back to schedule</button></div></div>}
    </dialog>
  </div>;
}
