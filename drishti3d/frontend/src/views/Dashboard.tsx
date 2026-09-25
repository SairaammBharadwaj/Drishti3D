import { useCallback, useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { api, type Project, type Capabilities } from '../api'

const statusLabels = { created: 'Draft', processing: 'Processing', done: 'Reconstructed', failed: 'Needs attention' }
function destination(p: Project) {
  if (p.status === 'done') return `/projects/${p.id}`
  if (p.status === 'processing' || p.status === 'failed') return `/projects/${p.id}/demo`
  return `/new?project=${encodeURIComponent(p.id)}`
}

export default function Dashboard() {
  const [projects, setProjects] = useState<Project[]>([])
  const [caps, setCaps] = useState<Capabilities | null>(null)
  const [err, setErr] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)
  const [query, setQuery] = useState('')
  const [filter, setFilter] = useState('all')
  const [deleting, setDeleting] = useState<string | null>(null)
  const load = useCallback(() => {
    setLoading(true); setErr(null)
    api.listProjects().then(setProjects).catch(e => setErr(String(e))).finally(() => setLoading(false))
    api.capabilities().then(setCaps).catch(() => setCaps(null))
  }, [])
  useEffect(load, [load])
  useEffect(() => {
    if (!projects.some(p => p.status === 'processing')) return
    const timer = setInterval(() => { api.listProjects().then(setProjects).catch(() => {}) }, 10000)
    return () => clearInterval(timer)
  }, [projects])
  const remove = async (p: Project) => {
    if (!confirm(`Delete “${p.name}” and all its files? This cannot be undone.`)) return
    setDeleting(p.id)
    try { await api.deleteProject(p.id); load() } catch (e) { setErr(String(e)) } finally { setDeleting(null) }
  }
  const shown = projects.filter(p => (filter === 'all' || p.status === filter) && `${p.name} ${p.description}`.toLowerCase().includes(query.toLowerCase()))
    .sort((a, b) => Date.parse(b.created_at) - Date.parse(a.created_at))
  return <div className="library">
    <div className="page-heading"><div><div className="eyebrow">YOUR SPATIAL WORKSPACE</div><h1>Mission library<span className="muted">.</span></h1><p>Every capture, reconstruction, and question. One place to return to.</p></div><Link className="action primary-action" to="/new">New reconstruction <span aria-hidden="true">+</span></Link></div>
    <div className="library-stats">{[['All missions', projects.length], ['Reconstructed', projects.filter(p => p.status === 'done').length], ['Processing', projects.filter(p => p.status === 'processing').length], ['Needs attention', projects.filter(p => p.status === 'failed').length]].map(([label, value]) => <div key={label}><strong>{loading || err ? '—' : value}</strong><span>{label}</span></div>)}</div>
    <div className="library-tools"><div className="segmented" aria-label="Filter missions">{[['all', 'All missions'], ['done', 'Ready'], ['processing', 'Processing'], ['created', 'Drafts'], ['failed', 'Attention']].map(([value, label]) => <button key={value} aria-pressed={filter === value} onClick={() => setFilter(value)}>{label}</button>)}</div><div className="mission-search"><label className="sr-only" htmlFor="mission-search">Search missions</label><svg viewBox="0 0 24 24" aria-hidden="true"><circle cx="11" cy="11" r="6" /><path d="m16 16 4 4" /></svg><input id="mission-search" type="search" aria-label="Search missions" placeholder="Search missions…" value={query} onChange={e => setQuery(e.target.value)} /></div></div>
    {err && <div className="notebox warn library-message" role="alert"><strong>Could not update the mission library.</strong><p>{err}</p><button onClick={load}>Try again</button></div>}
    {loading ? <><p className="muted" role="status">Loading missions…</p><div className="mission-grid" aria-hidden="true">{[0, 1, 2].map(i => <div key={i} className="loading-card" />)}</div></> : <>
      <p className="eyebrow" role="status">{shown.length} {shown.length === 1 ? 'MISSION' : 'MISSIONS'} {query || filter !== 'all' ? 'MATCHING YOUR FILTERS' : 'IN YOUR LIBRARY'}</p>
      {!shown.length && !err && <div className="empty-state"><span className="outline-cube" aria-hidden="true">◇</span><h2>{projects.length ? 'No matching missions.' : 'Your next perspective starts here.'}</h2><p>{projects.length ? 'Try another name or reset the filters.' : 'Create a mission and bring your first drone capture into the workspace.'}</p>{projects.length ? <button onClick={() => { setQuery(''); setFilter('all') }}>Reset filters</button> : <Link className="action primary-action" to="/new">Create a mission ↗</Link>}</div>}
      <div className="mission-grid">{shown.map(p => <article className="mission-card" key={p.id}><div className="mission-card-top"><span className="mono">MISSION / {p.id.slice(0, 8).toUpperCase()}</span><span className={`badge ${p.status}`}>{statusLabels[p.status]}</span></div><div className="mission-card-body"><h2><Link to={destination(p)}>{p.name}</Link></h2><time className="eyebrow" dateTime={p.created_at}>{new Date(p.created_at).toLocaleDateString(undefined, { day: '2-digit', month: 'short', year: 'numeric' })}</time><p>{p.description || 'No description added.'}</p><div className="mission-inputs"><span className={p.has_video ? 'is-ready' : ''}>{p.has_video ? 'Video uploaded' : 'Awaiting video'}</span><span className={p.has_telemetry ? 'is-ready' : ''}>{p.has_telemetry ? 'Telemetry attached' : 'Video only'}</span></div><div className="mission-card-footer"><Link to={destination(p)}>{p.status === 'done' ? 'Open workspace' : p.status === 'processing' ? 'View progress' : p.status === 'failed' ? 'Review mission' : 'Continue setup'} <span aria-hidden="true">→</span></Link><button className="mission-delete" disabled={deleting === p.id || p.status === 'processing'} onClick={() => remove(p)} aria-label={`Delete ${p.name}`}>{deleting === p.id ? 'Deleting…' : 'Delete'}</button></div><div className="mission-secondary">{p.has_video && <Link to={`/projects/${p.id}/demo`}>Presentation</Link>}{p.status === 'done' && <Link to={`/projects/${p.id}/report`}>Quality report</Link>}</div></div></article>)}</div>
    </>}
    <details className="capability-details"><summary>Processing capabilities <span className="muted">/ {caps ? 'detected on this server' : 'unavailable'}</span></summary>{caps ? <><div className="row"><Cap ok={caps.engines.opencv_sfm} label="OpenCV reconstruction" /><Cap ok={caps.engines.colmap} label="COLMAP" /><Cap ok={caps.optional.mesh_open3d} label="Mesh generation" /><Cap ok={caps.optional.las_export} label="LAS export" />{caps.ai_backends.map(a => <Cap key={a.name} ok={a.available} label={a.name} />)}</div><p>Installed components are shown here. Their availability does not establish the accuracy of a reconstruction.</p></> : <p>Connect to the backend and refresh to check available processing components.</p>}</details>
  </div>
}
function Cap({ ok, label }: { ok: boolean; label: string }) { return <span className="pill" style={{ color: ok ? 'var(--green)' : 'var(--muted)' }}>{ok ? '●' : '○'} {label} · {ok ? 'available' : 'not installed'}</span> }
