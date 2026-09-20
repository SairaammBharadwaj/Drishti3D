import { useEffect, useRef, useState } from 'react'
import { Link, useParams, useSearchParams } from 'react-router-dom'
import ReconstructionNotice from '../ReconstructionNotice'
import { api, type QualityReport } from '../api'

interface Event { status: string; stage: string; progress: number; message: string; error?: string | null; warnings?: string[] }

const STAGES = [
  'ingestion', 'telemetry', 'frames', 'quality', 'sync', 'keyframes',
  'masking', 'sfm', 'densify', 'georegistration', 'fusion', 'mesh', 'report', 'exports',
]

export default function Monitor() {
  const { id } = useParams()
  const [sp] = useSearchParams()
  const jobId = sp.get('job') ?? ''
  const [ev, setEv] = useState<Event>({ status: 'queued', stage: '', progress: 0, message: 'queued' })
  const [warnings, setWarnings] = useState<string[]>([])
  const [quality, setQuality] = useState<QualityReport | null>(null)
  useEffect(() => {
    if (ev.status === 'done' && id) api.quality(id).then(setQuality).catch(() => {})
  }, [ev.status, id])
  const [elapsed, setElapsed] = useState(0)
  const start = useRef(Date.now())

  useEffect(() => {
    if (!jobId) return
    const t = setInterval(() => setElapsed((Date.now() - start.current) / 1000), 250)
    const es = new EventSource(api.eventsUrl(jobId))
    es.onmessage = (m) => {
      const data = JSON.parse(m.data) as Event
      setEv(data)
      if (data.warnings?.length) setWarnings(data.warnings)
      if (data.status === 'done' || data.status === 'failed') es.close()
    }
    es.onerror = () => {
      // SSE may drop; fall back to a poll to capture terminal state.
      api.getJob(jobId).then((j) => setEv(j)).catch(() => {})
    }
    return () => { es.close(); clearInterval(t) }
  }, [jobId])

  const curIdx = STAGES.indexOf(ev.stage)

  return (
    <div className="container" style={{ maxWidth: 820 }}>
      <div className="spread">
        <h1>Processing Monitor</h1>
        <span className={`badge ${ev.status === 'running' ? 'processing' : ev.status}`}>{ev.status}</span>
      </div>

      <div className="card stack" style={{ marginTop: 14 }}>
        <div className="spread">
          <div><strong>{ev.stage || '—'}</strong> <span className="muted">{ev.message}</span></div>
          <div className="mono">{(ev.progress * 100).toFixed(0)}% · {elapsed.toFixed(1)}s</div>
        </div>
        <div className="progress-track"><div className="progress-fill" style={{ width: `${ev.progress * 100}%` }} /></div>

        <div className="timeline" style={{ marginTop: 8 }}>
          {STAGES.map((s, i) => (
            <div key={s} className="pill" style={{
              fontSize: 11,
              color: i < curIdx || ev.status === 'done' ? 'var(--green)' : i === curIdx ? 'var(--accent)' : 'var(--muted)',
              borderColor: i === curIdx ? 'var(--accent)' : 'var(--border)',
            }}>{s}</div>
          ))}
        </div>
      </div>

      {ev.status === 'failed' && (
        <div className="notebox warn" style={{ marginTop: 14 }}>
          <strong className="err">Reconstruction failed.</strong>
          <div className="mono" style={{ marginTop: 6 }}>{ev.error ?? 'unknown error'}</div>
          <div style={{ marginTop: 8 }}><Link to="/new">Try again →</Link></div>
        </div>
      )}

      {warnings.length > 0 && (
        <div className="card" style={{ marginTop: 14 }}>
          <h3>Warnings</h3>
          <ul>{warnings.map((w, i) => <li key={i} className="warn">{w}</li>)}</ul>
        </div>
      )}

      {ev.status === 'done' && (
        <div className="notebox" style={{ marginTop: 14 }}>
          <strong className="badge done">Processing complete</strong>
          <ReconstructionNotice quality={quality} />
          <div className="row" style={{ marginTop: 10 }}>
            <Link to={`/projects/${id}/demo`}><button className="primary">View 3D & metrics →</button></Link>
            <Link to={`/projects/${id}`}><button>Open analysis workspace →</button></Link>
            <Link to={`/projects/${id}/report`}><button>View report</button></Link>
          </div>
        </div>
      )}
    </div>
  )
}
