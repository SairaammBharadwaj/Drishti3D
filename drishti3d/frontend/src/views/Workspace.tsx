import { useCallback, useEffect, useMemo, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import {
  api, PROVENANCE, enuToLatLon,
  type ModelPayload, type QualityReport, type Trajectory,
  type Measurement, type MeasurementKind, type FrameMetric, type Keyframe, type Vec3,
} from '../api'
import ReconstructionNotice from '../ReconstructionNotice'
import ToleranceLens from '../ToleranceLens'
import PointCloudViewer from '../PointCloudViewer'
import TrajectoryMap from '../TrajectoryMap'

const KIND_MIN: Record<MeasurementKind, number> = { point: 1, distance: 2, height: 2, area: 3 }

export default function Workspace() {
  const { id = '' } = useParams()
  const [model, setModel] = useState<ModelPayload | null>(null)
  // The capped preview paints immediately; the full cloud is fetched on
  // request because it is tens of megabytes and most sessions never need it.
  const [full, setFull] = useState<Awaited<ReturnType<typeof api.modelFull>> | null>(null)
  const [fullState, setFullState] = useState<'idle' | 'loading' | 'error'>('idle')
  const [fullProgress, setFullProgress] = useState(0)
  const [quality, setQuality] = useState<QualityReport | null>(null)
  const [traj, setTraj] = useState<Trajectory | null>(null)
  const [metrics, setMetrics] = useState<FrameMetric[]>([])
  const [keyframes, setKeyframes] = useState<Keyframe[]>([])
  const [measurements, setMeasurements] = useState<Measurement[]>([])
  const [exps, setExps] = useState<Record<string, string>>({})
  const [err, setErr] = useState<string | null>(null)

  const [colorMode, setColorMode] = useState<'true' | 'provenance'>('provenance')
  const [splat, setSplat] = useState(false)
  const [pointSize, setPointSize] = useState(1)
  const [visible, setVisible] = useState<Set<number>>(new Set([0, 1, 2, 3, 4]))
  const [kind, setKind] = useState<MeasurementKind | null>(null)
  const [pts, setPts] = useState<Vec3[]>([])
  const [hover, setHover] = useState<Vec3 | null>(null)
  const [allowInferred, setAllowInferred] = useState(false)
  const [lastResult, setLastResult] = useState<Measurement | null>(null)

  useEffect(() => {
    api.model(id).then(setModel).catch((e) => setErr(String(e)))
    api.quality(id).then(setQuality).catch(() => {})
    api.trajectory(id).then(setTraj).catch(() => {})
    api.frameMetrics(id).then(setMetrics).catch(() => {})
    api.keyframes(id).then(setKeyframes).catch(() => {})
    api.exports(id).then((e) => setExps(e.available)).catch(() => {})
    api.listMeasurements(id).then(setMeasurements).catch(() => {})
  }, [id])

  const toggleProv = (code: number) => {
    const s = new Set(visible)
    s.has(code) ? s.delete(code) : s.add(code)
    setVisible(s)
  }

  const startKind = (k: MeasurementKind) => { setKind(k); setPts([]); setLastResult(null) }
  const onPick = useCallback((p: Vec3) => setPts((prev) => [...prev, p]), [])
  const cancel = () => { setKind(null); setPts([]) }

  const finish = async () => {
    if (!kind) return
    try {
      const m = await api.createMeasurement(id, { kind, points: pts, allow_inferred: allowInferred })
      setLastResult(m)
      setMeasurements(await api.listMeasurements(id))
      setPts([]); setKind(null)
    } catch (e) { setErr(String(e)) }
  }

  const del = async (mid: string) => {
    await api.deleteMeasurement(id, mid)
    setMeasurements(await api.listMeasurements(id))
  }

  const savedLines = useMemo(
    () => measurements.filter((m) => m.points_enu.length >= 2).map((m) => m.points_enu),
    [measurements])

  const kfSet = useMemo(() => new Set(keyframes.map((k) => k.frame_index)), [keyframes])
  const hoverLL = hover && model ? enuToLatLon(model.frame, hover[0], hover[1]) : null
  const canFinish = kind != null && pts.length >= KIND_MIN[kind]

  if (err && !model) return <div className="container"><div className="notebox warn">{err}</div><Link to="/missions">← Missions</Link></div>
  if (!model) return <div className="container"><div className="muted">Loading reconstruction…</div></div>

  return (
    <div className="analysis-page">
    <header className="analysis-header"><div className="row"><Link to="/missions">← Missions</Link><span className="muted">/</span><h1>Analysis workspace</h1></div><div className="row"><span className="eyebrow">INSPECT · MEASURE · UNDERSTAND</span><Link to={`/projects/${id}/demo`}>Present ↗</Link></div></header>
    <div className="workspace">
      {/* LEFT: tools + layers */}
      <aside className="wpanel">
        <ReconstructionNotice quality={quality} />
        <div className="spread"><h3>Measurement</h3></div>
        <div className="row">
          {(['point', 'distance', 'height', 'area'] as MeasurementKind[]).map((k) => (
            <button key={k} className={kind === k ? 'active' : ''} onClick={() => startKind(k)}>{k}</button>
          ))}
        </div>
        {kind && (
          <div className="notebox" style={{ marginTop: 8 }}>
            <div><strong>{kind}</strong> — click points on the cloud.</div>
            <div className="muted">picked {pts.length} / min {KIND_MIN[kind]}</div>
            <div className="row" style={{ marginTop: 6 }}>
              <button className="primary" disabled={!canFinish} onClick={finish}>Finish</button>
              <button onClick={() => setPts([])}>Clear</button>
              <button onClick={cancel}>Cancel</button>
            </div>
          </div>
        )}
        <label className="checkline" style={{ marginTop: 8 }}>
          <input type="checkbox" checked={allowInferred} onChange={(e) => setAllowInferred(e.target.checked)} />
          Include inferred geometry
        </label>

        {lastResult && (
          <div className="notebox" style={{ marginTop: 10 }}>
            <div className="spread"><strong>{lastResult.kind}</strong>
              <span className="mono">{lastResult.value == null ? '—' : `${lastResult.value.toFixed(3)} ${lastResult.unit}`}</span></div>
            <div className="muted">{lastResult.confidence_note}</div>
            {lastResult.warnings.map((w, i) => <div key={i} className="warn" style={{ fontSize: 12 }}>⚠ {w}</div>)}
          </div>
        )}

        <div style={{ marginTop: 18, borderTop: '1px solid var(--border)', paddingTop: 12 }}>
          <ToleranceLens
            projectId={id} kind={kind} points={pts}
            onConsumed={() => { setPts([]); setKind(null) }} />
        </div>

        <h3 style={{ marginTop: 18 }}>Display</h3>
        <div className="row">
          <button className={colorMode === 'provenance' ? 'active' : ''} onClick={() => setColorMode('provenance')}>Provenance</button>
          <button className={colorMode === 'true' ? 'active' : ''} onClick={() => setColorMode('true')}>True color</button>
        </div>
        <label className="checkline" style={{ marginTop: 8 }}>
          <input type="checkbox" checked={splat} onChange={(e) => setSplat(e.target.checked)} />
          <span style={{ flex: 1 }}>Soft point rendering</span>
        </label>
        <label htmlFor="point-size">Point size: {pointSize.toFixed(1)}×</label>
        <input id="point-size" className="slider" type="range" min={0.3} max={4} step={0.1} value={pointSize} onChange={(e) => setPointSize(+e.target.value)} />

        <h3 style={{ marginTop: 18 }}>Provenance layers</h3>
        {PROVENANCE.map((p) => {
          const count = quality?.cloud.class_counts?.[p.key] ?? 0
          return (
            <label key={p.code} className="checkline">
              <input type="checkbox" checked={visible.has(p.code)} onChange={() => toggleProv(p.code)} />
              <span className="swatch" style={{ background: `rgb(${p.color.join(',')})` }} />
              <span style={{ flex: 1 }}>{p.label}</span>
              <span className="muted mono">{count}</span>
            </label>
          )
        })}
        <div className="muted" style={{ fontSize: 12, marginTop: 6 }}>
          Measurements use observed high-confidence geometry unless you include inferred.
        </div>
      </aside>

      {/* CENTER: viewer */}
      <div className="viewer-wrap">
        <PointCloudViewer
          model={model} full={full} colorMode={colorMode} splat={splat} pointSize={pointSize}
          visibleProvenance={visible} picking={kind != null}
          onPick={onPick} onHover={setHover}
          activePoints={pts} savedLines={savedLines}
        />
        <div className="viewer-hint">
          {kind ? `Picking for ${kind} — click points, then Finish` : 'Drag to orbit · scroll to zoom · pick a tool to measure'}
        </div>
        <div className="viewer-detail">
          {full ? (
            <span className="mono">all {full.n.toLocaleString()} points</span>
          ) : fullState === 'loading' ? (
            <span className="mono">loading full cloud… {Math.round(fullProgress * 100)}%</span>
          ) : (
            <button
              onClick={async () => {
                setFullState('loading'); setFullProgress(0)
                try {
                  setFull(await api.modelFull(id, setFullProgress))
                  setFullState('idle')
                } catch (e) { setErr(String(e)); setFullState('error') }
              }}
              title="The view shows a downsampled preview. This loads every point."
            >
              Show all {model.points.length < (quality?.cloud.n_points ?? 0)
                ? (quality?.cloud.n_points ?? 0).toLocaleString() : ''} points
            </button>
          )}
        </div>
        <div className="viewer-overlay mono">
          {hover
            ? `ENU  E ${hover[0].toFixed(2)}  N ${hover[1].toFixed(2)}  U ${hover[2].toFixed(2)} m` +
              (hoverLL ? `\n${hoverLL.lat.toFixed(6)}, ${hoverLL.lon.toFixed(6)}` : '')
            : `${(full ? full.n : model.points.length).toLocaleString()} points shown`
              + (full || !quality?.cloud.n_points
                 || quality.cloud.n_points <= model.points.length
                  ? '' : ` of ${quality.cloud.n_points.toLocaleString()}`)}
        </div>
      </div>

      {/* RIGHT: quality + map + exports + measurements */}
      <aside className="wpanel right">
        <div className="spread">
          <h3>Reconstruction</h3>
          <Link to={`/projects/${id}/report`}>Full report →</Link>
        </div>
        {quality && (
          <>
            <div className="kv"><span className="k">Registered keyframes</span><span>{quality.reconstruction.n_registered}/{quality.reconstruction.n_keyframes}</span></div>
            <div className="kv"><span className="k">Points</span><span>{quality.cloud.n_points.toLocaleString()}</span></div>
            <div className="kv"><span className="k">Median reproj. err</span><span>{fmt(quality.reconstruction.median_reproj_err, 3, 'px')}</span></div>
            <div className="kv"><span className="k">Mean track length</span><span>{fmt(quality.reconstruction.mean_track_length, 2)}</span></div>
            {quality.alignment ? (
              <>
                <div className="kv"><span className="k">Scale source</span><span className="mono">{quality.alignment.scale_source}</span></div>
                <div className="kv"><span className="k">Align. RMSE (H/V)</span><span>{quality.alignment.alignment_rmse_horizontal_m.toFixed(2)} / {quality.alignment.alignment_rmse_vertical_m.toFixed(2)} m</span></div>
              </>
            ) : <div className="kv"><span className="k">Alignment</span><span>relative scale only</span></div>}
            <div className="kv"><span className="k">Proc. / video</span><span>{fmt(quality.performance.processing_to_video_ratio, 1, '×')}</span></div>
            {quality.alignment && <div className="notebox warn" style={{ marginTop: 8, fontSize: 12 }}>{quality.alignment.note}</div>}
          </>
        )}

        <h3 style={{ marginTop: 18 }}>Trajectory</h3>
        {traj ? <TrajectoryMap traj={traj} /> : <div className="muted">not available</div>}

        <h3 style={{ marginTop: 18 }}>Keyframe timeline</h3>
        <div className="timeline">
          {metrics.map((m) => (
            <div key={m.frame_index}
              className={`tick ${m.accepted ? 'ok' : 'bad'} ${kfSet.has(m.frame_index) ? 'kf' : ''}`}
              title={`frame ${m.frame_index}${m.reasons.length ? ' · ' + m.reasons.join(',') : ''}`} />
          ))}
        </div>
        <div className="muted" style={{ fontSize: 12 }}>green accepted · red rejected · outlined = keyframe</div>

        <h3 style={{ marginTop: 18 }}>Measurements ({measurements.length})</h3>
        {measurements.length === 0 && <div className="muted">None yet.</div>}
        {measurements.map((m) => (
          <div key={m.id} className="kv">
            <span className="k">{m.kind}{m.used_inferred ? ' *' : ''}</span>
            <span className="mono">{m.value == null ? '—' : `${m.value.toFixed(3)} ${m.unit}`}</span>
            <button className="danger" style={{ padding: '2px 6px' }} onClick={() => del(m.id)}>✕</button>
          </div>
        ))}

        <h3 style={{ marginTop: 18 }}>Exports</h3>
        <div className="row">
          {Object.keys(exps).length === 0 && <span className="muted">none</span>}
          {Object.entries(exps).map(([key]) => (
            <a key={key} href={api.exportUrl(id, key)}><button>{key}</button></a>
          ))}
        </div>
        {err && <div className="notebox warn" style={{ marginTop: 10, fontSize: 12 }}>{err}</div>}
      </aside>
    </div>
    </div>
  )
}

function fmt(v: number | null | undefined, digits: number, unit = ''): string {
  if (v == null) return 'not available'
  return `${v.toFixed(digits)}${unit ? ' ' + unit : ''}`
}
