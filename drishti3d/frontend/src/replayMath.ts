// Pose at a video time, from the solved keyframes (GET /replay). Mirrors
// drishti_recon.replay.pose_at, which is the tested reference: linear in
// position, slerp in rotation, and a label for how far the pose is from a
// solved camera. Kept free of three.js so it runs under plain Node in
// scripts/replay-math.test.ts.

export type Quat = [number, number, number, number]
export interface Key { t: number; frame_index: number; position: [number, number, number]; quaternion: Quat }
export type SyncStatus = 'synced' | 'gap' | 'out_of_range'
export interface Pose {
  status: SyncStatus
  position?: [number, number, number]
  quaternion?: Quat
  frame_index?: number
  dt_to_keyframe_s?: number
  bracket_s?: number
}

export function slerp(a: Quat, b: Quat, t: number): Quat {
  let d = a[0] * b[0] + a[1] * b[1] + a[2] * b[2] + a[3] * b[3]
  let bb = b
  if (d < 0) { bb = [-b[0], -b[1], -b[2], -b[3]]; d = -d }   // short way round
  let wa: number, wb: number
  if (d > 0.9995) { wa = 1 - t; wb = t } else {
    const th = Math.acos(d), s = Math.sin(th)
    wa = Math.sin((1 - t) * th) / s; wb = Math.sin(t * th) / s
  }
  const q: Quat = [wa * a[0] + wb * bb[0], wa * a[1] + wb * bb[1], wa * a[2] + wb * bb[2], wa * a[3] + wb * bb[3]]
  const n = Math.hypot(...q)
  return [q[0] / n, q[1] / n, q[2] / n, q[3] / n]
}

/** Index of the last key with t <= time (binary search); -1 if none. */
function bracket(track: Key[], time: number): number {
  let lo = 0, hi = track.length - 1, ans = -1
  while (lo <= hi) {
    const mid = (lo + hi) >> 1
    if (track[mid].t <= time) { ans = mid; lo = mid + 1 } else hi = mid - 1
  }
  return ans
}

export function poseAt(track: Key[], time: number, maxGap: number): Pose {
  if (!track.length || time < track[0].t || time > track[track.length - 1].t)
    return { status: 'out_of_range' }
  const i = bracket(track, time)
  if (i >= track.length - 1) {
    const k = track[track.length - 1]
    return { status: 'synced', position: k.position, quaternion: k.quaternion, frame_index: k.frame_index, dt_to_keyframe_s: 0 }
  }
  const a = track[i], b = track[i + 1]
  const span = b.t - a.t
  const w = span <= 0 ? 0 : (time - a.t) / span
  const lerp = (u: number, v: number) => (1 - w) * u + w * v
  return {
    status: span > maxGap ? 'gap' : 'synced',
    position: [lerp(a.position[0], b.position[0]), lerp(a.position[1], b.position[1]), lerp(a.position[2], b.position[2])],
    quaternion: slerp(a.quaternion, b.quaternion, w),
    frame_index: (w < 0.5 ? a : b).frame_index,
    dt_to_keyframe_s: Math.min(time - a.t, b.t - time),
    bracket_s: span,
  }
}
