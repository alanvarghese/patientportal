'use client';
import { Icon } from './icons';
import { useStaff,roleName } from './staff-access';

export function WorkspaceSidebar({ active }: { active: 'today' | 'patients' | 'registration' }) {
  const user=useStaff();
  async function logout(){const r=await fetch('/api/staff/logout',{method:'POST',headers:{'X-Practice-Client':'portal'}});if(r.ok)location.assign('/login');}
  return <aside className="sidebar">
    <a className="brand" href="/" aria-label="Practice home"><span className="brand-mark">p<span>+</span></span><span>practice<span className="brand-dot">.</span></span></a>
    <div className="practice-label"><span className="tiny-dot" /> KERALA TELEMEDICINE</div>
    <div className="nav-label">WORKSPACE</div>
    <nav aria-label="Workspace">
      <a className={`nav-item ${active === 'today' ? 'active' : ''}`} href="/" aria-label="Today" aria-current={active === 'today' ? 'page' : undefined}><Icon name="grid" />Today{active === 'today' && <span className="nav-indicator" />}</a>
      <a className={`nav-item ${active === 'patients' ? 'active' : ''}`} href="/patients" aria-label="Patient records" aria-current={active === 'patients' ? 'page' : undefined}><Icon name="patients" />Patient records{active === 'patients' && <span className="nav-indicator" />}</a>
      {user?.role==='medical_admin'&&<a className={`nav-item ${active==='registration'?'active':''}`} href="/registration"><Icon name="patients"/>Registration & booking</a>}
    </nav>
    <div className="roadmap"><span className="nav-label">BUILDING TOGETHER</span><div><Icon name="video" /><span>Consultations<small>Video calls available</small></span></div></div>
    <div className="sidebar-note"><span className="note-icon"><Icon name="heart" size={18} /></span><h3>More time for care.</h3><p>A calmer workspace for your everyday practice.</p><span className="section-tag">TEAM WORKSPACE · DEMO</span></div>
    <div className="profile"><span className="doctor-avatar">{user?.role==='doctor'?'DR':user?.role==='nurse'?'RN':'MA'}</span><div><strong>{user?.name||'Staff workspace'}</strong><small>{roleName(user?.role||'staff')} · <button className="text-button" onClick={()=>void logout()}>Sign out</button></small></div></div>
  </aside>;
}
