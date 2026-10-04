import { useEffect, useState } from 'react'
import { api, type AccuracyBlock, type AccuracyReport } from './api'

// Every block says whether it is independent. Residuals at the GCPs that
// fitted the correction, and leave-one-out over them, are never presented as
// the model's accuracy (drishti_recon.accuracy).
const BLOCKS: { key: 'raw' | 'checkpoints' | 'leave_one_out' | 'fit_residuals'; title: string }[] = [
  { key: 'checkpoints', title: 'Checkpoints (after correction)' },
  { key: 'raw', title: 'As reconstructed' },
  { key: 'leave_one_out', title: 'Leave-one-out over GCPs' },
  { key: 'fit_residuals', title: 'Fit residuals at GCPs' },
]

const m = (v: number | undefined) => (v == null ? '—' : `${v.toFixed(3)} m`)

export default function AccuracyPanel({ projectId }: { projectId: string }) {
  const [rep, setRep] = useState<AccuracyReport | null>(null)
  const [state, setState] = useState<'loading' | 'none' | 'ok'>('loading')
  const [file, setFile] = useState<File | null>(null)
  const [source, setSource] = useState('')
  const [datum, setDatum] = useState<'ellipsoidal' | 'msl'>('ellipsoidal')
  const [err, setErr] = useState<string | null>(null)

  useEffect(() => {
    setState('loading'); setRep(null)
    api.accuracy(projectId).then((r) => { setRep(r); setState('ok') }).catch(() => setState('none'))
  }, [projectId])

  const upload = async () => {
    if (!file || !source.trim()) return
    setErr(null)
    try {
      setRep(await api.uploadCheckpoints(projectId, file, source.trim(), datum)); setState('ok')
    } catch (e) { setErr(String(e)) }
  }

  return (
    <div className="accuracy-panel">
      {state === 'loading' && <div className="muted">Loading…</div>}
      {state === 'none' && <p className="muted">No surveyed checkpoints for this mission. Absolute accuracy is not established; GNSS alignment residuals are not accuracy.</p>}
      {rep && (
        <>
          {rep.stale && <div className="notebox warn" style={{ fontSize: 12 }}>The reconstruction changed after this report: re-run it.</div>}
          <p><strong>{rep.headline.text}</strong></p>
          {rep.headline.warning && <div className="notebox warn" style={{ fontSize: 12 }}>{rep.headline.warning}</div>}
          <p className="muted" style={{ fontSize: 12 }}>
            Truth: {rep.truth_source ?? 'unstated'} · {rep.n_gcp} GCP · {rep.n_check} checkpoint
            · correction: {rep.correction.kind}{rep.correction.note ? ` (${rep.correction.note})` : ''}
          </p>
          {!rep.asprs.sample_sufficient && <p className="warn" style={{ fontSize: 12 }}>⚠ {rep.asprs.note}</p>}
          {BLOCKS.map(({ key, title }) => {
            const b = rep[key] as AccuracyBlock | undefined
            if (!b || !b.stats.rmse_m) return null
            return (
              <div key={key} className="accuracy-block">
                <div className="spread">
                  <span>{title}</span>
                  <span className={b.independent ? 'badge ok' : 'badge warn'}>{b.independent ? 'independent' : 'NOT independent'}</span>
                </div>
                <div className="kv"><span className="k">RMSE H / V / 3-D</span><span className="mono">{m(b.stats.rmse_m.horizontal)} / {m(b.stats.rmse_m.u)} / {m(b.stats.rmse_m['3d'])}</span></div>
                <div className="kv"><span className="k">CE90 / LE90</span><span className="mono">{m(b.stats.ce90_m)} / {m(b.stats.le90_m)}</span></div>
                <div className="muted" style={{ fontSize: 11 }}>{b.label} · n = {b.stats.n}</div>
              </div>
            )
          })}
        </>
      )}
      <details style={{ marginTop: 8 }}>
        <summary>Score against surveyed points</summary>
        <p className="muted" style={{ fontSize: 12 }}>
          CSV columns: <code>id, role</code> (gcp or check), <code>model_e, model_n, model_u</code> (the point picked in this viewer),
          and the survey as <code>lat, lon, h</code>, <code>easting, northing, h, epsg</code> or <code>e, n, u</code>.
          Hold points back as checkpoints: only they give an independent figure.
        </p>
        <input type="file" accept=".csv" aria-label="Checkpoint CSV" onChange={(e) => setFile(e.target.files?.[0] ?? null)} />
        <input type="text" placeholder="Truth source (e.g. DGPS survey, 2026-10-02)" value={source}
          onChange={(e) => setSource(e.target.value)} style={{ width: '100%', marginTop: 6 }} />
        <label className="checkline">Survey heights
          <select value={datum} onChange={(e) => setDatum(e.target.value as 'ellipsoidal' | 'msl')}>
            <option value="ellipsoidal">WGS84 ellipsoidal</option>
            <option value="msl">above sea level</option>
          </select>
        </label>
        <button className="primary" disabled={!file || !source.trim()} onClick={upload}>Score</button>
        {err && <div className="notebox warn" style={{ marginTop: 6, fontSize: 12 }}>{err}</div>}
      </details>
    </div>
  )
}
