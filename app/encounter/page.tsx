'use client';
import { useEffect,useState } from 'react';
import { EncounterNotes } from './notes';
import { WorkspaceSidebar } from '../components/workspace-sidebar';

export default function EncounterPage(){
 const [id,setId]=useState('');
 useEffect(()=>{setId(new URLSearchParams(location.search).get('appointment')||'');},[]);
 return <div className="workspace"><WorkspaceSidebar active="today"/><div className="main-shell"><header className="topbar"><strong>Consultation record</strong><a className="portal-link" href="/">Back to schedule →</a></header><main><div className="page-heading"><div><div className="eyebrow">TIME TO LISTEN. SPACE TO DOCUMENT.</div><h1>A clear record of care.</h1><p>Review, save and finalize the consultation for this appointment.</p></div></div>{id?<EncounterNotes appointmentId={id} videoLink/>:<p>Open a consultation record from an appointment in the schedule.</p>}</main></div></div>;
}
