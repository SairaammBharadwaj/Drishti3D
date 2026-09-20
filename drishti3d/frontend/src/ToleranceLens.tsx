import { useCallback, useEffect, useState } from 'react'
import {
  api, type Question, type QuestionEvidence, type QuestionStatus,
  type Refinement, type MeasurementKind, type Vec3,
} from './api'

/**
 * The Tolerance Lens.
 *
 * Every status, interval and reason shown here comes from the backend. Nothing
 * on this panel decides whether a measurement is acceptable — a status computed
 * from rendered vertices would be a statement about the viewer's geometry
 * rather than about the evidence, which is the one thing this product must not
 * do.
 */

const STATUS_LABEL: Record<QuestionStatus, string> = {
  meets_requirement: 'Meets requirement',
  estimated_only: 'Estimated only',
  needs_refinement: 'Needs refinement',
  not_observable: 'Not observable',
}

/** Tolerances an operator is likely to ask for, in metres. */
const TOLERANCE_STEPS = [0.02, 0.05, 0.1, 0.2, 0.5, 1, 2, 5]

function fmt(v: number | null | undefined, digits = 3, unit = '') {
  return v == null || !Number.isFinite(v) ? '—' : `${v.toFixed(digits)}${unit}`
}

function StatusChip({ status }: { status: QuestionStatus }) {
  return <span className={`qchip q-${status.replace(/_/g, '-')}`}>{STATUS_LABEL[status]}</span>
}

function Card({ q, projectId, onChanged, onDelete }: {
  q: Question; projectId: string
  onChanged: (q: Question) => void; onDelete: (id: string) => void
}) {
  const [evidence, setEvidence] = useState<QuestionEvidence | null>(null)
  const [showEvidence, setShowEvidence] = useState(false)
  const [refining, setRefining] = useState(false)
  const [refinement, setRefinement] = useState<Refinement | null>(null)
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState<string | null>(null)
  const r = q.result

  const setTol = async (t: number) => {
    setBusy(true); setErr(null)
    try { onChanged(await api.setTolerance(projectId, q.id, t)) }
    catch (e) { setErr(String(e)) } finally { setBusy(false) }
  }

  const loadEvidence = async () => {
    setShowEvidence((v) => !v)
    if (evidence) return
    try { setEvidence(await api.questionEvidence(projectId, q.id)) }
    catch (e) { setErr(String(e)) }
  }

  const improve = async () => {
    setRefining(true); setErr(null)
    try {
      const run = await api.refineQuestion(projectId, q.id, 4)
      setRefinement(run)
      onChanged(await api.listQuestions(projectId).then(
        (all) => all.find((x) => x.id === q.id) ?? q))
    } catch (e) { setErr(String(e)) } finally { setRefining(false) }
  }

  return (
    <div className="qcard">
      <div className="spread">
        <strong>{q.label || q.kind}</strong>
        {r && <StatusChip status={r.status} />}
      </div>

      <div className="qvalue mono">
        {r?.value == null ? '—' : `${r.value.toFixed(3)} ${r.unit}`}
        {r?.interval_half_width != null &&
          <span className="muted"> ± {r.interval_half_width.toFixed(3)} ({r.interval_level}%)</span>}
      </div>
      {r && r.interval_basis !== 'calibrated' && (
        <div className="muted" style={{ fontSize: 12 }}>
          Interval is a sensitivity estimate, not a coverage-checked one.
        </div>
      )}

      <label style={{ marginTop: 8, display: 'block' }}>
        Required tolerance: <span className="mono">
          {q.tolerance_m == null ? 'none' : `±${q.tolerance_m} m`}</span>
      </label>
      <input
        className="slider" type="range" min={0} max={TOLERANCE_STEPS.length - 1} step={1}
        value={Math.max(0, TOLERANCE_STEPS.indexOf(q.tolerance_m ?? 0.2))}
        disabled={busy}
        onChange={(e) => setTol(TOLERANCE_STEPS[+e.target.value])}
      />
      <div className="muted" style={{ fontSize: 12 }}>
        Changing this re-decides the same measurement. It does not re-measure.
      </div>

      {r?.threshold_result && (
        <div className="notebox" style={{ marginTop: 8 }}>
          Threshold: <strong>{r.threshold_result}</strong>
        </div>
      )}

      {q.guidance.length > 0 && (
        <div style={{ marginTop: 10 }}>
          <div className="muted" style={{ fontSize: 12 }}>
            {r?.dominant_limitation
              ? <>Dominant limitation: <span className="mono">{r.dominant_limitation}</span></>
              : 'Limitations'}
          </div>
          {q.guidance.map((g) => (
            <div key={g.reason} className="qreason">
              <div>{g.explanation}</div>
              <div className="muted">→ {g.next_action}</div>
            </div>
          ))}
        </div>
      )}

      <div className="row" style={{ marginTop: 10 }}>
        <button onClick={loadEvidence}>{showEvidence ? 'Hide evidence' : 'Show evidence'}</button>
        <button className="primary" disabled={refining} onClick={improve}>
          {refining ? 'Improving…' : 'Improve this measurement'}
        </button>
        <button onClick={() => onDelete(q.id)}>Delete</button>
      </div>

      {err && <div className="warn" style={{ fontSize: 12 }}>⚠ {err}</div>}

      {showEvidence && evidence && (
        <div className="notebox" style={{ marginTop: 8 }}>
          <div className="spread">
            <strong>Evidence</strong>
            <span className="mono">{evidence.support_basis}</span>
          </div>
          <div className="muted" style={{ fontSize: 12 }}>{evidence.note}</div>
          {evidence.endpoints.map((ep) => (
            <div key={ep.index} style={{ marginTop: 6 }}>
              <div className="mono" style={{ fontSize: 12 }}>
                endpoint {ep.index}: {ep.n_measuring_views} measuring / {ep.n_candidate_views} candidate views,
                parallax {fmt(ep.measured_ray_separation_deg ?? ep.max_ray_separation_deg, 1, '°')}
                {ep.within_established_coverage ? '' : ' · outside established coverage'}
              </div>
              <div className="qframes">
                {ep.frames.slice(0, 8).map((f) => (
                  <span key={f.camera_index} className={f.measured ? 'qframe measured' : 'qframe'}>
                    f{f.frame_index}{f.pixel ? ` @${f.pixel.map((x) => Math.round(x)).join(',')}` : ''}
                  </span>
                ))}
              </div>
            </div>
          ))}
        </div>
      )}

      {refinement && (
        <div className="notebox" style={{ marginTop: 8 }}>
          <div className="spread">
            <strong>Refinement</strong>
            <span className="mono">
              {refinement.n_added} of {refinement.n_considered} frames · {refinement.wall_seconds}s
            </span>
          </div>
          {/* Three separate facts on purpose: a cleared blocker, a narrower
              interval and a moved value are different outcomes, and collapsing
              them into one arrow is how a refinement that made things worse
              reads as a success. */}
          <table className="qdiff">
            <tbody>
              <tr><td>value</td>
                <td className="mono">{fmt(refinement.before.value as number)}</td>
                <td className="mono">{fmt(refinement.after.value as number)}</td></tr>
              <tr><td>interval</td>
                <td className="mono">{fmt(refinement.before.interval_half_width as number)}</td>
                <td className="mono">{fmt(refinement.after.interval_half_width as number)}</td></tr>
              <tr><td>views</td>
                <td className="mono">{String(refinement.before.n_supporting_views ?? '—')}</td>
                <td className="mono">{String(refinement.after.n_supporting_views ?? '—')}</td></tr>
              <tr><td>parallax</td>
                <td className="mono">{String(refinement.before.max_ray_separation_deg ?? '—')}°</td>
                <td className="mono">{String(refinement.after.max_ray_separation_deg ?? '—')}°</td></tr>
            </tbody>
          </table>
          <div style={{ fontSize: 12, marginTop: 4 }}>
            {refinement.n_added === 0
              ? <>No frame was recovered — <span className="mono">{refinement.termination_reason}</span></>
              : <>Outcome: {refinement.improved ? 'improved' : 'no improvement'}</>}
          </div>
          {refinement.rejected.filter((x) => x.n_frames).map((x) => (
            <div key={x.reason} className="muted" style={{ fontSize: 12 }}>
              {x.n_frames} frames rejected — {x.explanation}
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

export default function ToleranceLens({ projectId, kind, points, onConsumed }: {
  projectId: string
  /** A selection made in the viewer, ready to become a question. */
  kind: MeasurementKind | null
  points: Vec3[]
  onConsumed: () => void
}) {
  const [questions, setQuestions] = useState<Question[]>([])
  const [filter, setFilter] = useState<QuestionStatus | 'all'>('all')
  const [err, setErr] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  const reload = useCallback(() => {
    api.listQuestions(projectId).then(setQuestions).catch((e) => setErr(String(e)))
  }, [projectId])
  useEffect(reload, [reload])

  const ask = async () => {
    if (!kind || points.length < 2) return
    setBusy(true); setErr(null)
    try {
      const q = await api.createQuestion(projectId, {
        kind, points, tolerance_m: 0.2,
        label: `${kind} ${questions.length + 1}`,
      })
      setQuestions((prev) => [q, ...prev])
      onConsumed()
    } catch (e) { setErr(String(e)) } finally { setBusy(false) }
  }

  const shown = questions.filter(
    (q) => filter === 'all' || q.result?.status === filter)
  const counts = questions.reduce<Record<string, number>>((acc, q) => {
    const s = q.result?.status ?? 'not_observable'
    acc[s] = (acc[s] ?? 0) + 1
    return acc
  }, {})

  return (
    <div>
      <div className="spread"><h3>Tolerance Lens</h3>
        <span className="muted mono">{questions.length}</span></div>

      {kind && points.length >= 2 && (
        <button className="primary" disabled={busy} onClick={ask} style={{ width: '100%' }}>
          Ask this as a question ({kind}, {points.length} points)
        </button>
      )}

      <div className="row" style={{ marginTop: 8, flexWrap: 'wrap' }}>
        {(['all', 'meets_requirement', 'estimated_only', 'needs_refinement', 'not_observable'] as const).map((f) => (
          <button key={f} className={filter === f ? 'active' : ''} onClick={() => setFilter(f)}>
            {f === 'all' ? `all ${questions.length}` : `${STATUS_LABEL[f]} ${counts[f] ?? 0}`}
          </button>
        ))}
      </div>

      {err && <div className="warn" style={{ fontSize: 12 }}>⚠ {err}</div>}
      {questions.length === 0 && (
        <div className="muted" style={{ fontSize: 12, marginTop: 8 }}>
          Pick a distance, height or area on the cloud, then ask it as a question
          with a required tolerance.
        </div>
      )}

      {shown.map((q) => (
        <Card key={q.id} q={q} projectId={projectId}
          onChanged={(nq) => setQuestions((prev) => prev.map((x) => x.id === nq.id ? nq : x))}
          onDelete={async (qid) => {
            await api.deleteQuestion(projectId, qid)
            setQuestions((prev) => prev.filter((x) => x.id !== qid))
          }} />
      ))}
    </div>
  )
}
