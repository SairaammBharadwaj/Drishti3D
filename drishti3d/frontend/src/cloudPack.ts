// The browser's decoder for model.pack. The format, and the reference
// decoder this must agree with, are in backend/app/cloud_pack.py. Kept free
// of other imports so Node can run it to check it against that reference.

/** Decode a D3DP pack; `decode` in backend/app/cloud_pack.py is the reference. */
export function decodePack(buf: ArrayBuffer) {
  const view = new DataView(buf)
  const magic = String.fromCharCode(
    view.getUint8(0), view.getUint8(1), view.getUint8(2), view.getUint8(3))
  if (magic !== 'D3DP') throw new Error(`unexpected cloud format '${magic}'`)
  const version = view.getUint32(4, true)
  if (version !== 1) throw new Error(`pack version ${version} not supported`)
  const n = view.getUint32(8, true)
  const origin = [view.getFloat64(16, true), view.getFloat64(24, true), view.getFloat64(32, true)]
  const step = view.getFloat64(40, true)
  const b = new Uint8Array(buf, 48)
  const xyz = new Float32Array(n * 3)
  for (let axis = 0; axis < 3; axis++) {
    const lo = 2 * axis * n, hi = lo + n, o = origin[axis]
    let acc = 0
    for (let i = 0; i < n; i++) {
      acc = (acc + (b[lo + i] | (b[hi + i] << 8))) & 0xffff
      xyz[i * 3 + axis] = o + acc * step
    }
  }
  const at = 6 * n
  const rgb = new Uint8Array(n * 3)
  for (let i = 0; i < n; i++) {
    rgb[i * 3] = b[at + i]; rgb[i * 3 + 1] = b[at + n + i]; rgb[i * 3 + 2] = b[at + 2 * n + i]
  }
  const provenance = b.slice(at + 3 * n, at + 4 * n)
  return { n, xyz, rgb, provenance }
}
