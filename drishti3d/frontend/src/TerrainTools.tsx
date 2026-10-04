import { useState } from 'react'
import {
  api, type TerrainTool, type Vec3, type VolumeResult, type ProfileResult,
  type SlopeResult, type LosResult, type TerrainCommon,
} from './api'

// Volume and profile read the mean height per cell, line of sight the top
// surface, all from observed points only (drishti_recon.terrain). An empty
// cell is unknown: below 80% observed the answer is a refusal, and a sight
// line over unobserved cells is "unknown", never "visible".
const TOOLS: { key: TerrainTool; label: string; min: number; hint: string }[] = [
  { key: 'volume', label: 'Volume', min: 3, hint: 'Click round the pile; the base is a plane through the edge.' },
  { key: 'profile', label: 'Profile', min: 2, hint: 'Click the two ends of the section line.' },
  { key: 'slope', label: 'Slope', min: 3, hint: 'Click round the area to grade.' },
  { key: 'los', label: 'Line of sight', min: 2, hint: 'Click the observer, then the target.' },
]

type Result = VolumeResult | ProfileResult | SlopeResult | LosResult

interface Props {
  projectId: string
  tool: TerrainTool | null
  points: Vec3[]
  available: boolean
  onStart: (t: TerrainTool) => void
  onClear: () => void
  onCancel: () => void
}

export default function TerrainTools({ projectId, tool, points, available, onStart, onClear, onCancel }: Props) {
  const [result, setResult] = useState<{ tool: TerrainTool; r: Result } | null>(null)
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState<string | null>(null)
  const [base, setBase] = useState<'edge' | 'lowest'>('edge')
  const [observerH, setObserverH] = useState(1.7)
  const spec = TOOLS.find((t) => t.key === tool)

  if (!available) return <div className="muted">Needs the mission’s rasters: it is not georeferenced, or they have not been built.</div>

  const run = async () => {
    if (!tool) return
    setBusy(true); setErr(null)
    try {
      const body = tool === 'volume' ? { polygon: points, base }
        : tool === 'slope' ? { polygon: points }
        : tool === 'profile' ? { a: points[0], b: points[points.length - 1] }
        // Picks are real cloud points: stand on them, rather than on the DSM
        // cell under them, which may be empty or hold a taller point.
        : { observer: points[0], target: points[points.length - 1], observer_height_m: observerH, use_point_heights: true }
      setResult({ tool, r: await api.terrain<Result & TerrainCommon>(projectId, tool, body) })
      onCancel()
    } catch (e) { setErr(String(e)) } finally { setBusy(false) }
  }

  return (
    <div className="terrain-tools">
      <div className="row">
        {TOOLS.map((t) => (
          <button key={t.key} className={tool === t.key ? 'active' : ''} onClick={() => { setResult(null); onStart(t.key) }}>{t.label}</button>
        ))}
      </div>
      {spec && (
        <div className="notebox" style={{ marginTop: 8 }}>
          <div><strong>{spec.label}</strong> — {spec.hint}</div>
          <div className="muted">picked {points.length} / min {spec.min}</div>
          {tool === 'volume' && (
            <label className="checkline">Base
              <select value={base} onChange={(e) => setBase(e.target.value as 'edge' | 'lowest')}>
                <option value="edge">plane through the edge</option>
                <option value="lowest">lowest point inside</option>
              </select>
            </label>
          )}
          {tool === 'los' && (
            <label className="checkline">Observer eye height (m)
              <input type="number" min={0} max={500} step={0.1} value={observerH}
                onChange={(e) => setObserverH(+e.target.value)} style={{ width: 70 }} />
            </label>
          )}
          <div className="row" style={{ marginTop: 6 }}>
            <button className="primary" disabled={busy || points.length < spec.min} onClick={run}>{busy ? 'Computing…' : 'Compute'}</button>
            <button onClick={onClear}>Clear</button>
            <button onClick={onCancel}>Cancel</button>
          </div>
        </div>
      )}
      {err && <div className="notebox warn" style={{ marginTop: 8, fontSize: 12 }}>{err}</div>}
      {result && <ResultCard tool={result.tool} r={result.r} />}
    </div>
  )
}

const m = (v: number | null | undefined, d = 2, u = 'm') => (v == null ? '—' : `${v.toFixed(d)} ${u}`)

function ResultCard({ tool, r }: { tool: TerrainTool; r: Result }) {
  if (r.status === 'refused') {
    return (
      <div className="notebox warn terrain-result" role="status">
        <strong>Refused</strong>
        <p>{r.reason}</p>
        {r.coverage != null && <p className="muted">Observed: {Math.round(r.coverage * 100)}%</p>}
      </div>
    )
  }
  const footer = (
    <p className="muted terrain-meta">
      {r.surface} · {r.cell_size_m} m cells · {r.crs}
      {r.coverage != null && ` · ${Math.round(r.coverage * 100)}% observed`}
    </p>
  )
  if (tool === 'volume') {
    const v = r as VolumeResult
    return (
      <div className="notebox terrain-result">
        <div className="spread"><strong>Volume</strong><span className="mono">{m(v.net_m3, 1, 'm³')}</span></div>
        <div className="kv"><span className="k">Cut / fill</span><span className="mono">{m(v.cut_m3, 1, 'm³')} / {m(v.fill_m3, 1, 'm³')}</span></div>
        <div className="kv"><span className="k">Area</span><span className="mono">{m(v.area_m2, 1, 'm²')}</span></div>
        <div className="kv"><span className="k">±1σ (independent – correlated)</span>
          <span className="mono">{m(v.sigma_m3?.independent_cells, 1, '')} – {m(v.sigma_m3?.fully_correlated_bound, 1, 'm³')}</span></div>
        <div className="kv"><span className="k">Base</span><span>{v.base?.kind === 'edge' ? `edge plane, rms ${m(v.base?.edge_rms_m, 2)}` : 'lowest point'}</span></div>
        {v.unobserved_note && <p className="warn" style={{ fontSize: 12 }}>⚠ {v.unobserved_note}</p>}
        <p className="muted" style={{ fontSize: 12 }}>{v.sigma_m3?.note}</p>
        {footer}
      </div>
    )
  }
  if (tool === 'profile') {
    const p = r as ProfileResult
    return (
      <div className="notebox terrain-result">
        <div className="spread"><strong>Profile</strong><span className="mono">{m(p.length_m, 1)}</span></div>
        <ProfileChart samples={p.samples ?? []} />
        <div className="kv"><span className="k">Rise / grade</span><span className="mono">{m(p.net_rise_m)} / {p.mean_grade_pct?.toFixed(1)}%</span></div>
        <div className="kv"><span className="k">Min / max</span><span className="mono">{m(p.min_z)} / {m(p.max_z)}</span></div>
        {!!p.gaps && <p className="warn" style={{ fontSize: 12 }}>⚠ {p.gaps} unobserved sample(s): shown as breaks, not interpolated</p>}
        {footer}
      </div>
    )
  }
  if (tool === 'slope') {
    const s = r as SlopeResult
    return (
      <div className="notebox terrain-result">
        <div className="spread"><strong>Slope</strong><span className="mono">{m(s.median_deg, 1, '°')} median</span></div>
        <div className="kv"><span className="k">Mean / 90th / max</span><span className="mono">{m(s.mean_deg, 1, '°')} / {m(s.p90_deg, 1, '°')} / {m(s.max_deg, 1, '°')}</span></div>
        {footer}
      </div>
    )
  }
  const l = r as LosResult
  const label = { visible: 'Visible', blocked: 'Blocked', unknown: 'Unknown' }[l.result ?? 'unknown']
  return (
    <div className={`notebox terrain-result ${l.result === 'unknown' ? 'warn' : ''}`}>
      <div className="spread"><strong>Line of sight</strong><span className={`los-${l.result}`}>{label}</span></div>
      <div className="kv"><span className="k">Length</span><span className="mono">{m(l.length_m, 1)}</span></div>
      {l.obstruction && <div className="kv"><span className="k">First obstruction</span><span className="mono">{m(l.obstruction.distance_m, 1)} along, {m(-l.obstruction.clearance_m, 2)} above the ray</span></div>}
      {l.min_clearance_m != null && <div className="kv"><span className="k">Least clearance</span><span className="mono">{m(l.min_clearance_m)}</span></div>}
      {l.result === 'unknown' && <p style={{ fontSize: 12 }}>{l.reason}. Not called visible: the ray passes cells nobody observed or within 2σ of the surface.</p>}
      {footer}
    </div>
  )
}

function ProfileChart({ samples }: { samples: { d_m: number; z: number | null }[] }) {
  const have = samples.filter((s) => s.z != null) as { d_m: number; z: number }[]
  if (have.length < 2) return null
  const W = 260, H = 90, pad = 4
  const d1 = samples[samples.length - 1].d_m || 1
  const zs = have.map((s) => s.z)
  const z0 = Math.min(...zs), z1 = Math.max(...zs)
  const x = (d: number) => pad + (d / d1) * (W - 2 * pad)
  const y = (z: number) => H - pad - ((z - z0) / Math.max(z1 - z0, 1e-6)) * (H - 2 * pad)
  // Break the line at gaps: an unobserved cell is not drawn across.
  let path = '', pen = false
  for (const s of samples) {
    if (s.z == null) { pen = false; continue }
    path += `${pen ? 'L' : 'M'}${x(s.d_m).toFixed(1)},${y(s.z).toFixed(1)} `
    pen = true
  }
  return (
    <svg className="profile-chart" viewBox={`0 0 ${W} ${H}`} role="img"
      aria-label={`Height profile, ${z0.toFixed(1)} to ${z1.toFixed(1)} m`}>
      <path d={path} fill="none" stroke="currentColor" strokeWidth={1.5} />
    </svg>
  )
}
