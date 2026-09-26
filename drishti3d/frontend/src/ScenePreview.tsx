import { useEffect, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import * as THREE from 'three'
import { api, PROVENANCE } from './api'

/** What `scripts/build-preview.py` says about the scene. */
interface PreviewMeta {
  project_id?: string
  code?: string
  place?: string
  scale?: string
  credit?: string
  points_in_scene?: number
  /** The transform the sample was built with; applied to the full cloud too. */
  origin_enu?: [number, number, number]
  metres_per_unit?: number
  view?: { angle: number; elevation_deg: number }
}

/** Points in the preview's frame: x east, y up, z south (three.js, y up). */
interface Cloud {
  n: number
  positions: Float32Array
  rgb: Uint8Array
  evidence: Uint8Array
  nFill: number
  full: boolean
}

const EVIDENCE = new Map(PROVENANCE.map((p) => [p.code, p.color]))
const FILL_CODE = 6
const UNKNOWN: [number, number, number] = [127, 140, 141]

function evidenceColours(prov: Uint8Array): { colours: Uint8Array; nFill: number } {
  const colours = new Uint8Array(prov.length * 3)
  let nFill = 0
  for (let i = 0; i < prov.length; i++) {
    const c = EVIDENCE.get(prov[i]) ?? UNKNOWN
    colours[i * 3] = c[0]; colours[i * 3 + 1] = c[1]; colours[i * 3 + 2] = c[2]
    if (prov[i] === FILL_CODE) nFill++
  }
  return { colours, nFill }
}

/** `preview.bin`: 16-byte records, east/up/north already in local units. */
function fromSample(buf: ArrayBuffer): Cloud {
  const view = new DataView(buf)
  const n = Math.floor(buf.byteLength / 16)
  const positions = new Float32Array(n * 3), rgb = new Uint8Array(n * 3), prov = new Uint8Array(n)
  for (let i = 0; i < n; i++) {
    const o = i * 16
    positions[i * 3] = view.getFloat32(o, true)
    positions[i * 3 + 1] = view.getFloat32(o + 4, true)
    positions[i * 3 + 2] = -view.getFloat32(o + 8, true)
    rgb[i * 3] = view.getUint8(o + 12); rgb[i * 3 + 1] = view.getUint8(o + 13); rgb[i * 3 + 2] = view.getUint8(o + 14)
    prov[i] = view.getUint8(o + 15)
  }
  const { colours, nFill } = evidenceColours(prov)
  return { n, positions, rgb, evidence: colours, nFill, full: false }
}

/** The mission's whole cloud (ENU metres), moved into the sample's frame. */
function fromFull(full: { n: number; xyz: Float32Array; rgb: Uint8Array; provenance: Uint8Array },
                  origin: [number, number, number], mpu: number): Cloud {
  const positions = new Float32Array(full.n * 3)
  for (let i = 0; i < full.n; i++) {
    positions[i * 3] = (full.xyz[i * 3] - origin[0]) / mpu
    positions[i * 3 + 1] = (full.xyz[i * 3 + 2] - origin[2]) / mpu
    positions[i * 3 + 2] = -(full.xyz[i * 3 + 1] - origin[1]) / mpu
  }
  const { colours, nFill } = evidenceColours(full.provenance)
  return { n: full.n, positions, rgb: full.rgb, evidence: colours, nFill, full: true }
}

// The homepage scene: one finished mission, whole. A small uniform sample
// (`/showcase/preview.bin`) paints first; when this installation has the
// mission, every point streams in from the API behind it. Measurement and
// evidence stay in the mission's workspace; this is a picture of it.
export default function ScenePreview() {
  const mount = useRef<HTMLDivElement>(null)
  const gl = useRef<{
    renderer: THREE.WebGLRenderer; scene: THREE.Scene; camera: THREE.PerspectiveCamera
    points: THREE.Points; material: THREE.PointsMaterial; draw: () => void
  } | null>(null)
  const [meta, setMeta] = useState<PreviewMeta>({})
  const [cloud, setCloud] = useState<Cloud | null>(null)
  const [loading, setLoading] = useState<number | null>(null)
  const [error, setError] = useState(false)
  const [unavailable, setUnavailable] = useState(false)
  const [evidence, setEvidence] = useState(false)
  const [turn, setTurn] = useState(0)
  const [missionLink, setMissionLink] = useState<string | null>(null)

  // Data: metadata, then the sample, then (if the mission is here) every point.
  useEffect(() => {
    const abort = new AbortController()
    const live = () => !abort.signal.aborted
    ;(async () => {
      let m: PreviewMeta = {}
      try {
        const r = await fetch('/showcase/preview.json', { signal: abort.signal })
        if (r.ok) m = await r.json() as PreviewMeta
      } catch { /* captions fall back */ }
      if (!live()) return
      setMeta(m)
      try {
        const r = await fetch('/showcase/preview.bin', { signal: abort.signal })
        if (!r.ok) throw new Error('Scene unavailable')
        const sample = fromSample(await r.arrayBuffer())
        if (live()) setCloud(sample)
      } catch { if (live()) setError(true) }
      if (!m.project_id || !m.origin_enu || !m.metres_per_unit) return
      let done = false
      try { done = (await api.getProject(m.project_id)).status === 'done' } catch { return }
      if (!live() || !done) return
      setMissionLink(`/projects/${m.project_id}`)
      setLoading(0)
      try {
        const full = await api.modelFull(m.project_id, (f) => { if (live()) setLoading(f) }, abort.signal)
        if (live()) { setCloud(fromFull(full, m.origin_enu, m.metres_per_unit)); setError(false) }
      } catch { /* the sample stays on screen */ }
      finally { if (live()) setLoading(null) }
    })()
    return () => abort.abort()
  }, [])

  // Renderer: its own canvas, so a remount never reuses a lost context.
  useEffect(() => {
    const host = mount.current!
    let renderer: THREE.WebGLRenderer
    try {
      renderer = new THREE.WebGLRenderer({ antialias: false, alpha: true })
    } catch {
      setUnavailable(true)
      return
    }
    renderer.setClearColor(0x000000, 0)
    renderer.setPixelRatio(Math.min(devicePixelRatio || 1, 2))
    host.appendChild(renderer.domElement)
    const scene = new THREE.Scene()
    const camera = new THREE.PerspectiveCamera(30, 1, 0.01, 100)
    const material = new THREE.PointsMaterial({ vertexColors: true, sizeAttenuation: false, size: 2 })
    const points = new THREE.Points(new THREE.BufferGeometry(), material)
    points.frustumCulled = false
    scene.add(points)
    const draw = () => renderer.render(scene, camera)
    const resize = () => {
      const el = renderer.domElement
      const w = el.clientWidth, h = el.clientHeight
      if (!w || !h) return
      renderer.setSize(w, h, false)
      camera.aspect = w / h; camera.updateProjectionMatrix(); draw()
    }
    const observer = new ResizeObserver(resize); observer.observe(renderer.domElement)
    gl.current = { renderer, scene, camera, points, material, draw }
    return () => {
      observer.disconnect()
      points.geometry.dispose(); material.dispose()
      renderer.dispose(); renderer.forceContextLoss()
      renderer.domElement.remove()
      gl.current = null
    }
  }, [])

  // Geometry: replaced (and the old one freed) when the sample gives way to
  // the full cloud.
  useEffect(() => {
    const g = gl.current
    if (!g || !cloud) return
    g.points.geometry.dispose()
    const geometry = new THREE.BufferGeometry()
    geometry.setAttribute('position', new THREE.BufferAttribute(cloud.positions, 3))
    geometry.setAttribute('color', new THREE.BufferAttribute(new Uint8Array(cloud.rgb), 3, true))
    g.points.geometry = geometry
    // Millions of points overlap into a surface at one pixel; the sample
    // needs larger points to read as one.
    g.material.size = (cloud.full ? 1.25 : 2.2) * g.renderer.getPixelRatio()
    g.draw()
  }, [cloud])

  // Colour: written into the existing buffer rather than a new attribute each
  // toggle, which would leave the old GPU buffer behind.
  useEffect(() => {
    const g = gl.current
    if (!g || !cloud) return
    const attr = g.points.geometry.getAttribute('color') as THREE.BufferAttribute | undefined
    if (!attr) return
    ;(attr.array as Uint8Array).set(evidence ? cloud.evidence : cloud.rgb)
    attr.needsUpdate = true
    g.draw()
  }, [cloud, evidence])

  // View: orbit about the vertical axis at a fixed elevation, from the south.
  useEffect(() => {
    const g = gl.current
    if (!g) return
    const az = (meta.view?.angle ?? 0.35) + turn
    const el = ((meta.view?.elevation_deg ?? 34) * Math.PI) / 180
    const d = 2.75
    g.camera.position.set(d * Math.cos(el) * Math.sin(az), d * Math.sin(el), d * Math.cos(el) * Math.cos(az))
    g.camera.lookAt(0, -0.07, 0)
    g.draw()
  }, [meta, turn])

  const place = meta.place ?? 'Saved reconstruction'
  const caption = !cloud ? place
    : cloud.full
      ? `${place} · every point: ${(cloud.n - cloud.nFill).toLocaleString()} reconstructed + ${cloud.nFill.toLocaleString()} fill`
      : `${place} · ${cloud.n.toLocaleString()}-point sample of ${meta.points_in_scene ? meta.points_in_scene.toLocaleString() : 'the scene'}`
  return <>
    <div className="scene-preview">
      <div className="scene-top"><span className="eyebrow"><i className="status-dot" /> RECONSTRUCTED FROM DRONE VIDEO</span><span className="mono">{loading != null ? `LOADING ALL POINTS ${Math.round(loading * 100)}%` : meta.code ?? ''}</span></div>
      <div className="scene-reticle" aria-hidden="true" />
      <div ref={mount} role="img" aria-label={`3D reconstruction of ${place}, ${evidence ? 'coloured by evidence: green observed, amber low confidence, blue inferred fill' : 'in the colours of the source video'}. Use the rotate buttons to change the view.`} />
      {!cloud && !unavailable && <div className="scene-loading" role="status">{error ? 'Preview unavailable. Open the mission library below.' : 'Loading the reconstructed scene…'}</div>}
      {unavailable && <div className="scene-loading" role="status">3D preview needs WebGL. Open the mission library below.</div>}
      <div className="scene-controls"><div className="segmented" aria-label="Scene colouring"><button aria-pressed={!evidence} onClick={() => setEvidence(false)}>Appearance</button><button aria-pressed={evidence} onClick={() => setEvidence(true)}>Evidence</button></div><div className="row"><button aria-label="Rotate scene left" onClick={() => setTurn(a => a - .3)}>↶</button><button aria-label="Rotate scene right" onClick={() => setTurn(a => a + .3)}>↷</button></div></div>
      <div className="scene-caption"><span>{evidence ? 'Green: observed · Amber: low confidence · Blue: inferred fill' : caption}</span><span>{meta.scale ?? ''}</span></div>
    </div>
    <div className="visual-footnote">
      <span>{meta.credit ?? 'REAL GEOMETRY.'}</span>
      {missionLink ? <Link to={missionLink}>Explore this mission ↗</Link> : <Link to="/missions">Open the mission library ↗</Link>}
    </div>
  </>
}
