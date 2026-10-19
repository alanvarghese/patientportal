'use client';

import { useEffect, useRef, useState } from 'react';
import { Icon } from '../components/icons';
import { WorkspaceSidebar } from '../components/workspace-sidebar';
import { useStaff } from '../components/staff-access';
import { Attachments } from './attachments';

type Patient = { id: string; patient_number: string; name: string; age: number; date_of_birth: string | null; phone: string | null; email: string | null; language: string | null; initials: string; color: string; source: 'registered' | 'sample'; appointment_count: number };
type Directory = { patients: Patient[]; total: number; offset: number; limit: number; practice_total: number; registered_count: number; sample_count: number };
type Visit = { id: string; day: string; time: string; duration: number; visit_type: string; reason: string; status: 'confirmed' | 'waiting' | 'completed'; booking_reference: string | null; fee_paise: number | null; payment_status: string | null };
type RecordDetail = { patient: Patient; registration_recorded_at: string | null; registration_recorded_on: string | null; appointment_count: number; completed_count: number; history_offset: number; history_limit: number; appointments: Visit[] };
function dateLabel(day: string) { const d = new Date(`${day}T12:00:00Z`); return `${d.getUTCDate()} ${['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'][d.getUTCMonth()]} ${d.getUTCFullYear()}`; }
function timeLabel(time: string) { const [h,m] = time.split(':').map(Number); return `${h % 12 || 12}:${String(m).padStart(2,'0')} ${h < 12 ? 'AM' : 'PM'}`; }
function PatientAvatar({ patient, large = false }: { patient: Patient; large?: boolean }) { return <span className={`avatar ${patient.color} ${large ? 'large' : ''}`}>{patient.initials}</span>; }
async function read(path: string, signal?: AbortSignal) {
  const r = await fetch(`/api/records/patients${path}`, { signal, cache: 'no-store' });
  if(r.status===401){location.assign('/login');throw new Error('Please sign in again.');}
  if (!r.ok) throw new Error(r.status === 404 ? 'This patient record could not be found.' : 'Patient records are unavailable. Please check the connection and try again.');
  return r.json();
}

export default function Patients() {
  const user=useStaff();
  const [directory, setDirectory] = useState<Directory | null>(null);
  const [search, setSearch] = useState('');
  const [query, setQuery] = useState('');
  const [source, setSource] = useState('all');
  const [offset, setOffset] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [refresh, setRefresh] = useState(0);
  const [selected, setSelected] = useState<string | null>(null);
  const [detail, setDetail] = useState<RecordDetail | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);
  const [detailError, setDetailError] = useState('');
  const [historyOffset, setHistoryOffset] = useState(0);
  const [detailRefresh, setDetailRefresh] = useState(0);
  const [tab, setTab] = useState<'profile' | 'history' | 'attachments'>('profile');
  const panelRef = useRef<HTMLDialogElement>(null);
  const LIMIT = 10;
  useEffect(() => { const value = new URLSearchParams(window.location.search).get('patient'); if (value) setSelected(value); }, []);
  useEffect(() => { const timer = setTimeout(() => { setQuery(search.trim()); setOffset(0); }, 250); return () => clearTimeout(timer); }, [search]);
  useEffect(() => {
    const controller = new AbortController(); setLoading(true); setError('');
    const params = new URLSearchParams({ q:query, source, offset:String(offset), limit:String(LIMIT) });
    read(`?${params}`,controller.signal).then(data => { if (!controller.signal.aborted) setDirectory(data); }).catch(e => { if (!controller.signal.aborted) { setDirectory(null); setError(e.message); } }).finally(() => { if (!controller.signal.aborted) setLoading(false); });
    return () => controller.abort();
  }, [query, source, offset, refresh]);
  useEffect(() => {
    if (selected) panelRef.current?.showModal(); else panelRef.current?.close();
  }, [selected]);
  useEffect(() => {
    if (!selected) return;
    const controller = new AbortController(); setDetailLoading(true); setDetailError(''); setDetail(null);
    read(`/${encodeURIComponent(selected)}?history_offset=${historyOffset}`,controller.signal).then(data => { if (!controller.signal.aborted) setDetail(data); }).catch(e => { if (!controller.signal.aborted) setDetailError(e.message); }).finally(() => { if (!controller.signal.aborted) setDetailLoading(false); });
    return () => controller.abort();
  }, [selected, historyOffset, detailRefresh]);
  function open(patient: Patient) { setHistoryOffset(0); setTab('profile'); setSelected(patient.id); }
  function close() { setSelected(null); setDetail(null); setDetailError(''); const url = new URL(window.location.href); url.searchParams.delete('patient'); window.history.replaceState(null,'',url); }
  function clear() { setSearch(''); setQuery(''); setOffset(0); setSource('all'); }
  const p = detail?.patient;
  return <div className="workspace">
    <WorkspaceSidebar active="patients" />
    <div className="main-shell"><header className="topbar"><div><span className="breadcrumb">Workspace</span><span className="breadcrumb-slash">/</span><strong>Patient records</strong></div><div><a className="portal-link" href="/book"><Icon name="calendar" size={15} />Patient booking ↗</a><span className="demo-pill" style={{display:'inline-flex'}}><span />Customer demo</span></div></header>
    <main>
      <div className="page-heading"><div><div className="eyebrow">PEOPLE AT THE HEART OF YOUR PRACTICE</div><h1>A familiar face. The full picture.</h1><p>Patient profiles and appointment history, together in one place.</p></div><button className="secondary-button records-refresh" onClick={() => setRefresh(n=>n+1)} disabled={loading}><Icon name="refresh" size={15} />Refresh</button></div>
      <div className="demo-banner"><span className="demo-label">DEMO</span><span>Fictional records only · Patient profiles, appointments and attachments</span></div>
      <section className="stats" aria-label="Patient overview">
        {[{label:user?.role==='doctor'?'Your assigned patients':'Patients in your practice',value:directory?.practice_total,sub:'A place for every patient',icon:'patients' as const},{label:'Registered patients',value:directory?.registered_count,sub:'Saved patient profiles',icon:'check' as const},{label:'Original sample patients',value:directory?.sample_count,sub:'The six fictional starter profiles',icon:'heart' as const}].map((s,i)=><div className="stat-card" key={s.label}><div className="stat-title">{s.label}<span className={`stat-icon stat-${i}`}><Icon name={s.icon} size={18} /></span></div><div className="stat-value">{loading || s.value === undefined ? '—' : String(s.value).padStart(2,'0')}</div><p>{s.sub}</p></div>)}
      </section>
      <section className="schedule patient-directory" aria-labelledby="directory-title"><div className="schedule-heading"><div><h2 id="directory-title">Patient directory <span>{loading ? '…' : directory?.total ?? 0}</span></h2><p>Find a patient and open their record.</p></div>{user?.role==='medical_admin'&&<a className="primary-button" href="/registration">Register a patient ↗</a>}</div>
      <div className="table-tools"><div className="filters" aria-label="Patient type">{[{value:'all',label:'All patients'},{value:'registered',label:'Registered patients'},{value:'sample',label:'Sample profiles'}].map(f=><button key={f.value} className={source===f.value?'chosen':''} aria-pressed={source===f.value} onClick={()=>{setSource(f.value);setOffset(0);}}>{f.label}</button>)}</div><label className="search records-search"><Icon name="search" size={17}/><input aria-label="Search patient records" placeholder="Name, patient number or mobile…" value={search} maxLength={100} onChange={e=>setSearch(e.target.value)}/></label></div>
      {error ? <div className="empty-state" role="alert"><h3>We couldn’t load your patients.</h3><p>{error}</p><button className="secondary-button" onClick={()=>setRefresh(n=>n+1)}>Try again</button></div> : loading ? <div className="empty-state" role="status"><span className="loader"/><h3>Finding your patients…</h3></div> : !directory?.patients.length ? <div className="empty-state"><Icon name="patients" size={30}/><h3>{directory?.practice_total ? 'No matching patients' : 'Your patient directory starts here'}</h3><p>{directory?.practice_total ? 'Try another name, patient number or mobile number.' : 'Profiles registered through the patient portal will appear here.'}</p><button className="secondary-button" onClick={clear}>Clear search & filters</button></div> : <div className="table-scroll"><table><thead><tr><th scope="col">PATIENT</th><th scope="col">CONTACT</th><th scope="col">PROFILE</th><th scope="col">APPOINTMENTS</th><th scope="col"><span className="sr-only">Action</span></th></tr></thead><tbody>{directory.patients.map(patient=><tr key={patient.id}><td><div className="patient-cell"><PatientAvatar patient={patient}/><div><strong>{patient.name}</strong><span>{patient.patient_number} · {patient.age} years</span></div></div></td><td><span className="record-contact">{patient.phone || 'Not recorded'}<small>{patient.language || 'Language not recorded'}</small></span></td><td><span className={`profile-source ${patient.source}`}>{patient.source==='registered'?'Registered patient':'Sample profile'}</span></td><td><span className="visit-count">{patient.appointment_count}<small>{patient.appointment_count===1?'appointment':'appointments'}</small></span></td><td><button className="row-button" onClick={()=>open(patient)} aria-label={`Open ${patient.name}'s record`}>Open record<Icon name="arrow" size={15}/></button></td></tr>)}</tbody></table></div>}
      <footer className="table-footer"><span>{loading?'Loading…':`${directory?.total ? offset+1 : 0}–${Math.min(offset+LIMIT,directory?.total||0)} of ${directory?.total||0} patients`}</span><div className="records-pagination"><button aria-label="Previous patient page" disabled={loading||offset===0} onClick={()=>setOffset(n=>Math.max(0,n-LIMIT))}>← Previous</button><button aria-label="Next patient page" disabled={loading||!directory||offset+LIMIT>=directory.total} onClick={()=>setOffset(n=>n+LIMIT)}>Next →</button></div></footer>
      </section><footer className="page-footer"><span className="footer-mark">p+</span><span>Made for a more personal practice.</span><span>Proof of concept · Patient records</span></footer>
    </main></div>
    <dialog ref={panelRef} className="record-dialog" aria-label="Patient record" onCancel={close} onClose={close} onClick={e=>{if(e.target===e.currentTarget)close();}}><div className="record-dialog-inner"><div className="dialog-heading"><span className="eyebrow">PATIENT RECORD</span><button aria-label="Close patient record" onClick={close}><Icon name="close"/></button></div>
      {detailLoading ? <div className="empty-state" role="status"><span className="loader"/><h3>Opening the record…</h3></div> : detailError ? <div className="empty-state" role="alert"><h3>Record unavailable</h3><p>{detailError}</p><button className="secondary-button" onClick={()=>setDetailRefresh(n=>n+1)}>Try again</button></div> : p && detail ? <>
      <div className="record-patient-heading"><PatientAvatar patient={p} large/><div><h2>{p.name}</h2><p>{p.patient_number} · {p.age} years</p><span className={`profile-source ${p.source}`}>{p.source==='registered'?'Registered patient':'Sample profile'}</span></div></div>
      {user?.role==='medical_admin'&&<p><a className="secondary-button" href={`/registration?patient=${p.id}`}>Edit details or book appointment →</a></p>}<div className="record-summary"><div><strong>{detail.appointment_count}</strong><span>Appointments</span></div><div><strong>{detail.completed_count}</strong><span>Marked completed</span></div><div><strong>{p.language||'—'}</strong><span>Preferred language</span></div></div>
      <div className="record-tabs" role="tablist" aria-label="Record sections"><button role="tab" id="profile-tab" aria-controls="record-profile" aria-selected={tab==='profile'} onClick={()=>setTab('profile')}>Profile</button><button role="tab" id="history-tab" aria-controls="record-history" aria-selected={tab==='history'} onClick={()=>setTab('history')}>Appointment history <span>{detail.appointment_count}</span></button>{user?.role!=='medical_admin'&&<button role="tab" id="attachments-tab" aria-controls="record-attachments" aria-selected={tab==='attachments'} onClick={()=>setTab('attachments')}>Attachments</button>}</div>
      {tab==='profile' ? <section id="record-profile" role="tabpanel" aria-labelledby="profile-tab"><dl className="record-demographics"><div><dt>Full name</dt><dd>{p.name}</dd></div><div><dt>Date of birth</dt><dd>{p.date_of_birth?dateLabel(p.date_of_birth):'Not recorded'}{!p.date_of_birth&&<small>Original sample profile uses a fictional age.</small>}</dd></div><div><dt>Mobile number</dt><dd>{p.phone||'Not recorded'}</dd></div><div><dt>Email</dt><dd>{p.email||'Not provided'}<small>Optional contact detail</small></dd></div><div><dt>Preferred language</dt><dd>{p.language||'Not recorded'}</dd></div><div><dt>Demo registration</dt><dd>{detail.registration_recorded_on?`Recorded ${dateLabel(detail.registration_recorded_on)}`:'No portal registration recorded'}<small>Registration agreement is separate from clinical consent.</small></dd></div></dl><div className="scope-note record-scope"><Icon name="heart" size={19}/><p>Reports and images are saved in Attachments. Assigned doctors can open consultation records from appointment history. Prescriptions and patient follow-up are the next section.</p></div></section> : tab==='attachments' ? <Attachments key={p.id} patientId={p.id} patientName={p.name}/> : <section id="record-history" role="tabpanel" aria-labelledby="history-tab"><p className="history-description">Booking history and attendance status. A completed appointment does not imply a signed clinical record. Times are in IST.</p>{detail.appointments.length ? <div className="visit-history">{detail.appointments.map(visit=><article className="history-entry" key={visit.id}><div className="history-entry-heading"><div><strong>{dateLabel(visit.day)}</strong><p>{timeLabel(visit.time)} IST · {visit.duration} min · Video</p></div><span className={`status ${visit.status}`}><span/>{visit.status==='waiting'?'Waiting':visit.status==='completed'?'Completed':'Confirmed'}</span></div><h3>{visit.visit_type}</h3><p className="history-reason">{visit.reason}</p>{visit.booking_reference&&<small className="history-reference">{visit.booking_reference}</small>}{user?.role==='doctor'&&<a className="row-button" href={`/encounter?appointment=${visit.id}`}>Consultation record →</a>}<a className="row-button" href={`/?day=${visit.day}`}>View in daily schedule <Icon name="arrow" size={14}/></a></article>)}</div>:<div className="empty-state"><Icon name="calendar" size={28}/><h3>No appointments yet</h3><p>This profile is saved and ready for its first booking.</p><a className="secondary-button" href="/book">Open patient booking ↗</a></div>}{detail.appointment_count>10&&<div className="history-pagination"><button className="secondary-button" disabled={historyOffset===0} onClick={()=>setHistoryOffset(n=>Math.max(0,n-10))}>← Newer</button><span>{historyOffset+1}–{Math.min(historyOffset+10,detail.appointment_count)} of {detail.appointment_count}</span><button className="secondary-button" disabled={historyOffset+10>=detail.appointment_count} onClick={()=>setHistoryOffset(n=>n+10)}>Older →</button></div>}</section>}
      </> : null}
    </div></dialog>
  </div>;
}
