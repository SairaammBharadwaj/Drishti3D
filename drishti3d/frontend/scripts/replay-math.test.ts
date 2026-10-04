// node --test scripts/replay-math.test.ts  (Node >= 22.18 strips the types)
import { test } from 'node:test'
import assert from 'node:assert/strict'
import { poseAt, slerp, type Key } from '../src/replayMath.ts'

const id: [number, number, number, number] = [0, 0, 0, 1]
const yaw90: [number, number, number, number] = [0, 0, Math.SQRT1_2, Math.SQRT1_2]
const track: Key[] = [
  { t: 0, frame_index: 0, position: [0, 0, 50], quaternion: id },
  { t: 1, frame_index: 30, position: [10, 0, 50], quaternion: yaw90 },
  { t: 5, frame_index: 150, position: [20, 0, 50], quaternion: yaw90 },
]

test('scrub interpolates position and rotation', () => {
  const p = poseAt(track, 0.5, 2)
  assert.equal(p.status, 'synced')
  assert.deepEqual(p.position, [5, 0, 50])
  const q = p.quaternion!
  assert.ok(Math.abs(q[2] - Math.sin(Math.PI / 8)) < 1e-9)   // 45 degrees of yaw
})

test('gaps and ranges are labelled like the Python reference', () => {
  assert.equal(poseAt(track, 3, 2).status, 'gap')
  assert.equal(poseAt(track, -0.01, 2).status, 'out_of_range')
  assert.equal(poseAt(track, 5.01, 2).status, 'out_of_range')
  assert.equal(poseAt(track, 5, 2).status, 'synced')
  assert.equal(poseAt([], 1, 2).status, 'out_of_range')
})

test('pause and scrub back are deterministic', () => {
  const a = poseAt(track, 0.7, 2)
  poseAt(track, 4, 2)
  assert.deepEqual(poseAt(track, 0.7, 2), a)
})

test('slerp takes the short way and stays unit length', () => {
  const q = slerp(id, [0, 0, -Math.sin(0.1), -Math.cos(0.1)], 0.5)
  assert.ok(Math.abs(Math.hypot(...q) - 1) < 1e-12)
  assert.ok(Math.abs(q[3]) > 0.99)
})
