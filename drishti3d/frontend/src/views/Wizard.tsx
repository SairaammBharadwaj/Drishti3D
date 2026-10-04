import { useEffect, useRef, useState } from 'react'
import { Link, useNavigate, useSearchParams } from 'react-router-dom'
import {
  api, recommendedProcessing,
  type Capabilities, type Densify, type Engine, type ProcessOptions, type Project,
} from '../api'
import { useReadOnly } from '../deployment'

export default function Wizard() {
  const nav = useNavigate()
  const readOnly = useReadOnly()
  const [params, setParams] = useSearchParams()
  const resumeId = params.get('project')
  const [resuming, setResuming] = useState(Boolean(resumeId))
  const [step, setStep] = useState(0)
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState<string | null>(null)

  const [name, setName] = useState('')
  const [description, setDescription] = useState('')
  const [project, setProject] = useState<Project | null>(null)

  const [preset, setPreset] = useState('balanced')
  // A fast real reconstruction first, then the full run replaces it.
  const [previewFirst, setPreviewFirst] = useState(false)
  const [maskBackend, setMaskBackend] = useState('none')
  const [doMesh, setDoMesh] = useState(true)
  const [engine, setEngine] = useState<Engine>('opencv')
  const [densify, setDensify] = useState<Densify>('none')
  // '' leaves the pipeline default in place (240 frames, 1280 px).
  const [maxFrames, setMaxFrames] = useState('')
  const [procWidth, setProcWidth] = useState('')
  const [useIntr, setUseIntr] = useState(false)
  const [intr, setIntr] = useState({ fx: '', fy: '', cx: '', cy: '' })
  const [caps, setCaps] = useState<Capabilities | null>(null)
  const capsRef = useRef<Capabilities | null>(null)

  const applyProfile = (o: ProcessOptions) => {
    setEngine(o.engine); setDensify(o.densify)
    setMaxFrames(o.max_analyze_frames ? String(o.max_analyze_frames) : '')
    setProcWidth(o.proc_max_width ? String(o.proc_max_width) : '')
  }

  // Default to what this server can actually run: the COLMAP + dense stereo
  // settings the demo missions used when it can, the built-in engine if not.
  useEffect(() => {
    api.capabilities().then((c) => {
      capsRef.current = c; setCaps(c); applyProfile(recommendedProcessing(c))
    }).catch(() => { capsRef.current = null; setCaps(null) })
  }, [])

  useEffect(() => {
    if (resumeId) return
    setProject(null); setName(''); setDescription(''); setStep(0); setErr(null)
    setResuming(false); setUseIntr(false); setIntr({ fx: '', fy: '', cx: '', cy: '' })
    setPreset('balanced'); setMaskBackend('none'); setDoMesh(true)
    applyProfile(recommendedProcessing(capsRef.current))
  }, [resumeId])

  const colmapReady = Boolean(caps?.engines.colmap)
  const mvsReady = colmapReady && Boolean(caps?.optional.dense_mvs?.available)
  const changeEngine = (e: Engine) => {
    if (e === 'colmap') applyProfile(recommendedProcessing(caps))
    else applyProfile({ ...recommendedProcessing(null), engine: e })
  }

  useEffect(() => {
    if (!resumeId || project?.id === resumeId) return
    let cancelled = false
    setResuming(true)
    api.getProject(resumeId).then(p => {
      if (cancelled) return
      if (p.status !== 'created') { nav(`/projects/${p.id}/demo`, { replace: true }); return }
      setProject(p); setName(p.name); setDescription(p.description); setStep(p.has_video ? 2 : 1)
      if (p.intrinsics) { setUseIntr(true); setIntr({ fx: String(p.intrinsics.fx), fy: String(p.intrinsics.fy), cx: String(p.intrinsics.cx), cy: String(p.intrinsics.cy) }) }
    }).catch(e => { if (!cancelled) setErr(String(e)) }).finally(() => { if (!cancelled) setResuming(false) })
    return () => { cancelled = true }
  }, [resumeId, project?.id, nav])

  const wrap = async (fn: () => Promise<void>) => {
    setBusy(true); setErr(null)
    try { await fn() } catch (e) { setErr(String(e)) } finally { setBusy(false) }
  }

  const createProject = () => wrap(async () => {
    const p = await api.createProject(name.trim(), description.trim())
    setProject(p); setStep(1); setParams({ project: p.id }, { replace: true })
  })

  const onVideo = (f: File | undefined) => f && project && wrap(async () => {
    setProject(await api.uploadVideo(project.id, f))
  })
  const onTelemetry = (f: File | undefined) => f && project && wrap(async () => {
    setProject(await api.uploadTelemetry(project.id, f))
  })

  const start = () => project && wrap(async () => {
    let intrinsics
    if (useIntr) {
      intrinsics = { fx: +intr.fx, fy: +intr.fy, cx: +intr.cx, cy: +intr.cy }
      if (Object.values(intrinsics).some((v) => !isFinite(v) || v <= 0))
        throw new Error('intrinsics must be positive numbers')
      await api.setIntrinsics(project.id, intrinsics)
    }
    const opts: ProcessOptions = previewFirst
      ? { preset: 'preview', then_full: true, mask_backend: maskBackend, do_mesh: doMesh, engine, densify, intrinsics }
      : { preset, mask_backend: maskBackend, do_mesh: doMesh, engine, densify, intrinsics }
    const frames = parseInt(maxFrames, 10), width = parseInt(procWidth, 10)
    if (Number.isFinite(frames)) opts.max_analyze_frames = frames
    if (Number.isFinite(width)) opts.proc_max_width = width
    const job = await api.process(project.id, opts)
    nav(`/projects/${project.id}/monitor?job=${job.id}`)
  })

  const canProcess = project?.has_video

  if (readOnly) return <div className="library"><div className="empty-state"><span className="outline-cube" aria-hidden="true">◇</span><h2>New reconstructions aren’t available here.</h2><p>This is a read-only showcase of finished missions. Reconstruction runs on the team’s own hardware.</p><Link className="action primary-action" to="/missions">Explore the missions ↗</Link></div></div>
  return (
    <div className="wizard-page">
      <div className="page-heading"><div><div className="eyebrow">CAPTURE → RECONSTRUCTION</div><h1>A new perspective.</h1><p>{project ? project.name : 'Set up your mission. Let the footage do the talking.'}</p></div><Link className="text-action" to="/missions">← Mission library</Link></div>
      <div className="wizard-layout"><aside className="wizard-aside"><ol className="wizard-steps">{['Your mission', 'Drone footage', 'Telemetry', 'Camera & options'].map((s, i) => <li key={s} aria-current={i === step ? 'step' : undefined}><span>{i < step ? '✓' : `0${i + 1}`}</span>{s}</li>)}</ol><p>Start with one continuous pass.<br />Clear overlap and different viewpoints help the reconstruction recover useful geometry.</p><p>Without telemetry, your model has relative scale. Geographic position and distances in metres are not established.</p></aside><div className="wizard-form">

      {err && <div className="notebox warn" role="alert" style={{ marginBottom: 14 }}>{err}</div>}
      {resuming && <p role="status">Opening your saved mission…</p>}
      {busy && <p role="status">Saving your mission… Please keep this page open.</p>}
      <fieldset disabled={busy || resuming || Boolean(resumeId && !project)} style={{ border: 0, padding: 0, margin: 0, minWidth: 0 }}>

      {step === 0 && (
        <div className="card stack">
          <div>
            <label htmlFor="mission-name">Mission name</label>
            <input id="mission-name" value={name} onChange={(e) => setName(e.target.value)} placeholder="e.g. Sector 7 damage survey" style={{ width: '100%' }} />
          </div>
          <div>
            <label htmlFor="mission-description">Description (optional)</label>
            <input id="mission-description" value={description} onChange={(e) => setDescription(e.target.value)} style={{ width: '100%' }} />
          </div>
          <div className="row">
            <button className="primary" disabled={!name.trim() || busy} onClick={createProject}>Create & continue →</button>
          </div>
        </div>
      )}

      {step === 1 && project && (
        <div className="card stack">
          <h3>Upload drone video</h3>
          <input type="file" aria-label="Upload drone video" accept=".mp4,.mov,.m4v,.avi,.mkv,.webm" onChange={(e) => onVideo(e.target.files?.[0])} />
          <div className="muted">Supported: MP4, MOV, M4V, AVI, MKV, WebM.</div>
          {project.video_filename && <div className="notebox">Uploaded: <span className="mono">{project.video_filename}</span></div>}
          <div className="row">
            <Link className="text-action" to="/missions">← Save & leave</Link>
            <button className="primary" disabled={!project.has_video || busy} onClick={() => setStep(2)}>Next →</button>
          </div>
        </div>
      )}

      {step === 2 && project && (
        <div className="card stack">
          <h3>Telemetry (optional · CSV / JSON / SRT / RTKLIB .pos)</h3>
          <div className="muted" style={{ fontSize: 13 }}>
            If supplied, required fields are timestamp, latitude, longitude, altitude. Optional: yaw, gps_accuracy, rtk_status, fx/fy/cx/cy.
          </div>
          <div className="notebox">No telemetry? Continue with video only. The reconstruction will have relative scale, without established distances in metres or a geographic position.</div>
          <input type="file" aria-label="Upload telemetry" accept=".csv,.json,.srt,.pos" onChange={(e) => onTelemetry(e.target.files?.[0])} />
          {project.telemetry_filename && <div className="notebox">Uploaded: <span className="mono">{project.telemetry_filename}</span></div>}
          <div className="row">
            <button onClick={() => setStep(1)}>← Back</button>
            <button className="primary" disabled={busy} onClick={() => setStep(3)}>{project.has_telemetry ? 'Next →' : 'Continue without telemetry →'}</button>
          </div>
        </div>
      )}

      {step === 3 && project && (
        <div className="card stack">
          <h3>Camera intrinsics (optional)</h3>
          <label className="checkline"><input type="checkbox" checked={useIntr} onChange={(e) => setUseIntr(e.target.checked)} /> Provide camera calibration (fx, fy, cx, cy)</label>
          {useIntr && (
            <div className="row">
              {(['fx', 'fy', 'cx', 'cy'] as const).map((k) => (
                <div key={k}>
                  <label htmlFor={`intr-${k}`}>{k}</label>
                  <input id={`intr-${k}`} inputMode="decimal" style={{ width: 100 }} value={intr[k]} onChange={(e) => setIntr({ ...intr, [k]: e.target.value })} />
                </div>
              ))}
            </div>
          )}
          <h3 style={{ marginTop: 12 }}>Processing options</h3>
          <div className="row">
            <div>
              <label htmlFor="engine">Reconstruction engine</label>
              <select id="engine" value={engine} onChange={(e) => changeEngine(e.target.value as Engine)}>
                <option value="colmap" disabled={!colmapReady}>COLMAP{colmapReady ? '' : ' (not installed)'}</option>
                <option value="opencv">built-in (OpenCV)</option>
              </select>
            </div>
            <div>
              <label htmlFor="preset">Preset</label>
              <select id="preset" value={preset} onChange={(e) => setPreset(e.target.value)} disabled={previewFirst}>
                <option value="preview">preview (first look, ≤40 keyframes)</option>
                <option value="fast">fast</option>
                <option value="balanced">balanced</option>
                <option value="quality">quality</option>
              </select>
            </div>
            <label className="checkline">
              <input type="checkbox" checked={previewFirst} onChange={(e) => setPreviewFirst(e.target.checked)} />
              Preview first, then the full balanced run (the preview is replaced when it finishes)
            </label>
            <div>
              <label htmlFor="masking">Dynamic masking</label>
              <select id="masking" value={maskBackend} onChange={(e) => setMaskBackend(e.target.value)}>
                <option value="none">none</option>
                <option value="optical_flow">optical-flow residual</option>
                <option value="semantic">semantic (torch)</option>
              </select>
            </div>
            <div>
              <label htmlFor="densification">Densification</label>
              <select id="densification" value={densify} onChange={(e) => setDensify(e.target.value as Densify)}>
                <option value="mvs" disabled={engine !== 'colmap' || !mvsReady}>dense stereo (observed, measurable){mvsReady ? '' : ' (needs COLMAP with CUDA)'}</option>
                <option value="none">classical only (sparse)</option>
                <option value="depth">depth prior (dense, AI-assisted)</option>
              </select>
            </div>
            <div>
              <label>Meshing</label>
              <label className="checkline"><input type="checkbox" checked={doMesh} onChange={(e) => setDoMesh(e.target.checked)} /> Generate mesh</label>
            </div>
          </div>
          <div className="row">
            <div>
              <label htmlFor="max-frames">Frames analysed (max)</label>
              <input id="max-frames" type="number" min={2} max={20000} step={1} inputMode="numeric" style={{ width: 130 }}
                placeholder="240 (default)" value={maxFrames} onChange={(e) => setMaxFrames(e.target.value)} />
            </div>
            <div>
              <label htmlFor="proc-width">Processing width (px)</label>
              <input id="proc-width" type="number" min={320} max={4096} step={16} inputMode="numeric" style={{ width: 130 }}
                placeholder="1280 (default)" value={procWidth} onChange={(e) => setProcWidth(e.target.value)} />
            </div>
          </div>
          {engine === 'colmap' && densify === 'mvs' && (
            <div className="notebox">The settings the DJI demo missions were processed with: COLMAP structure-from-motion, then dense multi-view stereo. Every dense point is agreed on by at least four real images, so it counts as observed geometry and can be measured. Needs a CUDA GPU. An 11-minute 1080p video took 12–13 minutes on the development laptop.</div>
          )}
          {engine === 'opencv' && (
            <div className="notebox">The built-in engine needs no external tools and produces a sparse cloud. For a dense, measurable model, choose COLMAP with dense stereo.</div>
          )}
          {densify === 'depth' && (
            <div className="notebox">Fuses a monocular depth prior (Depth Anything V2, GPU) to fill single-pass holes. Added points are tagged <b>AI-assisted</b> — shown as a distinct trust-map layer and excluded from measurements by default.</div>
          )}
          {maskBackend === 'optical_flow' && (
            <div className="notebox warn">Optical-flow masking may flag scene parallax on tall structures; best for near-nadir passes.</div>
          )}
          <div className="row">
            <button onClick={() => setStep(2)}>← Back</button>
            <button className="primary" disabled={!canProcess || busy} onClick={start}>Start reconstruction →</button>
          </div>
          {!project.has_telemetry && <div className="notebox">Video-only reconstruction: shape and quality metrics will be available; metric scale and map position are not established.</div>}
          {!canProcess && <div className="muted">Upload a video to proceed.</div>}
        </div>
      )}
      </fieldset></div></div>
    </div>
  )
}
