import { useEffect, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { api, type Project, type Capabilities } from '../api'

export default function Dashboard() {
  const [projects, setProjects] = useState<Project[]>([])
  const [caps, setCaps] = useState<Capabilities | null>(null)
  const [err, setErr] = useState<string | null>(null)
  const nav = useNavigate()

  const load = () => {
    api.listProjects().then(setProjects).catch((e) => setErr(String(e)))
    api.capabilities().then(setCaps).catch(() => {})
  }
  useEffect(load, [])

  const open = (p: Project) => {
    if (p.status === 'done') nav(`/projects/${p.id}`)
    else if (p.status === 'processing') nav(`/projects/${p.id}/monitor`)
  }

  const remove = async (e: React.MouseEvent, id: string) => {
    e.stopPropagation()
    if (!confirm('Delete this mission and all its files?')) return
    await api.deleteProject(id)
    load()
  }

  return (
    <div className="container">
      <div className="spread">
        <div>
          <h1>Mission Dashboard</h1>
          <div className="muted">Reconstruct and measure a scene from one drone pass.</div>
        </div>
        <Link to="/new"><button className="primary">+ New reconstruction</button></Link>
      </div>

      {caps && (
        <div className="card" style={{ marginTop: 14 }}>
          <h3>System capabilities (detected)</h3>
          <div className="row">
            <Cap ok={caps.engines.opencv_sfm} label="OpenCV SfM (verified path)" />
            <Cap ok={caps.engines.colmap} label="COLMAP" />
            <Cap ok={caps.optional.mesh_open3d} label="Mesh (Open3D)" />
            <Cap ok={caps.optional.las_export} label="LAS export" />
            <Cap ok={caps.optional.torch} label="Torch (masking)" />
            {caps.ai_backends.map((a) => (
              <Cap key={a.name} ok={a.available} label={`AI: ${a.name}`} />
            ))}
          </div>
          <div className="muted" style={{ marginTop: 6, fontSize: 12 }}>
            Availability is probed live — nothing is claimed that is not installed.
          </div>
        </div>
      )}

      {err && <div className="notebox warn" style={{ marginTop: 14 }}>{err}</div>}

      <h2>Missions</h2>
      {projects.length === 0 && <div className="muted">No missions yet. Create one to begin.</div>}
      <div className="grid cols">
        {projects.map((p) => (
          <div key={p.id} className="card" style={{ cursor: p.status !== 'created' ? 'pointer' : 'default' }}
               onClick={() => open(p)}>
            <div className="spread">
              <strong>{p.name}</strong>
              <span className={`badge ${p.status}`}>{p.status}</span>
            </div>
            <div className="muted" style={{ fontSize: 12, margin: '6px 0' }}>
              {new Date(p.created_at).toLocaleString()}
            </div>
            {p.description && <div style={{ fontSize: 13 }}>{p.description}</div>}
            <div className="row" style={{ marginTop: 10 }}>
              <span className="pill">{p.has_video ? 'video ✓' : 'no video'}</span>
              <span className="pill">{p.has_telemetry ? 'telemetry ✓' : 'no telemetry'}</span>
            </div>
            <div className="row" style={{ marginTop: 10 }}>
              {p.status === 'done' && <Link to={`/projects/${p.id}`} onClick={(e) => e.stopPropagation()}>Open workspace →</Link>}
              {p.status === 'done' && <Link to={`/projects/${p.id}/report`} onClick={(e) => e.stopPropagation()}>Report</Link>}
              {p.status === 'created' && <Link to="/new" onClick={(e) => e.stopPropagation()}>Continue setup</Link>}
              <button className="danger" style={{ marginLeft: 'auto' }} onClick={(e) => remove(e, p.id)}>Delete</button>
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}

function Cap({ ok, label }: { ok: boolean; label: string }) {
  return (
    <span className="pill" style={{ color: ok ? 'var(--green)' : 'var(--muted)', borderColor: ok ? '#1f5a37' : 'var(--border)' }}>
      {ok ? '●' : '○'} {label}
    </span>
  )
}
