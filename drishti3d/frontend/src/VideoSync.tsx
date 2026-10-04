import { useEffect, useRef, useState } from 'react'
import { api, type ReplayTrack } from './api'
import { poseAt, type Pose } from './replayMath'

// Plays the source video and reports the reconstructed camera at the shown
// frame. Poses come from GET /replay already in Three.js convention; between
// keyframes they are interpolated (replayMath.poseAt), and the indicator says
// whether the pose is near a solved camera, bridging a gap, or unavailable.

interface Props {
  projectId: string
  onPose: (pose: Pose | null) => void
  follow: boolean
  onFollow: (on: boolean) => void
}

const LABEL: Record<Pose['status'], string> = {
  synced: 'Synced', gap: 'Gap — interpolated', out_of_range: 'No solved camera here',
}

type FrameVideo = HTMLVideoElement & {
  requestVideoFrameCallback?: (cb: (now: number, meta: { mediaTime: number }) => void) => number
  cancelVideoFrameCallback?: (h: number) => void
}

export default function VideoSync({ projectId, onPose, follow, onFollow }: Props) {
  const ref = useRef<FrameVideo>(null)
  const [track, setTrack] = useState<ReplayTrack | null>(null)
  const [pose, setPose] = useState<Pose | null>(null)
  const [time, setTime] = useState(0)
  const [paused, setPaused] = useState(true)
  const [videoErr, setVideoErr] = useState(false)

  useEffect(() => {
    setTrack(null); setPose(null)
    api.replay(projectId).then(setTrack).catch(() => setTrack({ track: [], max_gap_s: 2, convention: '' }))
  }, [projectId])

  useEffect(() => () => onPose(null), [onPose])

  useEffect(() => {
    const v = ref.current
    if (!v || !track) return
    let handle = 0, raf = 0, live = true
    const update = (t: number) => {
      const p = poseAt(track.track, t, track.max_gap_s)
      setTime(t); setPose(p); onPose(p.status === 'out_of_range' ? null : p)
    }
    // Frame-accurate where the browser reports the presented frame's time;
    // otherwise the playback clock each animation frame.
    const tick = () => {
      if (!live) return
      if (v.requestVideoFrameCallback) {
        handle = v.requestVideoFrameCallback((_n, meta) => { update(meta.mediaTime); tick() })
      } else {
        update(v.currentTime); raf = requestAnimationFrame(tick)
      }
    }
    const onSeek = () => update(v.currentTime)        // scrubbing while paused
    const onPlay = () => setPaused(false)
    const onPause = () => { setPaused(true); update(v.currentTime) }
    v.addEventListener('seeked', onSeek)
    v.addEventListener('play', onPlay)
    v.addEventListener('pause', onPause)
    update(v.currentTime)
    tick()
    return () => {
      live = false
      v.removeEventListener('seeked', onSeek); v.removeEventListener('play', onPlay); v.removeEventListener('pause', onPause)
      if (handle && v.cancelVideoFrameCallback) v.cancelVideoFrameCallback(handle)
      cancelAnimationFrame(raf)
    }
  }, [track, onPose])

  const status = pose?.status ?? 'out_of_range'
  return (
    <div className="video-sync">
      {videoErr
        ? <div className="muted">The original video is not available on this server.</div>
        : <video ref={ref} src={api.videoUrl(projectId)} controls preload="metadata" muted playsInline
            onError={() => setVideoErr(true)} style={{ width: '100%' }} />}
      <div className={`sync-indicator sync-${status}`} role="status" aria-live="polite">
        <span className="sync-dot" />
        <strong>{LABEL[status]}</strong>
        <span className="mono">
          t {time.toFixed(2)} s{paused ? ' · paused' : ''}
          {pose?.dt_to_keyframe_s != null && ` · ${pose.dt_to_keyframe_s.toFixed(2)} s from keyframe ${pose.frame_index}`}
          {status === 'gap' && pose?.bracket_s != null && ` · keyframes ${pose.bracket_s.toFixed(1)} s apart`}
        </span>
      </div>
      {track && track.track.length === 0 && <div className="muted" style={{ fontSize: 12 }}>No solved cameras with video times for this mission.</div>}
      <label className="checkline">
        <input type="checkbox" checked={follow} onChange={(e) => onFollow(e.target.checked)} />
        Fly the 3-D view with the video camera
      </label>
    </div>
  )
}
