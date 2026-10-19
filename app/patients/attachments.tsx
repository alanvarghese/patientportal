'use client';

import { FormEvent, useEffect, useRef, useState } from 'react';
import { Icon } from '../components/icons';

type Attachment = { id: string; filename: string; title: string; mime_type: string; size_bytes: number; uploaded_at: string; uploaded_by: string };
type Result = { attachments: Attachment[]; total: number };
function sizeLabel(size: number) { return size < 1024 * 1024 ? `${Math.max(1, Math.round(size / 1024))} KB` : `${(size / (1024 * 1024)).toFixed(1)} MB`; }
function uploadedDate(value: string) { return new Intl.DateTimeFormat('en-IN', { day:'numeric',month:'short',year:'numeric',timeZone:'Asia/Kolkata' }).format(new Date(value)); }

export function Attachments({ patientId, patientName }: { patientId: string; patientName: string }) {
  const [data, setData] = useState<Result | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const [file, setFile] = useState<File | null>(null);
  const [title, setTitle] = useState('');
  const [busy, setBusy] = useState(false);
  const [offset, setOffset] = useState(0);
  const [refresh, setRefresh] = useState(0);
  const [preview, setPreview] = useState<Attachment | null>(null);
  const inputRef = useRef<HTMLInputElement>(null);
  const previewRef = useRef<HTMLDivElement>(null);
  const base = `/api/records/patients/${encodeURIComponent(patientId)}/attachments`;
  useEffect(() => {
    const controller = new AbortController(); setLoading(true); setError('');
    fetch(`${base}?offset=${offset}`, {signal:controller.signal,cache:'no-store'}).then(async response => { if(!response.ok) throw new Error('Attachments could not be loaded. Please try again.'); return response.json(); }).then(result=>{if(!controller.signal.aborted)setData(result);}).catch(e=>{if(!controller.signal.aborted)setError(e.message);}).finally(()=>{if(!controller.signal.aborted)setLoading(false);});
    return ()=>controller.abort();
  },[base, offset, refresh]);
  useEffect(()=>{ if(preview)previewRef.current?.scrollIntoView({block:'nearest'}); },[preview]);
  function choose(next: File | null) {
    setNotice(''); setError(''); setFile(null);
    if (!next) return;
    if (!/\.(pdf|jpe?g|png)$/i.test(next.name)) { setError('Choose a PDF, JPEG or PNG file.'); return; }
    if (!next.size || next.size > 10 * 1024 * 1024) { setError('Choose a non-empty file of 10 MB or smaller.'); return; }
    setFile(next);
  }
  async function upload(event: FormEvent) {
    event.preventDefault(); if(!file)return;
    setBusy(true);setError('');setNotice('');
    try {
      const response = await fetch(base, {method:'POST',headers:{'Content-Type':file.type||'application/octet-stream','X-Practice-Client':'portal','X-File-Name':encodeURIComponent(file.name),'X-Attachment-Title':encodeURIComponent(title.trim())},body:file});
      const result = await response.json().catch(()=>({}));
      if(!response.ok)throw new Error(typeof result.detail === 'string' ? result.detail : 'The file could not be uploaded. Please try again.');
      setNotice(result.already_attached?'This file is already attached to this patient.':'Attachment saved to this patient record.');
      setFile(null);setTitle('');if(inputRef.current)inputRef.current.value='';setOffset(0);setRefresh(n=>n+1);
    } catch(e) { setError(e instanceof Error?e.message:'Upload failed. Please try again.'); }
    finally {setBusy(false);}
  }
  function url(item: Attachment, download=false){return `${base}/${encodeURIComponent(item.id)}/content${download?'?download=true':''}`;}
  return <section id="record-attachments" role="tabpanel" aria-labelledby="attachments-tab">
    <p className="history-description">Reports and images attached to {patientName}. Use fictional documents only in this demo.</p>
    <form className="attachment-upload" onSubmit={upload}>
      <div className="attachment-upload-heading"><span className="attachment-symbol">＋</span><div><h3>Add an attachment</h3><p>PDF, JPEG or PNG · Up to 10 MB per file</p></div></div>
      <label className="field-label" htmlFor="attachment-file">Choose file</label><input className="attachment-file-input" id="attachment-file" ref={inputRef} type="file" accept=".pdf,.jpg,.jpeg,.png,application/pdf,image/jpeg,image/png" disabled={busy} onChange={e=>choose(e.target.files?.[0]||null)}/>
      {file&&<p className="chosen-file">{file.name}<span>{sizeLabel(file.size)}</span></p>}
      <label className="field-label" htmlFor="attachment-title">Title <span>(optional)</span></label><input className="form-input" id="attachment-title" value={title} disabled={busy} maxLength={120} onChange={e=>setTitle(e.target.value)} placeholder="For example, referral letter or previous report"/>
      <button className="primary-button attachment-upload-button" disabled={!file||busy}>{busy?'Validating & saving…':'Upload attachment'}{!busy&&<Icon name="arrow" size={15}/>}</button>
    </form>
    {error&&<div className="booking-error attachment-message" role="alert">{error}</div>}
    {notice&&<div className="notice attachment-message" role="status">{notice}</div>}
    <div className="attachment-list-heading"><h3>Saved attachments {data&&<span>{data.total}</span>}</h3><button className="text-button" disabled={loading||busy} onClick={()=>setRefresh(n=>n+1)}>Refresh</button></div>
    {loading?<div className="empty-state" role="status"><span className="loader"/><p>Loading attachments…</p></div>:!data?.attachments.length?<div className="attachment-empty"><Icon name="patients" size={25}/><strong>No attachments yet</strong><p>Add a report or an image to keep it with this patient’s record.</p></div>:<div className="attachment-list">{data.attachments.map(item=><article className="attachment-item" key={item.id}><span className={`file-type ${item.mime_type==='application/pdf'?'pdf':'image'}`}>{item.mime_type==='application/pdf'?'PDF':'IMG'}</span><div className="attachment-item-content"><h4>{item.title}</h4><p>{item.filename}</p><small>{sizeLabel(item.size_bytes)} · {uploadedDate(item.uploaded_at)} · {item.uploaded_by}</small><div className="attachment-actions"><button className="text-button" onClick={()=>setPreview(item)}>Preview</button><a href={url(item)} target="_blank" rel="noopener noreferrer">Open ↗</a><a href={url(item,true)}>Download ↓</a></div></div></article>)}</div>}
    {data&&data.total>10&&<div className="history-pagination"><button className="secondary-button" disabled={offset===0||loading} onClick={()=>setOffset(n=>Math.max(0,n-10))}>← Newer</button><span>{offset+1}–{Math.min(offset+10,data.total)} of {data.total}</span><button className="secondary-button" disabled={offset+10>=data.total||loading} onClick={()=>setOffset(n=>n+10)}>Older →</button></div>}
    {preview&&<div className="attachment-preview" ref={previewRef}><div className="attachment-preview-heading"><h3>{preview.title}</h3><button aria-label="Close attachment preview" onClick={()=>setPreview(null)}><Icon name="close" size={17}/></button></div>{preview.mime_type==='application/pdf'?<><img src={`${base}/${encodeURIComponent(preview.id)}/preview`} alt={`First page of ${preview.title}`} onLoad={()=>previewRef.current?.scrollIntoView({block:'nearest'})} onError={()=>setError('This PDF preview is unavailable. You can still open or download the file.')}/><p>First page preview · <a href={url(preview)} target="_blank" rel="noopener noreferrer">Open the full PDF ↗</a> or download it above.</p></>:<img src={url(preview)} alt={preview.title} onLoad={()=>previewRef.current?.scrollIntoView({block:'nearest'})} onError={()=>setError('This image could not be displayed. Try opening or downloading it.')}/>}</div>}
  </section>;
}
