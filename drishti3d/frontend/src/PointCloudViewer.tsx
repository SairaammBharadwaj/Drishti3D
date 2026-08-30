import { useEffect, useRef } from 'react'
import * as THREE from 'three'
import { TrackballControls } from 'three/examples/jsm/controls/TrackballControls.js'
import { PROVENANCE, type ModelPayload, type Vec3 } from './api'

interface Props {
  model: ModelPayload
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
  const ctx = useRef<{
    renderer: THREE.WebGLRenderer
    scene: THREE.Scene
    camera: THREE.PerspectiveCamera
    controls: TrackballControls
    points: THREE.Points
    basePositions: Float32Array
    trueColors: Float32Array
    provColors: Float32Array
    provCodes: number[]
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

    const renderer = new THREE.WebGLRenderer({ antialias: true })
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

    const n = props.model.points.length
    const basePositions = new Float32Array(n * 3)
    const trueColors = new Float32Array(n * 3)
    const provColors = new Float32Array(n * 3)
    const provCodes = props.model.provenance
    const center = new THREE.Vector3()
    for (let i = 0; i < n; i++) {
      const p = props.model.points[i]
      basePositions[i * 3] = p[0]
      basePositions[i * 3 + 1] = p[1]
      basePositions[i * 3 + 2] = p[2]
      center.add(new THREE.Vector3(p[0], p[1], p[2]))
      const c = props.model.colors[i]
      trueColors[i * 3] = c[0] / 255
      trueColors[i * 3 + 1] = c[1] / 255
      trueColors[i * 3 + 2] = c[2] / 255
      const pc = PROVENANCE[provCodes[i]]?.color ?? [200, 200, 200]
      provColors[i * 3] = pc[0] / 255
      provColors[i * 3 + 1] = pc[1] / 255
      provColors[i * 3 + 2] = pc[2] / 255
    }
    if (n > 0) center.multiplyScalar(1 / n)

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
  }, [props.model])

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
  }, [props.colorMode, props.visibleProvenance])

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

  return <div ref={mountRef} style={{ width: '100%', height: '100%' }} />
}
