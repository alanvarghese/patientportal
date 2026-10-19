'use client';
import { createContext, useContext, useEffect, useState } from 'react';
import { usePathname } from 'next/navigation';

export type StaffUser = { id:string; name:string; role:'doctor'|'medical_admin'|'nurse'; practitioner_id:string|null };
const StaffContext=createContext<StaffUser|null>(null);
export const useStaff=()=>useContext(StaffContext);
export const roleName=(role:string)=>({doctor:'Doctor',medical_admin:'Medical Admin',nurse:'Nurse'}[role]||role);

export function StaffAccess({children}:{children:React.ReactNode}) {
 const path=usePathname();
 const [ready,setReady]=useState(false),[user,setUser]=useState<StaffUser|null>(null),[error,setError]=useState('');
 useEffect(()=>{
  const controller=new AbortController();setReady(false);setError('');
  const publicPage=path==='/login'||path==='/book'||(path==='/consultation'&&(location.hash.startsWith('#invite=')||new URLSearchParams(location.search).get('role')==='patient'));
  if(publicPage){setUser(null);setReady(true);return()=>controller.abort();}
  fetch('/api/staff/me',{cache:'no-store',signal:controller.signal}).then(async r=>{
   if(r.status===401){location.replace('/login?next='+encodeURIComponent(location.pathname+location.search));return;}
   if(!r.ok)throw new Error('Staff sign-in is temporarily unavailable. Please refresh.');
   const result=await r.json();if(!controller.signal.aborted){setUser(result);setReady(true);}
  }).catch(e=>{if(!controller.signal.aborted)setError(e.message);});
  return()=>controller.abort();
 },[path]);
 if(error)return <main className="empty-state" role="alert"><h2>We couldn’t restore your session.</h2><p>{error}</p><a className="secondary-button" href="/login">Go to sign-in</a></main>;
 if(!ready)return <main className="empty-state" role="status"><span className="loader"/><p>Opening your workspace…</p></main>;
 return <StaffContext.Provider value={user}>{children}</StaffContext.Provider>;
}
