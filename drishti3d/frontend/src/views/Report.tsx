import { useEffect, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { api, PROVENANCE, type QualityReport } from '../api'

export default function Report() {
  const { id = '' } = useParams()
  const [q, setQ] = useState<QualityReport | null>(null)
  const [err, setErr] = useState<string | null>(null)
  useEffect(() => { api.quality(id).then(setQ).catch((e) => setErr(String(e))) }, [id])

  if (err) return <div className="container"><div className="notebox warn">{err}</div></div>
  if (!q) return <div className="container"><div className="muted">Loading report…</div></div>

  const gte = q.ground_truth_evaluation
  const dims = gte?.dimensional_accuracy

  return (
    <div className="container report-page">
      <div className="report-heading">
        <div><p className="report-kicker">Reconstruction evidence</p><h1>Evidence report</h1><p>Quality, provenance, and limits for this reconstruction.</p></div>
        <div className="row">
          <Link to={`/projects/${id}`}><button>← Workspace</button></Link>
          <a href={api.exportUrl(id, 'report_html')} target="_blank" rel="noreferrer"><button>Open HTML</button></a>
          <a href={api.exportUrl(id, 'report_json')}><button>Download JSON</button></a>
        </div>
      </div>

      <div className="notebox" style={{ margin: '12px 0' }}>
        Scale source: <strong className="mono">{q.input.scale_source ?? q.alignment?.scale_source ?? 'relative'}</strong>.
        {' '}Absolute accuracy is GPS-limited unless RTK/PPK or GCPs are supplied.
      </div>

      <div className="grid" style={{ gridTemplateColumns: '1fr 1fr' }}>
        <Section title="Input">
          <KV k="Resolution" v={`${q.input.video.width}×${q.input.video.height}`} />
          <KV k="Duration" v={`${q.input.video.duration.toFixed(2)} s`} />
          <KV k="FPS" v={q.input.video.fps.toFixed(2)} />
          <KV k="Video SHA-256" v={q.input.video.sha256.slice(0, 16) + '…'} mono />
          <KV k="Telemetry samples" v={q.input.telemetry.n_valid} />
          <KV k="RTK present" v={String(q.input.telemetry.has_rtk)} />
        </Section>

        <Section title="Frames">
          <KV k="Analyzed" v={q.frames.total_analyzed} />
          <KV k="Accepted" v={q.frames.accepted} />
          <KV k="Rejected" v={q.frames.rejected} />
          <KV k="Keyframes" v={q.frames.keyframes} />
        </Section>

        <Section title="Reconstruction">
          <KV k="Registered" v={`${q.reconstruction.n_registered}/${q.reconstruction.n_keyframes}`} />
          <KV k="Points" v={q.cloud.n_points.toLocaleString()} />
          <KV k="Median reproj err" v={num(q.reconstruction.median_reproj_err, 3, 'px')} />
          <KV k="Mean track length" v={num(q.reconstruction.mean_track_length, 2)} />
          <KV k="Mean tri. angle" v={num(q.reconstruction.mean_tri_angle, 2, '°')} />
          <KV k="Model dimensions" v={q.cloud.dimensions_m ? q.cloud.dimensions_m.map((d) => d.toFixed(1)).join(' × ') + ' m' : 'n/a'} />
        </Section>

        <Section title="GPS alignment">
          {q.alignment ? <>
            <KV k="Scale" v={q.alignment.scale.toFixed(4)} />
            <KV k="Inliers" v={`${q.alignment.n_inliers}/${q.alignment.n_total}`} />
            <KV k="Horizontal RMSE" v={`${q.alignment.alignment_rmse_horizontal_m.toFixed(3)} m`} />
            <KV k="Vertical RMSE" v={`${q.alignment.alignment_rmse_vertical_m.toFixed(3)} m`} />
          </> : <div className="muted">Relative scale only (insufficient GPS correspondences).</div>}
        </Section>
      </div>

      <Section title="Provenance distribution">
        {PROVENANCE.map((p) => {
          const frac = q.cloud.class_fractions?.[p.key] ?? 0
          return (
            <div key={p.code} style={{ margin: '6px 0' }}>
              <div className="spread" style={{ fontSize: 13 }}>
                <span><span className="swatch" style={{ background: `rgb(${p.color.join(',')})`, display: 'inline-block', verticalAlign: 'middle', marginRight: 6 }} />{p.label}</span>
                <span className="mono">{(frac * 100).toFixed(1)}%</span>
              </div>
              <div className="bar"><span style={{ width: `${frac * 100}%`, background: `rgb(${p.color.join(',')})` }} /></div>
            </div>
          )
        })}
      </Section>

      {gte && (
        <Section title="Independent accuracy (ground-truth fixture)">
          <KV k="Surface accuracy (median)" v={`${gte.surface_accuracy_m.median.toFixed(3)} m`} />
          <KV k="Surface accuracy (p90)" v={`${gte.surface_accuracy_m.p90.toFixed(3)} m`} />
          {dims && dims.length > 0 && (
            <table style={{ marginTop: 8 }}>
              <thead><tr><th>Reference</th><th>Truth</th><th>Measured</th><th>Error</th></tr></thead>
              <tbody>
                {dims.map((d) => (
                  <tr key={d.name}>
                    <td>{d.name}</td>
                    <td>{d.truth_m.toFixed(3)} m</td>
                    <td>{d.measured_m == null ? '—' : d.measured_m.toFixed(3) + ' m'}</td>
                    <td>{d.pct_error == null ? '—' : d.pct_error.toFixed(2) + '%'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </Section>
      )}

      <Section title="Performance">
        <KV k="Processing time" v={`${q.performance.processing_time_s.toFixed(1)} s`} />
        <KV k="Processing / video ratio" v={num(q.performance.processing_to_video_ratio, 2, '×')} />
      </Section>

      {q.warnings.length > 0 && (
        <Section title="Warnings">
          <ul>{q.warnings.map((w, i) => <li key={i} className="warn">{w}</li>)}</ul>
        </Section>
      )}

      <Section title="Known limitations">
        <ul>{q.limitations.map((l, i) => <li key={i} className="muted">{l}</li>)}</ul>
      </Section>

      <div className="muted" style={{ fontSize: 12, marginTop: 20 }}>
        Generated by Drishti3D. Not an official NTRO product. Figures reflect this run's inputs only.
      </div>
    </div>
  )
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return <section className="card report-section"><h2>{title}</h2>{children}</section>
}
function KV({ k, v, mono }: { k: string; v: React.ReactNode; mono?: boolean }) {
  return <div className="kv"><span className="k">{k}</span><span className={mono ? 'mono' : ''}>{v}</span></div>
}
function num(v: number | null | undefined, d: number, unit = ''): string {
  return v == null ? 'not available' : `${v.toFixed(d)}${unit ? ' ' + unit : ''}`
}
