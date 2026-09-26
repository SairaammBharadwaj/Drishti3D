import { useEffect, useRef, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { api, PROVENANCE, processingTime, recommendedProcessing, type Project, type Job, type QualityReport, type ModelPayload } from '../api'
import ReconstructionNotice from '../ReconstructionNotice'
import PointCloudViewer from '../PointCloudViewer'

const fmt = (n: number | null | undefined, digits = 1, unit = '') => n == null || !Number.isFinite(n) ? 'Unavailable' : `${n.toLocaleString(undefined, { maximumFractionDigits: digits })}${unit}`
const noop = () => {}
const layers = new Set([0, 1, 2, 3, 4])

export default function Presentation() {
  const { id } = useParams()
  const nav = useNavigate()
  const [projects, setProjects] = useState<Project[]>([])
  const [project, setProject] = useState<Project | null>(null)
  const [phase, setPhase] = useState<'source' | 'running' | 'results'>('source')
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  const [q, setQ] = useState<QualityReport | null>(null)
  const [model, setModel] = useState<ModelPayload | null>(null)
  const [job, setJob] = useState<Job | null>(null)
  const [exports, setExports] = useState<Record<string, string>>({})
  const [mode, setMode] = useState<'true' | 'provenance'>('true')
  const [size, setSize] = useState(1)
  const [videoError, setVideoError] = useState(false)
  const [elapsed, setElapsed] = useState(0)
  const generation = useRef(0)
  const video = useRef<HTMLVideoElement>(null)
  const root = useRef<HTMLDivElement>(null)

  useEffect(() => {
    const token = ++generation.current
    setProject(null); setPhase('source'); setQ(null); setModel(null); setJob(null)
    setError(''); setBusy(false); setVideoError(false); setExports({})
    api.listProjects().then(ps => { if (generation.current === token) setProjects(ps) }).catch(e => { if (generation.current === token) setError(String(e)) })
    if (id) api.getProject(id).then(p => { if (generation.current === token) setProject(p) }).catch(e => { if (generation.current === token) setError(String(e)) })
    return () => { generation.current++ }
  }, [id])

  async function reveal(projectId: string, token: number) {
    const [quality, cloud, files] = await Promise.all([api.quality(projectId), api.model(projectId), api.exports(projectId)])
    if (generation.current !== token) return
    setQ(quality); setModel(cloud); setExports(files.available); setPhase('results'); setBusy(false)
    setProject(p => p ? { ...p, status: 'done' } : p)
  }

  useEffect(() => {
    if (phase !== 'running' || !project) return
    let stopped = false
    let timer: ReturnType<typeof setTimeout>
    const token = generation.current
    const start = Date.now()
    const clock = setInterval(() => setElapsed((Date.now() - start) / 1000), 1000)
    async function poll() {
      try {
        const current = await api.getProject(project!.id)
        const state = job?.id ? await api.getJob(job.id) : null
        if (stopped) return
        if (state) setJob(state)
        if (current.status === 'done' || state?.status === 'done') {
          await reveal(project!.id, token)
          return
        }
        if (current.status === 'failed' || state?.status === 'failed') {
          setProject(current); setPhase('source'); setBusy(false)
          setError(state?.error || 'Reconstruction failed. Check the capture and retry.'); return
        }
        setError('')
      } catch (e) { if (!stopped) setError(`Connection interrupted; retrying. ${String(e)}`) }
      if (!stopped) timer = setTimeout(poll, 2000)
    }
    void poll()
    return () => { stopped = true; clearTimeout(timer); clearInterval(clock) }
  }, [phase, project?.id, job?.id])

  async function run() {
    if (!project || busy) return
    video.current?.pause(); setBusy(true); setError('')
    const token = generation.current
    try {
      const current = await api.getProject(project.id)
      if (generation.current !== token) return
      setProject(current)
      if (current.status === 'done') await reveal(current.id, token)
      else if (current.status === 'processing') { setJob(null); setElapsed(0); setPhase('running') }
      else {
        // The same settings as a mission started from the wizard: dense stereo
        // on COLMAP when this server has it, the built-in engine otherwise.
        const caps = await api.capabilities().catch(() => null)
        const next = await api.process(current.id, recommendedProcessing(caps))
        if (generation.current !== token) return
        setJob(next); setElapsed(0); setPhase('running')
      }
    } catch (e) { if (generation.current === token) { setError(String(e)); setBusy(false) } }
  }

  const metricScale = q ? !!q.alignment && q.alignment.scale_source !== 'relative' : false
  const progress = Math.max(0, Math.min(100, (job?.progress ?? 0) * 100))

  return <div className={`presentation ${phase === 'results' ? 'showing-results' : ''}`} ref={root}>
    <div className="demo-toolbar">
      <Link to="/missions">← Missions</Link>
      <label className="demo-select">Capture <select aria-label="Choose capture" value={id ?? ''} onChange={e => nav(e.target.value ? `/projects/${e.target.value}/demo` : '/demo')}>
        <option value="">Select a mission</option>
        {projects.filter(p => p.has_video).map(p => <option key={p.id} value={p.id}>{p.name}</option>)}
      </select></label>
      <button onClick={() => { const action = document.fullscreenElement ? document.exitFullscreen() : root.current?.requestFullscreen(); action?.catch(() => setError('Fullscreen is unavailable in this browser.')) }}>Fullscreen</button>
    </div>
    <header className="demo-hero">
      <div className="demo-eyebrow">DRISHTI3D / CAPTURE → RECONSTRUCT → UNDERSTAND</div>
      <h1>One flight.<br /><span>A new dimension of insight.</span></h1>
      <p>Turn drone footage into an interactive 3D scene. Explore the geometry, inspect its evidence, and understand what you can measure.</p>
    </header>
    <ol className="demo-steps" aria-label="Demo progress">{['Original capture', 'Reconstruction', 'Spatial intelligence'].map((s, i) => <li key={s} aria-current={i === (phase === 'source' ? 0 : phase === 'running' ? 1 : 2) ? 'step' : undefined}><span>0{i + 1}</span>{s}</li>)}</ol>
    {error && <div className="notebox warn" role="alert">{error}</div>}
    {!id && <div className="demo-empty card"><h2>Choose a capture to begin</h2><p>Select a mission above, or upload a video to create your own reconstruction.</p><Link to="/new"><button className="primary">Upload a new capture →</button></Link></div>}
    {id && !project && !error && <p role="status">Loading capture…</p>}
    {project && phase !== 'results' && <div className="demo-intro">
      <section className="demo-media"><div className="demo-panel-title"><span>01 / ORIGINAL FOOTAGE</span><span>{project.name}</span></div>
        {project.has_video ? <video key={project.id} ref={video} controls playsInline preload="metadata" src={api.videoUrl(project.id)} onError={() => setVideoError(true)} /> : <p>No video uploaded.</p>}
        {videoError && <p className="notebox warn">This browser cannot play the original format. <a href={api.videoUrl(project.id)}>Download the source video</a> to play it locally. Inference can still run.</p>}
        <div className="demo-media-footer">Original capture · {project.has_telemetry ? 'Flight telemetry attached' : 'Video only · relative scale'} · {project.intrinsics ? 'Camera calibration supplied' : 'Camera parameters estimated'}</div>
      </section>
      <aside className="card demo-brief"><div className="demo-eyebrow">FROM PIXELS TO EVIDENCE</div><h2>See what this flight reveals.</h2>
        <p>{project.description || 'Reconstruct the scene from overlapping frames, recover the camera path, and inspect the resulting spatial evidence.'}</p>
        <ul><li><strong>Explore in 3D</strong><span>Rotate, zoom, and inspect the reconstructed point cloud.</span></li><li><strong>Understand quality</strong><span>Frame registration, geometric consistency, and processing performance.</span></li><li><strong>Know the evidence</strong><span>Separate observed geometry from AI-assisted points before measuring.</span></li></ul>
        {phase === 'source' ? <><button className="primary demo-cta" disabled={busy || !project.has_video} onClick={run}>{busy ? 'Loading results…' : project.status === 'done' ? 'Reveal 3D & metrics →' : project.status === 'processing' ? 'Follow live reconstruction →' : 'Generate 3D & metrics →'}</button><small className="muted">{project.status === 'done' ? 'Presentation mode: reveals this mission’s saved reconstruction. No new inference is run.' : 'Runs the reconstruction pipeline. Processing time depends on the footage and hardware.'}</small></> : <div role="status" aria-live="polite"><h2>{job?.stage || 'Reconstructing scene…'}</h2><p>{job?.message || 'Waiting for the active reconstruction to complete.'}</p><div className="progress-track"><div className="progress-fill" style={{ width: `${progress}%` }} /></div><p className="mono">{job ? `${progress.toFixed(0)}% · ` : ''}{fmt(elapsed, 0)} s elapsed</p><small>Results open automatically when processing completes.</small></div>}
      </aside>
    </div>}
    {phase === 'results' && q && model && project && <div className="demo-results">
      <div className="spread demo-result-heading"><div><div className="demo-eyebrow">03 / RECONSTRUCTION RESULTS</div><h2>{project.name}</h2><span className="muted">Metrics from this mission’s saved quality report</span></div><div className="row"><button onClick={() => { setPhase('source'); setBusy(false) }}>← Replay original</button><Link to={`/projects/${id}`}><button className="primary">Measure in workspace ↗</button></Link></div></div>
      <ReconstructionNotice quality={q} />
      <div className="demo-stats">
        <Stat label="Reconstructed points" value={fmt(q.cloud.n_points, 0)} note="Geometry in the output cloud" />
        <Stat label="Camera registration" value={fmt(q.reconstruction.registered_fraction * 100, 1, '%')} note={`${q.reconstruction.n_registered} of ${q.reconstruction.n_keyframes} keyframes recovered`} />
        <Stat label="Reprojection error" value={fmt(q.reconstruction.median_reproj_err, 2, ' px')} note="Image consistency · lower is better" />
        <Stat label="Processing time" value={fmt(processingTime(q).seconds, 1, ' s')} note={`${fmt(processingTime(q).ratio, 2, '×')} video duration${processingTime(q).endToEnd ? ' · end to end' : ' · excludes exports'}`} />
      </div>
      <div className="demo-output-grid"><section className="demo-media"><div className="demo-panel-title"><span>INTERACTIVE 3D / POINT CLOUD</span><span>{fmt(model.points.length, 0)} displayed points</span></div><div className="demo-viewer-tools"><button className={mode === 'true' ? 'active' : ''} onClick={() => setMode('true')}>True colour</button><button className={mode === 'provenance' ? 'active' : ''} onClick={() => setMode('provenance')}>Evidence colours</button><label>Point size <input aria-label="Point size" type="range" min="0.3" max="4" step="0.1" value={size} onChange={e => setSize(Number(e.target.value))} /></label></div><div className="demo-viewer">{model.points.length ? <PointCloudViewer model={model} colorMode={mode} splat={false} pointSize={size} visibleProvenance={layers} picking={false} onPick={noop} onHover={noop} activePoints={[]} savedLines={[]} /> : <p>No geometry was reconstructed from this capture.</p>}</div><div className="demo-media-footer">Drag to rotate · Scroll to zoom · Right-drag to pan · Blue line: recovered camera path</div></section>
      <aside className="card"><h3>What is the model made of?</h3><p className="muted">Evidence classes describe how each point was obtained. They are not an independent accuracy score.</p>{PROVENANCE.map(p => <div className="demo-provenance" key={p.code}><div className="spread"><span>{p.label}</span><strong>{fmt((q.cloud.class_fractions[p.key] ?? 0) * 100, 1, '%')}</strong></div><div className="bar"><span style={{ width: `${Math.max(0, Math.min(1, q.cloud.class_fractions[p.key] ?? 0)) * 100}%`, background: `rgb(${p.color.join(',')})` }} /></div></div>)}<div className="notebox">{metricScale ? `Scale source: ${q.alignment?.scale_source}. Measurement accuracy depends on calibration, geometry, and positioning quality.` : 'Relative scale: explore the shape; real-world distances are not established for this capture.'}</div></aside></div>
      <div className="demo-detail-grid">
        <section className="card"><h3>Capture & frame selection</h3><Metric label="Source resolution" value={`${q.input.video.width} × ${q.input.video.height}`} /><Metric label="Duration / frame rate" value={`${fmt(q.input.video.duration, 1, ' s')} / ${fmt(q.input.video.fps, 1, ' fps')}`} /><Metric label="Frames analyzed" value={fmt(q.frames.total_analyzed, 0)} /><Metric label="Accepted / rejected" value={`${q.frames.accepted} / ${q.frames.rejected}`} /><Metric label="Selected keyframes" value={fmt(q.frames.keyframes, 0)} /><p className="muted">Frame screening reduces blurred or poorly exposed inputs before reconstruction.</p></section>
        <section className="card"><h3>Geometry & scale</h3><Metric label="Mean observations per track" value={fmt(q.reconstruction.mean_track_length, 2)} /><Metric label="Mean triangulation angle" value={fmt(q.reconstruction.mean_tri_angle, 2, '°')} /><Metric label="Model dimensions" value={metricScale && q.cloud.dimensions_m ? q.cloud.dimensions_m.map(v => fmt(v, 1)).join(' × ') + ' m' : 'Metric scale unavailable'} /><Metric label="Median point spacing" value={metricScale ? fmt(q.cloud.median_point_spacing_m, 3, ' m') : 'Metric scale unavailable'} /><p className="muted">Multiple views and sufficient viewing angles support depth recovery. Point count alone does not establish accuracy.</p></section>
        <section className="card"><h3>Positioning evidence</h3><Metric label="Telemetry samples" value={fmt(q.input.telemetry.n_valid, 0)} /><Metric label="RTK in telemetry" value={q.input.telemetry.has_rtk ? 'Present' : 'Absent'} /><Metric label="Horizontal alignment RMSE" value={fmt(q.alignment?.alignment_rmse_horizontal_m, 3, ' m')} /><Metric label="Vertical alignment RMSE" value={fmt(q.alignment?.alignment_rmse_vertical_m, 3, ' m')} /><p className="muted">Alignment residuals describe the fit to input GPS. They do not establish independent survey accuracy.</p></section>
      </div>
      <section className="card demo-validation"><div><div className="demo-eyebrow">HOW GOOD IS THIS RECONSTRUCTION?</div><h2>{q.ground_truth_evaluation ? 'Measured against a ground-truth reference.' : 'Quality indicators available. Absolute accuracy unverified.'}</h2><p className="muted">{q.ground_truth_evaluation ? 'These errors compare this reconstruction to the supplied reference fixture.' : 'This mission has no independent ground-truth evaluation. Registration and reprojection error describe reconstruction consistency; they cannot prove centimetre accuracy.'}</p></div>{q.ground_truth_evaluation && <div className="demo-stats"><Stat label="Median surface error" value={fmt(q.ground_truth_evaluation.surface_accuracy_m?.median, 3, ' m')} note="Against the supplied reference" /><Stat label="90th-percentile error" value={fmt(q.ground_truth_evaluation.surface_accuracy_m?.p90, 3, ' m')} note="90% of evaluated errors fall below this" /></div>}</section>
      {(q.warnings.length > 0 || q.limitations.length > 0) && <details className="card" open><summary>Run notes & limitations ({q.warnings.length + q.limitations.length})</summary><ul>{q.warnings.map((w, i) => <li className="warn" key={`w${i}`}>{w}</li>)}{q.limitations.map((l, i) => <li className="muted" key={`l${i}`}>{l}</li>)}</ul></details>}
      <section className="card demo-downloads"><div><h2>Take the evidence with you.</h2><p className="muted">Export the generated artifacts or open the complete evidence report.</p></div><div className="row"><Link to={`/projects/${id}/report`}><button className="primary">Full evidence report ↗</button></Link>{Object.keys(exports).map(key => <a key={key} href={api.exportUrl(project.id, key)} target="_blank" rel="noreferrer"><button>{key.replace(/_/g, ' ')} ↓</button></a>)}</div></section>
    </div>}
    <footer className="demo-footer"><strong>DRISHTI3D</strong><span>Single-pass reconstruction · Evidence-aware geometry · Spatial measurement</span></footer>
  </div>
}
function Stat({ label, value, note }: { label: string; value: string; note: string }) { return <div className="demo-stat"><span>{label}</span><strong>{value}</strong><small>{note}</small></div> }
function Metric({ label, value }: { label: string; value: string }) { return <div className="kv"><span className="k">{label}</span><span className="mono">{value}</span></div> }
