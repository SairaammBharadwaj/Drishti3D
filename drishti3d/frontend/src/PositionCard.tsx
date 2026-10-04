import type { PointInfo } from './api'

/** "14RPU1998348741" -> "14R PU 19983 48741": how MGRS is read aloud and written. */
function spacedMgrs(code: string) {
  const m = /^(\d{1,2}[A-Z])([A-Z]{2})(\d+)$/.exec(code)
  if (!m) return code
  const half = m[3].length / 2
  return `${m[1]} ${m[2]} ${m[3].slice(0, half)} ${m[3].slice(half)}`
}

// Every height is named: over Austin sea level and the ellipsoid differ by
// 27 m, over Sardinia by 47 m, and an unnamed height is a guess about which
// it is. A mission whose telemetry never said gets no height at all (DEC-047).
export default function PositionCard({ info }: { info: PointInfo }) {
  if (!info.georeferenced) return <div className="notebox position-card"><strong>Position</strong><p className="muted">{info.note}</p></div>
  const m = (v: number) => `${v.toFixed(2)} m`
  return (
    <div className="notebox position-card">
      <strong>Position</strong>
      <dl>
        <dt>Lat, lon</dt><dd className="mono">{info.lat!.toFixed(6)}, {info.lon!.toFixed(6)}</dd>
        {info.mgrs && <><dt>MGRS</dt><dd className="mono">{spacedMgrs(info.mgrs)}</dd></>}
        {info.utm && <><dt>UTM {info.utm.zone}</dt><dd className="mono">E {info.utm.easting_m.toFixed(1)} N {info.utm.northing_m.toFixed(1)}</dd></>}
        {info.h_msl_m != null && <><dt>Above sea level</dt><dd className="mono">{m(info.h_msl_m)} ({info.h_msl_model})</dd></>}
        {info.h_ellipsoidal_m != null && <><dt>Ellipsoidal</dt><dd className="mono">{m(info.h_ellipsoidal_m)} (WGS84{info.h_ellipsoidal_model ? `, ${info.h_ellipsoidal_model}` : ''})</dd></>}
        {info.h_relative_m != null && <><dt>Above take-off</dt><dd className="mono">{m(info.h_relative_m)}</dd></>}
      </dl>
      {info.height_note && <p className="muted">{info.height_note}</p>}
      {info.placement_note && <p className="muted">{info.placement_note}</p>}
    </div>
  )
}
