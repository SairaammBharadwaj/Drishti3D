import type { QualityReport } from './api'

export function hasInsufficientGeometry(q: QualityReport) {
  return q.cloud.n_points < 10 || q.reconstruction.n_registered < 3
}

export default function ReconstructionNotice({ quality }: { quality: QualityReport | null }) {
  if (!quality || !hasInsufficientGeometry(quality)) return null
  return <div className="notebox warn" role="alert">
    <strong>Processing finished, but there is too little geometry to show a usable scene.</strong>
    <div>This run produced {quality.cloud.n_points} points and recovered {quality.reconstruction.n_registered} of {quality.reconstruction.n_keyframes} camera frames. 100% is processing progress, not reconstruction quality.</div>
    <div>Use a continuous shot with overlapping views. Edited montages and scene cuts can prevent reconstruction.</div>
  </div>
}
