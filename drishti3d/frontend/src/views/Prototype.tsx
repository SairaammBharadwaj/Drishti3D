import { useEffect, useRef, useState } from 'react'
import * as THREE from 'three'
import { PLYLoader } from 'three/examples/jsm/loaders/PLYLoader.js'
import { TrackballControls } from 'three/examples/jsm/controls/TrackballControls.js'

type SceneInfo = { dense_points: number; measured_points: number; camera_count: number; bounds: number[][]; cameras: number[][][]; focals: number[] }
type ViewState = { dense: boolean; measured: boolean; evidence: boolean; size: number; path: boolean }

export default function Prototype() {
  const mount = useRef<HTMLDivElement>(null)
  const root = useRef<HTMLDivElement>(null)
  const control = useRef<{ update: (s: ViewState) => void; view: (i: number) => void } | null>(null)
  const [info, setInfo] = useState<SceneInfo | null>(null)
  const [error, setError] = useState('')
  const [ready, setReady] = useState(false)
  const [state, setState] = useState<ViewState>({ dense: true, measured: false, evidence: false, size: 3, path: false })
  const latest = useRef(state); latest.current = state

  useEffect(() => {
    const host = mount.current!
    let cancelled = false, raf = 0
    let renderer: THREE.WebGLRenderer | undefined
    let controls: TrackballControls | undefined
    let resize: ResizeObserver | undefined
    const geometries: THREE.BufferGeometry[] = []
    const materials: THREE.Material[] = []
    const abort = new AbortController()
    async function load() {
      try {
        const fetchFile = async (name: string) => {
          const response = await fetch(`/prototype/${name}`, { signal: abort.signal })
          if (!response.ok) throw new Error(`Cannot load ${name}: HTTP ${response.status}`)
          return response
        }
        const [metadata, denseBytes, measuredBytes] = await Promise.all([
          fetchFile('scene.json').then(r => r.json()) as Promise<SceneInfo>,
          fetchFile('dense.ply').then(r => r.arrayBuffer()),
          fetchFile('measured.ply').then(r => r.arrayBuffer()),
        ])
        if (cancelled) return
        setInfo(metadata)
        renderer = new THREE.WebGLRenderer({ antialias: true })
        renderer.setPixelRatio(Math.min(devicePixelRatio, 2))
        renderer.setClearColor(0x060b10)
        host.appendChild(renderer.domElement)
        renderer.domElement.className = 'viewer-canvas'
        const scene = new THREE.Scene()
        const center = new THREE.Vector3(...metadata.bounds[0] as [number, number, number]).add(new THREE.Vector3(...metadata.bounds[1] as [number, number, number])).multiplyScalar(.5)
        const radius = new THREE.Vector3(...metadata.bounds[0] as [number, number, number]).distanceTo(new THREE.Vector3(...metadata.bounds[1] as [number, number, number])) / 2
        const camera = new THREE.PerspectiveCamera(55, 1, radius / 10000, radius * 1000)
        controls = new TrackballControls(camera, renderer.domElement)
        controls.rotateSpeed = 2.5; controls.zoomSpeed = 1.1; controls.panSpeed = .8
        const loader = new PLYLoader()
        const cloud = (bytes: ArrayBuffer) => {
          const geometry = loader.parse(bytes); geometries.push(geometry)
          const material = new THREE.PointsMaterial({ vertexColors: true, size: radius * .001, sizeAttenuation: true })
          materials.push(material)
          const points = new THREE.Points(geometry, material); scene.add(points)
          return points
        }
        const dense = cloud(denseBytes), measured = cloud(measuredBytes)
        const trajectory = new THREE.BufferGeometry().setFromPoints(metadata.cameras.map(c => new THREE.Vector3(c[0][3], c[1][3], c[2][3])))
        geometries.push(trajectory)
        const lineMaterial = new THREE.LineBasicMaterial({ color: 0x65d8c5 }); materials.push(lineMaterial)
        const line = new THREE.Line(trajectory, lineMaterial); scene.add(line)
        function view(index: number) {
          if (index < 0) {
            camera.up.set(0, -1, 0)
            camera.position.copy(center).add(new THREE.Vector3(radius * .7, -radius, -radius * 1.1))
            camera.fov = 55; controls!.target.copy(center)
          } else {
            const pose = metadata.cameras[index]
            camera.position.set(pose[0][3], pose[1][3], pose[2][3])
            camera.up.set(-pose[0][1], -pose[1][1], -pose[2][1])
            const forward = new THREE.Vector3(pose[0][2], pose[1][2], pose[2][2])
            const depth = Math.max(radius * .3, center.clone().sub(camera.position).dot(forward))
            controls!.target.copy(camera.position).addScaledVector(forward, depth)
            camera.fov = THREE.MathUtils.radToDeg(2 * Math.atan(144 / metadata.focals[index]))
          }
          camera.updateProjectionMatrix(); camera.lookAt(controls!.target); controls!.update()
        }
        function update(s: ViewState) {
          dense.visible = s.dense; measured.visible = s.measured; line.visible = s.path
          for (const [points, color] of [[dense, 0xb78dff], [measured, 0x65e4b0]] as const) {
            points.material.vertexColors = !s.evidence
            points.material.color.setHex(s.evidence ? color : 0xffffff)
            points.material.size = radius * .001 * s.size
            points.material.needsUpdate = true
          }
        }
        control.current = { update, view }
        resize = new ResizeObserver(() => {
          const w = host.clientWidth, h = host.clientHeight
          if (!w || !h) return
          camera.aspect = w / h; camera.updateProjectionMatrix()
          renderer!.setSize(w, h); controls!.handleResize()
        }); resize.observe(host)
        update(latest.current); view(6)
        const draw = () => { raf = requestAnimationFrame(draw); controls!.update(); renderer!.render(scene, camera) }; draw()
        setReady(true)
      } catch (e) { if (!cancelled) setError(`The 3D scene could not load. ${String(e)}`) }
    }
    void load()
    return () => {
      cancelled = true; abort.abort(); cancelAnimationFrame(raf); resize?.disconnect(); controls?.dispose()
      geometries.forEach(g => g.dispose()); materials.forEach(m => m.dispose())
      renderer?.dispose(); renderer?.domElement.remove(); control.current = null
    }
  }, [])
  useEffect(() => { control.current?.update(state) }, [state])
  const change = (s: Partial<ViewState>) => setState(previous => ({ ...previous, ...s }))

  return <div className="prototype-page" ref={root}>
    <header className="spread prototype-heading"><div><div className="demo-eyebrow">DRISHTI3D / ORIGINAL PROTOTYPE IN 3D</div><h1>Explore the scene behind the video.</h1><p className="muted">The saved dense Gymnasium reconstruction used for the prototype. Rotate, zoom, and move freely through its geometry.</p></div><button onClick={() => {
      const request = document.fullscreenElement ? document.exitFullscreen() : root.current?.requestFullscreen()
      request?.catch(() => setError('Fullscreen is unavailable in this browser.'))
    }}>Fullscreen</button></header>
    <div className="prototype-layout">
      <section className="demo-media prototype-stage">
        <div className="demo-panel-title"><span>INTERACTIVE DENSE POINT CLOUD</span><span>{ready ? '3D scene ready' : 'Loading saved geometry…'}</span></div>
        <div ref={mount} className="prototype-canvas" />
        {!ready && <div className="prototype-loading" role="status">{error || 'Loading the original 838,658-point prototype…'}</div>}
        <div className="demo-media-footer">Drag: rotate · Scroll: zoom · Right-drag: pan · Use a camera button to return to the flight</div>
      </section>
      <aside className="card prototype-controls">
        <h3>Geometry layers</h3>
        <label className="checkline"><input type="checkbox" checked={state.dense} onChange={e => change({ dense: e.target.checked })} /> Dense prototype</label><p className="muted">{info?.dense_points.toLocaleString() ?? '838,658'} points · AI-assisted geometry</p>
        <label className="checkline"><input type="checkbox" checked={state.measured} onChange={e => change({ measured: e.target.checked })} /> Measured reconstruction</label><p className="muted">{info?.measured_points.toLocaleString() ?? '33,624'} triangulated points</p>
        {!state.dense && !state.measured && <p className="notebox">Both layers are hidden. Enable a layer to see the scene.</p>}
        <label className="checkline"><input type="checkbox" checked={state.evidence} onChange={e => change({ evidence: e.target.checked })} /> Colour by evidence</label>
        {state.evidence && <p><span style={{ color: '#b78dff' }}>Purple: AI-assisted</span><br /><span style={{ color: '#65e4b0' }}>Green: measured</span></p>}
        <label htmlFor="prototype-size">Point size</label><input id="prototype-size" className="slider" type="range" min=".3" max="4" step=".1" value={state.size} onChange={e => change({ size: Number(e.target.value) })} />
        <h3>Camera viewpoints</h3><div className="row">
          <button disabled={!ready} onClick={() => control.current?.view(6)}>Demo view</button>
          <button disabled={!ready} onClick={() => control.current?.view(0)}>Flight start</button>
          <button disabled={!ready} onClick={() => control.current?.view(Math.floor((info?.camera_count ?? 32) / 2))}>Mid-flight</button>
          <button disabled={!ready} onClick={() => control.current?.view((info?.camera_count ?? 32) - 1)}>Flight end</button>
          <button disabled={!ready} onClick={() => control.current?.view(-1)}>Overview</button>
        </div><label className="checkline"><input type="checkbox" checked={state.path} onChange={e => change({ path: e.target.checked })} /> Show camera path</label>
        <div className="notebox">Relative scale · no GPS. Dense detail includes AI inference and is not verified survey geometry. Gaps and unseen surfaces remain possible.</div>
        <p className="muted">Loaded from saved prototype assets. Opening this page does not run new inference.</p>
        <a href="/prototype/dense.ply" download>Download dense PLY ↓</a><br /><a href="/prototype/measured.ply" download>Download measured PLY ↓</a>
      </aside>
    </div>
    {ready && error && <p className="notebox warn" role="alert">{error}</p>}
    <details className="card prototype-reference"><summary>Compare with drone_vs_3d_full.mp4</summary><p className="muted">The recorded prototype uses fixed camera viewpoints. The viewer above lets you explore freely.</p><video controls playsInline preload="none" src="/prototype/reference.mp4" /></details>
  </div>
}
