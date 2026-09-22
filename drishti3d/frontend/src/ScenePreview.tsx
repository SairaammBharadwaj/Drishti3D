import { useEffect, useRef, useState } from 'react'

// Small, deterministically sampled copy of the bundled research scene.
// Full geometry and inspection controls remain in the research lab.
export default function ScenePreview() {
  const canvas = useRef<HTMLCanvasElement>(null)
  const [cloud, setCloud] = useState<DataView | null>(null)
  const [error, setError] = useState(false)
  const [evidence, setEvidence] = useState(false)
  const [angle, setAngle] = useState(-.65)
  useEffect(() => {
    const abort = new AbortController()
    fetch('/showcase/preview.bin', { signal: abort.signal }).then(r => {
      if (!r.ok) throw new Error('Scene unavailable')
      return r.arrayBuffer()
    }).then(b => setCloud(new DataView(b))).catch(() => { if (!abort.signal.aborted) setError(true) })
    return () => abort.abort()
  }, [])
  useEffect(() => {
    const el = canvas.current
    if (!el || !cloud) return
    const draw = () => {
      const w = el.clientWidth, h = el.clientHeight, dpr = Math.min(devicePixelRatio || 1, 2)
      el.width = w * dpr; el.height = h * dpr
      const ctx = el.getContext('2d')
      if (!ctx) return
      ctx.scale(dpr, dpr); ctx.clearRect(0, 0, w, h)
      const scale = Math.min(w / 9, h / 5.5), cos = Math.cos(angle), sin = Math.sin(angle)
      const points: {x: number; y: number; z: number; color: string; size: number}[] = []
      for (let i = 0; i < cloud.byteLength; i += 16) {
        const x = cloud.getFloat32(i, true) - .51, y = cloud.getFloat32(i + 4, true) + .18, z = cloud.getFloat32(i + 8, true) - .59
        const rx = x * cos - z * sin, rz = x * sin + z * cos
        const measured = cloud.getUint8(i + 15) === 1
        points.push({ x: w / 2 + rx * scale, y: h * .49 + (y * .8 + rz * .6) * scale, z: rz,
          color: evidence ? (measured ? '#b7e773' : '#9f8db9') : `rgb(${cloud.getUint8(i+12)},${cloud.getUint8(i+13)},${cloud.getUint8(i+14)})`, size: measured && evidence ? 1.8 : 1.5 })
      }
      points.sort((a, b) => b.z - a.z)
      for (const p of points) { ctx.fillStyle = p.color; ctx.fillRect(p.x, p.y, p.size, p.size) }
    }
    const observer = new ResizeObserver(draw); observer.observe(el); draw()
    return () => observer.disconnect()
  }, [cloud, evidence, angle])
  return <div className="scene-preview">
    <div className="scene-top"><span className="eyebrow"><i className="status-dot" /> SAVED RESEARCH SCENE</span><span className="mono">NB / 01</span></div>
    <div className="scene-reticle" aria-hidden="true" />
    <canvas ref={canvas} role="img" aria-label={`Sampled 3D reconstruction of Gymnasium Neubiberg, ${evidence ? 'green measured and purple AI-assisted geometry' : 'original point colours'}. Use the rotate buttons to change the view.`} />
    {!cloud && <div className="scene-loading" role="status">{error ? 'Preview unavailable. Explore the research lab below.' : 'Loading the reconstructed scene…'}</div>}
    <div className="scene-controls"><div className="segmented" aria-label="Scene colouring"><button aria-pressed={!evidence} onClick={() => setEvidence(false)}>Appearance</button><button aria-pressed={evidence} onClick={() => setEvidence(true)}>Evidence</button></div><div className="row"><button aria-label="Rotate scene left" onClick={() => setAngle(a => a - .3)}>↶</button><button aria-label="Rotate scene right" onClick={() => setAngle(a => a + .3)}>↷</button></div></div>
    <div className="scene-caption"><span>{evidence ? 'Green: triangulated · Purple: AI-assisted' : 'Gymnasium Neubiberg · sampled point cloud'}</span><span>Relative scale</span></div>
  </div>
}
