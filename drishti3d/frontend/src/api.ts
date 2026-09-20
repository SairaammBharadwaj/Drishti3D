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
}

// Provenance legend shared across the app.
export const PROVENANCE: { code: number; key: string; label: string; color: Vec3 }[] = [
  { code: 0, key: 'OBSERVED_HIGH_CONFIDENCE', label: 'Observed · high confidence', color: [46, 204, 113] },
  { code: 1, key: 'OBSERVED_LOW_CONFIDENCE', label: 'Observed · low confidence', color: [241, 196, 15] },
  { code: 2, key: 'AI_ASSISTED', label: 'AI-assisted / inferred', color: [155, 89, 182] },
  { code: 3, key: 'DYNAMIC_EXCLUDED', label: 'Dynamic · excluded', color: [231, 76, 60] },
  { code: 4, key: 'UNOBSERVED', label: 'Unobserved', color: [127, 140, 141] },
]

// Local ENU (metres) -> approximate WGS84, for coordinate readouts.
export function enuToLatLon(frame: FrameOrigin, e: number, n: number): { lat: number; lon: number } {
  const R = 6378137
  const lat = frame.lat0 + (n / R) * (180 / Math.PI)
  const lon = frame.lon0 + (e / (R * Math.cos((frame.lat0 * Math.PI) / 180))) * (180 / Math.PI)
  return { lat, lon }
}
