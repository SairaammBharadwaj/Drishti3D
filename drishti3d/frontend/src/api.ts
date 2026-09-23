// Typed client for the Drishti3D backend API.
const BASE = (import.meta.env.VITE_API_BASE as string | undefined) ?? ''

export type Vec3 = [number, number, number]

export interface Project {
  id: string
  name: string
  description: string
  status: 'created' | 'processing' | 'done' | 'failed'
  created_at: string
  has_video: boolean
  has_telemetry: boolean
  video_filename: string | null
  telemetry_filename: string | null
  intrinsics: Intrinsics | null
}

export interface Intrinsics {
  fx: number
  fy: number
  cx: number
  cy: number
}

export interface Job {
  id: string
  project_id: string
  status: 'queued' | 'running' | 'done' | 'failed'
  stage: string
  progress: number
  message: string
  error: string | null
  warnings: string[]
  created_at: string
  updated_at: string
}

export interface AiBackend { name: string; available: boolean; setup: string }
export interface Capabilities {
  engines: { opencv_sfm: boolean; colmap: boolean }
  ai_backends: AiBackend[]
  optional: { mesh_open3d: boolean; las_export: boolean; torch: boolean }
}

export interface CameraEnu { frame_index: number; C: Vec3 }
export interface FrameOrigin { lat0: number; lon0: number; alt0: number }

export interface ModelPayload {
  frame: FrameOrigin
  points: Vec3[]
  colors: Vec3[]
  confidence: number[]
  provenance: number[]
  cameras: CameraEnu[]
  bbox: { min: Vec3; max: Vec3 }
  /** Inferred hole-fill points appended by the API (provenance 6), if any. */
  fill_count?: number
}

export interface Trajectory {
  frame: FrameOrigin
  cameras_enu: CameraEnu[]
  gps_track_wgs84: Vec3[]
  cameras_wgs84: Vec3[]
}

export interface Keyframe { frame_index: number; timestamp: number }
export interface FrameMetric {
  frame_index: number
  timestamp: number
  blur: number
  brightness: number
  dark_frac: number
  bright_frac: number
  motion: number
  accepted: boolean
  reasons: string[]
}

export interface QualityReport {
  input: {
    video: { width: number; height: number; fps: number; duration: number; sha256: string }
    telemetry: { n_valid: number; has_rtk: boolean; warnings: string[] }
    scale_source?: string
  }
  frames: { total_analyzed: number; accepted: number; rejected: number; keyframes: number }
  reconstruction: {
    n_keyframes: number; n_registered: number; registered_fraction: number
    n_points: number; median_reproj_err: number | null
    mean_track_length: number | null; mean_tri_angle: number | null
  }
  cloud: {
    n_points: number; dimensions_m?: Vec3; median_point_spacing_m?: number
    class_counts: Record<string, number>; class_fractions: Record<string, number>
  }
  alignment: {
    scale: number; n_inliers: number; n_total: number
    alignment_rmse_horizontal_m: number; alignment_rmse_vertical_m: number
    scale_source: string; note: string
  } | null
  performance: {
    processing_time_s: number; video_duration_s: number
    processing_to_video_ratio: number | null
  }
  ground_truth_evaluation: {
    surface_accuracy_m: { median: number; mean: number; p90: number; rmse: number }
    dimensional_accuracy: {
      name: string; truth_m: number; measured_m: number | null
      abs_error_m: number | null; pct_error: number | null
    }[]
  } & Record<string, number | object> | null
  warnings: string[]
  limitations: string[]
}

export type MeasurementKind = 'point' | 'distance' | 'height' | 'area'
export interface Measurement {
  id: string
  project_id: string
  kind: MeasurementKind
  value: number | null
  unit: string
  points_enu: Vec3[]
  confidence_note: string
  used_inferred: boolean
  warnings: string[]
  created_at: string
}

export interface ExportList { available: Record<string, string> }

async function j<T>(res: Response): Promise<T> {
  if (!res.ok) {
    let detail = res.statusText
    try { detail = (await res.json()).detail ?? detail } catch { /* ignore */ }
    throw new Error(`${res.status}: ${detail}`)
  }
  return res.json() as Promise<T>
}

export const api = {
  health: () => fetch(`${BASE}/api/health`).then(j<{ status: string }>),
  capabilities: () => fetch(`${BASE}/api/capabilities`).then(j<Capabilities>),

  listProjects: () => fetch(`${BASE}/api/projects`).then(j<Project[]>),
  getProject: (id: string) => fetch(`${BASE}/api/projects/${id}`).then(j<Project>),
  videoUrl: (id: string) => `${BASE}/api/projects/${id}/video`,
  createProject: (name: string, description: string) =>
    fetch(`${BASE}/api/projects`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ name, description }),
    }).then(j<Project>),
  deleteProject: (id: string) =>
    fetch(`${BASE}/api/projects/${id}`, { method: 'DELETE' }).then(j),

  uploadVideo: (id: string, file: File) => {
    const fd = new FormData(); fd.append('file', file)
    return fetch(`${BASE}/api/projects/${id}/video`, { method: 'POST', body: fd }).then(j<Project>)
  },
  uploadTelemetry: (id: string, file: File) => {
    const fd = new FormData(); fd.append('file', file)
    return fetch(`${BASE}/api/projects/${id}/telemetry`, { method: 'POST', body: fd }).then(j<Project>)
  },
  setIntrinsics: (id: string, intr: Intrinsics) => {
    const fd = new FormData()
    fd.append('fx', String(intr.fx)); fd.append('fy', String(intr.fy))
    fd.append('cx', String(intr.cx)); fd.append('cy', String(intr.cy))
    return fetch(`${BASE}/api/projects/${id}/intrinsics`, { method: 'POST', body: fd }).then(j<Project>)
  },

  process: (id: string, body: {
    preset: string; mask_backend: string; do_mesh: boolean; densify?: string; intrinsics?: Intrinsics
  }) => fetch(`${BASE}/api/projects/${id}/process`, {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  }).then(j<Job>),

  getJob: (id: string) => fetch(`${BASE}/api/jobs/${id}`).then(j<Job>),
  eventsUrl: (jobId: string) => `${BASE}/api/jobs/${jobId}/events`,

  quality: (id: string) => fetch(`${BASE}/api/projects/${id}/quality`).then(j<QualityReport>),
  trajectory: (id: string) => fetch(`${BASE}/api/projects/${id}/trajectory`).then(j<Trajectory>),
  model: (id: string) => fetch(`${BASE}/api/projects/${id}/model`).then(j<ModelPayload>),

  /**
   * Every point, not the 120,000-point preview.
   *
   * `viewer.json` is capped because JSON is ruinous for this -- 2.69M points
   * is about 148 MB as text against 6.6 MB capped. The cap was never a
   * rendering limit; three.js draws millions of points comfortably. This is
   * the same cloud packed little-endian at 16 bytes per point:
   *
   *   'D3DC' | uint32 version | uint32 count | xyz float32 | rgb u8 | prov u8
   *
   * 43 MB for that cloud, and no parse beyond a typed-array view.
   */
  modelFull: async (id: string, onProgress?: (frac: number) => void) => {
    const res = await fetch(`${BASE}/api/projects/${id}/model.bin`)
    if (!res.ok) throw new Error(`model.bin: ${res.status}`)
    const total = Number(res.headers.get('Content-Length') || 0)
    let buf: ArrayBuffer
    if (onProgress && res.body && total) {
      const reader = res.body.getReader()
      const chunks: Uint8Array[] = []
      let got = 0
      for (;;) {
        const { done, value } = await reader.read()
        if (done) break
        chunks.push(value); got += value.length
        onProgress(got / total)
      }
      const merged = new Uint8Array(got)
      let at = 0
      for (const c of chunks) { merged.set(c, at); at += c.length }
      buf = merged.buffer
    } else {
      buf = await res.arrayBuffer()
    }
    const view = new DataView(buf)
    const magic = String.fromCharCode(
      view.getUint8(0), view.getUint8(1), view.getUint8(2), view.getUint8(3))
    if (magic !== 'D3DC') throw new Error(`unexpected cloud format '${magic}'`)
    const version = view.getUint32(4, true)
    if (version !== 1) throw new Error(`cloud format version ${version} not supported`)
    const n = view.getUint32(8, true)
    let off = 12
    const xyz = new Float32Array(buf, off, n * 3); off += n * 12
    const rgb = new Uint8Array(buf, off, n * 3); off += n * 3
    const provenance = new Uint8Array(buf, off, n)
    return { n, xyz, rgb, provenance }
  },
  keyframes: (id: string) => fetch(`${BASE}/api/projects/${id}/keyframes`).then(j<Keyframe[]>),
  frameMetrics: (id: string) => fetch(`${BASE}/api/projects/${id}/frame_metrics`).then(j<FrameMetric[]>),
  exports: (id: string) => fetch(`${BASE}/api/projects/${id}/exports`).then(j<ExportList>),
  exportUrl: (id: string, key: string) => `${BASE}/api/projects/${id}/exports/${key}`,

  createMeasurement: (id: string, body: {
    kind: MeasurementKind; points: Vec3[]; allow_inferred: boolean
  }) => fetch(`${BASE}/api/projects/${id}/measurements`, {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  }).then(j<Measurement>),
  listMeasurements: (id: string) =>
    fetch(`${BASE}/api/projects/${id}/measurements`).then(j<Measurement[]>),
  deleteMeasurement: (id: string, mid: string) =>
    fetch(`${BASE}/api/projects/${id}/measurements/${mid}`, { method: 'DELETE' }).then(j),

  // --- measurement questions ---------------------------------------------- //
  listQuestions: (id: string) =>
    fetch(`${BASE}/api/projects/${id}/questions`).then(j<Question[]>),
  createQuestion: (id: string, body: {
    kind: MeasurementKind; points: Vec3[]; tolerance_m: number | null
    label?: string; threshold_m?: number | null; allow_inferred?: boolean
  }) => fetch(`${BASE}/api/projects/${id}/questions`, {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  }).then(j<Question>),
  /** Changes only the requirement. The measurement is re-decided, not re-measured. */
  setTolerance: (id: string, qid: string, tolerance_m: number) =>
    fetch(`${BASE}/api/projects/${id}/questions/${qid}`, {
      method: 'PATCH', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ tolerance_m }),
    }).then(j<Question>),
  deleteQuestion: (id: string, qid: string) =>
    fetch(`${BASE}/api/projects/${id}/questions/${qid}`, { method: 'DELETE' }).then(j),
  questionEvidence: (id: string, qid: string) =>
    fetch(`${BASE}/api/projects/${id}/questions/${qid}/evidence`).then(j<QuestionEvidence>),
  refineQuestion: (id: string, qid: string, budget_frames = 4) =>
    fetch(`${BASE}/api/projects/${id}/questions/${qid}/refine`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ budget_frames }),
    }).then(j<Refinement>),
  listRefinements: (id: string, qid: string) =>
    fetch(`${BASE}/api/projects/${id}/questions/${qid}/refinements`).then(j<Refinement[]>),
}


// --- Measurement questions (the Tolerance Lens) ---------------------------- //
// A question is what the operator asked; a result is what the backend decided
// about it. They are separate because changing the tolerance re-decides the
// same measurement rather than making a new one.

export type QuestionStatus =
  | 'meets_requirement' | 'estimated_only' | 'needs_refinement' | 'not_observable'

export interface QuestionResult {
  id: string
  value: number | null
  unit: string
  sigma: number | null
  interval_half_width: number | null
  interval_level: number
  /** 'calibrated' or 'uncalibrated_sensitivity' — what the interval means. */
  interval_basis: string
  status: QuestionStatus
  status_reasons: string[]
  dominant_limitation: string | null
  threshold_result: 'above' | 'below' | 'indeterminate' | null
  evidence: Record<string, unknown>
  artifact_version: string | null
  /**
   * The reconstruction was rebuilt after this answer was computed. The value
   * is not wrong; it describes geometry that no longer exists. Re-asking the
   * question against the current artifacts is what makes it current.
   */
  superseded?: boolean
  warnings: string[]
  created_at: string
}

export interface Guidance {
  reason: string
  explanation: string
  next_action: string
}

export interface Question {
  id: string
  project_id: string
  kind: MeasurementKind
  label: string
  points_enu: Vec3[]
  tolerance_m: number | null
  interval_level: number
  threshold_m: number | null
  threshold_direction: string
  allow_inferred: boolean
  notes: string
  created_at: string
  updated_at: string
  result: QuestionResult | null
  guidance: Guidance[]
}

export interface EvidenceFrame {
  camera_index: number
  frame_index: number | null
  /** True when this frame measured the point, rather than merely seeing it. */
  measured: boolean
  pixel: [number, number] | null
  distance_m: number
  min_separation_from_selected_deg: number
}

export interface QuestionEvidence {
  question_id: string
  /** 'triangulated_observations' can license acceptance; 'frustum_upper_bound' cannot. */
  support_basis: string
  endpoints: {
    index: number
    point_enu: Vec3
    basis: string
    n_measuring_views: number
    n_candidate_views: number
    measured_ray_separation_deg: number | null
    max_ray_separation_deg: number
    within_established_coverage: boolean
    frames: EvidenceFrame[]
    /**
     * How this endpoint's support was recorded. A sparse row's pixel was
     * measured in that image by a feature detector; a dense row's pixel is the
     * fused point projected back into an image `stereo_fusion` recorded as
     * contributing. Both establish that the image contributed, but only the
     * first is an original image measurement.
     *
     * `kinds_recorded` is false for artifacts written before the distinction
     * existed -- their counts are an honest default, not a measurement.
     */
    observation_kinds?: {
      sparse_feature_observation: number
      dense_fusion_contributor: number
      kinds_recorded: boolean
    }
  }[]
  note: string
}

export interface Refinement {
  id: string
  question_id: string
  parent_measurement_id: string | null
  result_measurement_id: string | null
  improved: boolean
  n_considered: number
  n_added: number
  termination_reason: string
  wall_seconds: number
  before: Record<string, unknown>
  after: Record<string, unknown>
  added_frames: { frame_index: number; pnp_inliers: number; pixel: number[] }[]
  rejected: { reason: string; n_frames?: number; explanation: string }[]
  notes: string[]
  created_at: string
}

// Provenance legend shared across the app.
export const PROVENANCE: { code: number; key: string; label: string; color: Vec3 }[] = [
  { code: 0, key: 'OBSERVED_HIGH_CONFIDENCE', label: 'Observed · high confidence', color: [46, 204, 113] },
  { code: 1, key: 'OBSERVED_LOW_CONFIDENCE', label: 'Observed · low confidence', color: [241, 196, 15] },
  { code: 2, key: 'AI_ASSISTED', label: 'AI-assisted / inferred', color: [155, 89, 182] },
  { code: 3, key: 'DYNAMIC_EXCLUDED', label: 'Dynamic · excluded', color: [231, 76, 60] },
  { code: 4, key: 'UNOBSERVED', label: 'Unobserved', color: [127, 140, 141] },
  { code: 5, key: 'AI_GEOMETRICALLY_VERIFIED', label: 'AI-inferred · multi-view verified', color: [26, 188, 156] },
  // Surface laid across holes (mostly water) from the observed rim. Never measured.
  { code: 6, key: 'INFERRED_FILL', label: 'Inferred fill · water / holes', color: [52, 120, 219] },
]

// Local ENU (metres) -> approximate WGS84, for coordinate readouts.
export function enuToLatLon(frame: FrameOrigin, e: number, n: number): { lat: number; lon: number } {
  const R = 6378137
  const lat = frame.lat0 + (n / R) * (180 / Math.PI)
  const lon = frame.lon0 + (e / (R * Math.cos((frame.lat0 * Math.PI) / 180))) * (180 / Math.PI)
  return { lat, lon }
}
