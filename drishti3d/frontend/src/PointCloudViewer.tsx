import { useEffect, useRef, useState } from 'react'
import * as THREE from 'three'
import { TrackballControls } from 'three/examples/jsm/controls/TrackballControls.js'
import { PROVENANCE, type ModelPayload, type Vec3 } from './api'

interface Props {
  model: ModelPayload
  /** Every point, packed. When present it replaces the capped preview. */
  full?: { n: number; xyz: Float32Array; rgb: Uint8Array; provenance: Uint8Array } | null
  colorMode: 'true' | 'provenance'
  splat: boolean            // render soft gaussian surface splats vs hard points
  pointSize: number
  visibleProvenance: Set<number>
  picking: boolean
  onPick: (enu: Vec3) => void
  onHover: (enu: Vec3 | null) => void
  activePoints: Vec3[]      // current in-progress measurement points
  savedLines: Vec3[][]      // completed measurement polylines
}

export default function PointCloudViewer(props: Props) {
  const mountRef = useRef<HTMLDivElement>(null)
  const [unavailable, setUnavailable] = useState(false)
  const ctx = useRef<{
    renderer: THREE.WebGLRenderer
    scene: THREE.Scene
    camera: THREE.PerspectiveCamera
    controls: TrackballControls
    points: THREE.Points
    basePositions: Float32Array
    trueColors: Float32Array
    provColors: Float32Array
    provCodes: Uint8Array
    raycaster: THREE.Raycaster
    radius: number
    markerGroup: THREE.Group
    dispose: () => void
  } | null>(null)

  // ---- one-time scene construction when the model changes -----------------
  useEffect(() => {
    const mount = mountRef.current!
    const w = mount.clientWidth || 800
    const h = mount.clientHeight || 600

    let renderer: THREE.WebGLRenderer
    try {
      renderer = new THREE.WebGLRenderer({ antialias: true })
      setUnavailable(false)
    } catch {
      setUnavailable(true)
      return
    }
    renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2))
    renderer.setSize(w, h)
    renderer.setClearColor(0x05080b, 1)
    mount.appendChild(renderer.domElement)
    renderer.domElement.className = 'viewer-canvas'

    const scene = new THREE.Scene()
    const camera = new THREE.PerspectiveCamera(55, w / h, 0.1, 100000)
    camera.up.set(0, 0, 1)

    // TrackballControls = free arcball rotation (no fixed up-vector), so the
    // model can be spun a full 360 degrees in every axis, including over the top.
    const controls = new TrackballControls(camera, renderer.domElement)
    controls.rotateSpeed = 3.5
    controls.zoomSpeed = 1.2
    controls.panSpeed = 0.8
    controls.staticMoving = false
    controls.dynamicDampingFactor = 0.12

    // Two sources, one loop. `full` is the packed binary cloud -- every point,
    // typed arrays straight off the wire. Without it we use the capped JSON
    // preview. Converting the binary into arrays-of-arrays to share one code
    // path would allocate 2.69M three-element arrays and undo the reason the
    // binary format exists, so the accessors branch instead.
    const full = props.full
    const n = full ? full.n : props.model.points.length
    const basePositions = new Float32Array(n * 3)
    const trueColors = new Float32Array(n * 3)
    const provColors = new Float32Array(n * 3)
    // Kept for the provenance-layer filter below, which needs the class of
    // every point regardless of which source supplied it.
    const provCodes = new Uint8Array(n)
    const center = new THREE.Vector3()
    let cx = 0, cy = 0, cz = 0
    for (let i = 0; i < n; i++) {
      let px: number, py: number, pz: number
      let r: number, g: number, b: number, code: number
      if (full) {
        px = full.xyz[i * 3]; py = full.xyz[i * 3 + 1]; pz = full.xyz[i * 3 + 2]
        r = full.rgb[i * 3]; g = full.rgb[i * 3 + 1]; b = full.rgb[i * 3 + 2]
        code = full.provenance[i]
      } else {
        const p = props.model.points[i]
        px = p[0]; py = p[1]; pz = p[2]
        const c = props.model.colors[i]
        r = c[0]; g = c[1]; b = c[2]
        code = props.model.provenance[i]
      }
      basePositions[i * 3] = px
      basePositions[i * 3 + 1] = py
      basePositions[i * 3 + 2] = pz
      // Accumulated as scalars: allocating a Vector3 per point was tolerable
      // at 120k and is 2.69M allocations here.
      cx += px; cy += py; cz += pz
      trueColors[i * 3] = r / 255
      trueColors[i * 3 + 1] = g / 255
      trueColors[i * 3 + 2] = b / 255
      provCodes[i] = code
      const pc = PROVENANCE[code]?.color ?? [200, 200, 200]
      provColors[i * 3] = pc[0] / 255
      provColors[i * 3 + 1] = pc[1] / 255
      provColors[i * 3 + 2] = pc[2] / 255
    }
    if (n > 0) center.set(cx / n, cy / n, cz / n)

    const bmin = props.model.bbox.min, bmax = props.model.bbox.max
    const radius = Math.max(
      Math.hypot(bmax[0] - bmin[0], bmax[1] - bmin[1], bmax[2] - bmin[2]) / 2, 1)

    const geom = new THREE.BufferGeometry()
    geom.setAttribute('position', new THREE.BufferAttribute(basePositions.slice(), 3))
    geom.setAttribute('color', new THREE.BufferAttribute(trueColors.slice(), 3))
    // soft radial-gaussian sprite for "splat" surface rendering
    const sprite = (() => {
      const s = 64
      const cv = document.createElement('canvas'); cv.width = cv.height = s
      const g = cv.getContext('2d')!
      const grd = g.createRadialGradient(s / 2, s / 2, 0, s / 2, s / 2, s / 2)
      grd.addColorStop(0, 'rgba(255,255,255,1)')
      grd.addColorStop(0.5, 'rgba(255,255,255,0.85)')
      grd.addColorStop(1, 'rgba(255,255,255,0)')
      g.fillStyle = grd; g.fillRect(0, 0, s, s)
      const t = new THREE.CanvasTexture(cv); t.needsUpdate = true
      return t
    })()
    const mat = new THREE.PointsMaterial({
      size: radius * 0.004, vertexColors: true, sizeAttenuation: true,
    })
    mat.userData.sprite = sprite
    const points = new THREE.Points(geom, mat)
    scene.add(points)

    // camera trajectory polyline
    if (props.model.cameras.length > 1) {
      const cg = new THREE.BufferGeometry()
      const cp = new Float32Array(props.model.cameras.length * 3)
      props.model.cameras.forEach((c, i) => {
        cp[i * 3] = c.C[0]; cp[i * 3 + 1] = c.C[1]; cp[i * 3 + 2] = c.C[2]
      })
      cg.setAttribute('position', new THREE.BufferAttribute(cp, 3))
      const line = new THREE.Line(cg, new THREE.LineBasicMaterial({ color: 0x2ea6ff }))
      scene.add(line)
      const camDots = new THREE.Points(cg, new THREE.PointsMaterial({ color: 0x2ea6ff, size: radius * 0.012, sizeAttenuation: true }))
      scene.add(camDots)
    }

    // grid + axes for spatial reference
    const grid = new THREE.GridHelper(radius * 4, 20, 0x223040, 0x151d26)
    grid.rotation.x = Math.PI / 2
    grid.position.set(center.x, center.y, bmin[2])
    scene.add(grid)

    const markerGroup = new THREE.Group()
    scene.add(markerGroup)

    camera.position.set(center.x + radius * 1.6, center.y - radius * 1.8, center.z + radius * 1.4)
    controls.target.copy(center)
    controls.update()

    const raycaster = new THREE.Raycaster()
    raycaster.params.Points = { threshold: radius * 0.01 }

    let raf = 0
    const animate = () => { raf = requestAnimationFrame(animate); controls.update(); renderer.render(scene, camera) }
    animate()

    const onResize = () => {
      const nw = mount.clientWidth, nh = mount.clientHeight
      camera.aspect = nw / nh; camera.updateProjectionMatrix(); renderer.setSize(nw, nh)
      controls.handleResize()
    }
    window.addEventListener('resize', onResize)

    const dispose = () => {
      cancelAnimationFrame(raf)
      window.removeEventListener('resize', onResize)
      controls.dispose(); renderer.dispose()
      geom.dispose(); mat.dispose(); sprite.dispose()
      if (renderer.domElement.parentNode) renderer.domElement.parentNode.removeChild(renderer.domElement)
    }

    ctx.current = {
      renderer, scene, camera, controls, points, basePositions,
      trueColors, provColors, provCodes, raycaster, radius, markerGroup, dispose,
    }
    return dispose
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [props.model, props.full])

  // ---- color mode + provenance visibility --------------------------------
  useEffect(() => {
    const c = ctx.current; if (!c) return
    const src = props.colorMode === 'true' ? c.trueColors : c.provColors
    const colorAttr = c.points.geometry.getAttribute('color') as THREE.BufferAttribute
    const posAttr = c.points.geometry.getAttribute('position') as THREE.BufferAttribute
    const carr = colorAttr.array as Float32Array
    const parr = posAttr.array as Float32Array
    for (let i = 0; i < c.provCodes.length; i++) {
      const visible = props.visibleProvenance.has(c.provCodes[i])
      carr[i * 3] = src[i * 3]; carr[i * 3 + 1] = src[i * 3 + 1]; carr[i * 3 + 2] = src[i * 3 + 2]
      if (visible) {
        parr[i * 3] = c.basePositions[i * 3]
        parr[i * 3 + 1] = c.basePositions[i * 3 + 1]
        parr[i * 3 + 2] = c.basePositions[i * 3 + 2]
      } else {
        parr[i * 3] = NaN; parr[i * 3 + 1] = NaN; parr[i * 3 + 2] = NaN
      }
    }
    colorAttr.needsUpdate = true
    posAttr.needsUpdate = true
    c.points.geometry.computeBoundingSphere()
    // The scene effect above rebuilds the geometry in true colour with every
    // layer shown whenever the model or the full cloud changes, so this has to
    // re-run then too -- otherwise "show all points" silently drops the chosen
    // colour mode and every hidden layer.
  }, [props.colorMode, props.visibleProvenance, props.model, props.full])

  // ---- point size + splat/point render mode ------------------------------
  useEffect(() => {
    const c = ctx.current; if (!c) return
    const m = c.points.material as THREE.PointsMaterial
    if (props.splat) {
      // soft overlapping gaussian discs merge into a photorealistic surface
      m.map = m.userData.sprite
      m.transparent = true
      m.alphaTest = 0.12
      m.depthWrite = true
      m.size = c.radius * 0.004 * props.pointSize * 3.2
    } else {
      m.map = null
      m.transparent = false
      m.alphaTest = 0
      m.depthWrite = true
      m.size = c.radius * 0.004 * props.pointSize
    }
    m.needsUpdate = true
  }, [props.pointSize, props.splat])

  // ---- measurement markers -----------------------------------------------
  useEffect(() => {
    const c = ctx.current; if (!c) return
    while (c.markerGroup.children.length) c.markerGroup.remove(c.markerGroup.children[0])
    const addDot = (p: Vec3, color: number) => {
      const m = new THREE.Mesh(
        new THREE.SphereGeometry(c.radius * 0.012, 12, 12),
        new THREE.MeshBasicMaterial({ color }))
      m.position.set(p[0], p[1], p[2]); c.markerGroup.add(m)
    }
    const addLine = (pts: Vec3[], color: number) => {
      if (pts.length < 2) return
      const g = new THREE.BufferGeometry().setFromPoints(pts.map((p) => new THREE.Vector3(p[0], p[1], p[2])))
      c.markerGroup.add(new THREE.Line(g, new THREE.LineBasicMaterial({ color })))
    }
    props.savedLines.forEach((l) => { addLine(l, 0x2ecc71); l.forEach((p) => addDot(p, 0x2ecc71)) })
    props.activePoints.forEach((p) => addDot(p, 0xff9a3c))
    addLine(props.activePoints, 0xff9a3c)
  }, [props.activePoints, props.savedLines])

  // ---- pointer handlers (pick / hover) -----------------------------------
  useEffect(() => {
    const c = ctx.current; if (!c) return
    const el = c.renderer.domElement
    const toNdc = (e: PointerEvent) => {
      const r = el.getBoundingClientRect()
      return new THREE.Vector2(((e.clientX - r.left) / r.width) * 2 - 1, -((e.clientY - r.top) / r.height) * 2 + 1)
    }
    const intersect = (e: PointerEvent): Vec3 | null => {
      c.raycaster.setFromCamera(toNdc(e), c.camera)
      const hits = c.raycaster.intersectObject(c.points)
      if (!hits.length || hits[0].index == null) return null
      const i = hits[0].index
      return [c.basePositions[i * 3], c.basePositions[i * 3 + 1], c.basePositions[i * 3 + 2]]
    }
    const onMove = (e: PointerEvent) => { if (props.picking) props.onHover(intersect(e)) }
    const onClick = (e: PointerEvent) => {
      if (!props.picking) return
      const p = intersect(e)
      if (p) props.onPick(p)
    }
    el.addEventListener('pointermove', onMove)
    el.addEventListener('pointerdown', onClick)
    el.style.cursor = props.picking ? 'crosshair' : 'grab'
    return () => { el.removeEventListener('pointermove', onMove); el.removeEventListener('pointerdown', onClick) }
  }, [props.picking, props.onPick, props.onHover])

  return <div ref={mountRef} style={{ width: '100%', height: '100%' }}>
    {unavailable && <div className="viewer-unavailable" role="status"><strong>3D rendering is unavailable in this browser.</strong><p>Enable graphics acceleration or use a browser with WebGL support. Your quality report and saved measurements are still available.</p></div>}
  </div>
}
