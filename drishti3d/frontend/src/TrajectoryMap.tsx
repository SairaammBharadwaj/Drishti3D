import type { Trajectory } from './api'

// Offline 2D trajectory plot (no external map tiles). Plots the GPS track and
// the reconstructed camera path in a local east/north projection (metres).
export default function TrajectoryMap({ traj }: { traj: Trajectory }) {
  const W = 280, H = 200, pad = 16
  const R = 6378137
  const lat0 = traj.frame.lat0 * Math.PI / 180

  const gps = traj.gps_track_wgs84.map(([la, lo]) => ({
    e: (lo - traj.frame.lon0) * Math.PI / 180 * R * Math.cos(lat0),
    n: (la - traj.frame.lat0) * Math.PI / 180 * R,
  }))
  const cams = traj.cameras_enu.map((c) => ({ e: c.C[0], n: c.C[1] }))
  const all = [...gps, ...cams]
  if (all.length === 0) return <div className="muted">No trajectory.</div>

  const xs = all.map((p) => p.e), ys = all.map((p) => p.n)
  const minX = Math.min(...xs), maxX = Math.max(...xs)
  const minY = Math.min(...ys), maxY = Math.max(...ys)
  const span = Math.max(maxX - minX, maxY - minY, 1)
  const sx = (e: number) => pad + ((e - minX) / span) * (W - 2 * pad)
  const sy = (n: number) => H - pad - ((n - minY) / span) * (H - 2 * pad)

  const path = (pts: { e: number; n: number }[]) =>
    pts.map((p, i) => `${i ? 'L' : 'M'}${sx(p.e).toFixed(1)},${sy(p.n).toFixed(1)}`).join(' ')

  return (
    <svg width={W} height={H} style={{ background: '#05080b', border: '1px solid var(--border)', borderRadius: 6 }}>
      <path d={path(gps)} fill="none" stroke="#f1c40f" strokeWidth={1.5} opacity={0.8} />
      <path d={path(cams)} fill="none" stroke="#2ea6ff" strokeWidth={1.5} />
      {cams.length > 0 && <circle cx={sx(cams[0].e)} cy={sy(cams[0].n)} r={3} fill="#2ecc71" />}
      {cams.length > 0 && <circle cx={sx(cams[cams.length - 1].e)} cy={sy(cams[cams.length - 1].n)} r={3} fill="#e74c3c" />}
      <text x={pad} y={12} fontSize={10} fill="#8a97a5">east/north (m) · start ● end ●</text>
      <text x={pad} y={H - 4} fontSize={10} fill="#f1c40f">GPS</text>
      <text x={pad + 34} y={H - 4} fontSize={10} fill="#2ea6ff">camera path</text>
    </svg>
  )
}
