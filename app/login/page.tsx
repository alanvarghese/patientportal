'use client';
import { FormEvent, useState } from 'react';

export default function Login(){
 const [username,setUsername]=useState(''),[password,setPassword]=useState(''),[error,setError]=useState(''),[busy,setBusy]=useState(false);
 async function login(e:FormEvent){e.preventDefault();setBusy(true);setError('');try{
  const r=await fetch('/api/staff/login',{method:'POST',headers:{'Content-Type':'application/json','X-Practice-Client':'portal'},body:JSON.stringify({username,password})});
  const d=await r.json();if(!r.ok)throw new Error(typeof d.detail==='string'?d.detail:'Please check your sign-in details.');
  const next=new URLSearchParams(location.search).get('next')||'/';
  location.assign(next.startsWith('/')&&!next.startsWith('//')&&!next.includes('\\')?next:'/');
 }catch(e){setError(e instanceof Error?e.message:'Sign-in unavailable.');setBusy(false);}}
 return <div className="patient-portal"><header className="patient-header"><a className="brand" href="/login"><span className="brand-mark">p<span>+</span></span><span>practice.</span></a><span className="patient-header-label">ONE PRACTICE. A CONNECTED TEAM.</span><a className="secondary-button" href="/book">Patient sign-in ↗</a></header><main className="staff-login"><div className="eyebrow">WELCOME TO YOUR WORKSPACE</div><h1>Care starts<br/>with your team.</h1><p>Sign in as a doctor, medical admin or nurse. Your account determines what you can access.</p><section className="booking-card"><h2>Staff sign-in</h2>{error&&<div className="booking-error" role="alert">{error}</div>}<form onSubmit={login}><label className="field-label" htmlFor="username">Username</label><input className="form-input" id="username" autoComplete="username" required maxLength={64} value={username} onChange={e=>setUsername(e.target.value)}/><label className="field-label" htmlFor="password">Password</label><input className="form-input" id="password" type="password" autoComplete="current-password" required maxLength={256} value={password} onChange={e=>setPassword(e.target.value)}/><button className="primary-button full-button" disabled={busy}>{busy?'Signing in…':'Open my workspace →'}</button></form><p className="field-hint">Patients use the separate mobile sign-in. Staff accounts are created by the practice operator.</p></section><p className="patient-footer">Fictional demo only · Clinical notes and prescriptions are not enabled.</p></main></div>;
}
