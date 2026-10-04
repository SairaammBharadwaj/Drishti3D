"""The full point cloud, packed small enough for a home upload link.

``model.bin`` is 16 bytes a point: float32 ENU, RGB and a provenance code. A
showcase served from a laptop sends it at the laptop's upload speed (~2 MB/s
measured, 2026-09-29), so DJI_1001's 4.5 M points (72 MB) took ~40 s to
appear. The same points as sent here are 2.7x smaller (measured on DJI_1001's
cloud: 62.7 MB to 23.2 MB):

1. Positions are quantised to one uniform step on all three axes, the
   largest extent divided by 65535. That is ~2 cm for a 1.4 km scene, far finer
   than the points are spaced. This is for display only: measurements are
   made on the full-precision cloud on the server, and a picked point is
   snapped to it there.
2. Points are put in Morton (Z-order) order, so neighbours in space are
   neighbours in the stream, and each axis is stored as the difference from
   the previous point, modulo 2**16. Point order carries no meaning; the
   provenance code travels with each point.
3. Everything is stored plane by plane (each axis's low bytes, then its high
   bytes, then R, G, B, provenance), which gzip compresses far better than
   interleaved records.

Layout, little-endian, gzip-compressed as a whole and sent as
application/octet-stream (the browser decompresses it with
DecompressionStream, so Content-Length stays the true download size for the
progress bar)::

    magic   4  'D3DP'        version 4 uint32 (1)
    count   4  uint32        fill    4 uint32 (points of provenance 6)
    origin 24  3 x float64   step    8 float64 (metres)
    dx lo, dx hi, dy lo, dy hi, dz lo, dz hi   count bytes each
    r, g, b, provenance                        count bytes each

``frontend/src/api.ts`` holds the decoder the browser runs; :func:`decode`
here is its reference and is what the tests check.
"""
from __future__ import annotations

import gzip
import struct
import threading

import numpy as np

MAGIC = b"D3DP"
VERSION = 1
_HEADER = struct.Struct("<4sIII3dd")          # 48 bytes
_FILL_CODE = 6


def _spread(v: np.ndarray) -> np.ndarray:
    """Interleave zeros between the bits of a 16-bit value (Morton helper)."""
    x = v.astype(np.uint64) & np.uint64(0x1FFFFF)
    for shift, mask in [(32, 0x1F00000000FFFF), (16, 0x1F0000FF0000FF),
                        (8, 0x100F00F00F00F00F), (4, 0x10C30C30C30C30C3),
                        (2, 0x1249249249249249)]:
        x = (x | (x << np.uint64(shift))) & np.uint64(mask)
    return x


def encode(points: np.ndarray, colors: np.ndarray, provenance: np.ndarray,
           level: int = 6) -> bytes:
    pts = np.asarray(points, dtype=np.float64).reshape(-1, 3)
    n = len(pts)
    rgb = np.asarray(colors, dtype=np.uint8).reshape(n, 3)
    prov = np.asarray(provenance, dtype=np.uint8).reshape(n)
    lo = pts.min(axis=0) if n else np.zeros(3)
    span = float((pts.max(axis=0) - lo).max()) if n else 0.0
    step = span / 65535 if span > 0 else 1e-6
    q = np.clip(np.round((pts - lo) / step), 0, 65535).astype(np.uint32)
    order = np.argsort(_spread(q[:, 0]) | (_spread(q[:, 1]) << np.uint64(1))
                       | (_spread(q[:, 2]) << np.uint64(2)), kind="stable")
    q, rgb, prov = q[order], rgb[order], prov[order]
    delta = (np.diff(q.astype(np.int64), axis=0, prepend=0) & 0xFFFF).astype("<u2")
    planes = []
    for axis in range(3):
        b = np.ascontiguousarray(delta[:, axis]).view(np.uint8).reshape(n, 2)
        planes += [b[:, 0].tobytes(), b[:, 1].tobytes()]
    planes += [np.ascontiguousarray(rgb[:, i]).tobytes() for i in range(3)]
    planes.append(prov.tobytes())
    header = _HEADER.pack(MAGIC, VERSION, n, int((prov == _FILL_CODE).sum()),
                          *map(float, lo), step)
    return gzip.compress(header + b"".join(planes), compresslevel=level, mtime=0)


def decode(blob: bytes):
    """(xyz float32 Nx3, rgb uint8 Nx3, provenance uint8 N), in stream order."""
    raw = gzip.decompress(blob)
    magic, version, n, _fill, ox, oy, oz, step = _HEADER.unpack_from(raw)
    if magic != MAGIC or version != VERSION:
        raise ValueError(f"not a D3DP v{VERSION} pack")
    b = np.frombuffer(raw, np.uint8, offset=_HEADER.size)
    xyz = np.empty((n, 3), np.float32)
    for axis, origin in enumerate((ox, oy, oz)):
        lo_, hi_ = b[2 * axis * n:(2 * axis + 1) * n], b[(2 * axis + 1) * n:(2 * axis + 2) * n]
        d = lo_.astype(np.uint32) | (hi_.astype(np.uint32) << 8)
        xyz[:, axis] = origin + (np.cumsum(d, dtype=np.uint64) & 0xFFFF) * step
    rest = b[6 * n:]
    rgb = np.stack([rest[0:n], rest[n:2 * n], rest[2 * n:3 * n]], axis=1)
    return xyz, rgb, rest[3 * n:4 * n].copy()


#: (project_id, artifact revision, fill) -> packed bytes. A pack is ~20-30 MB
#: for the largest missions; the showcase has six.
_cache: dict = {}
_lock = threading.Lock()
_building: dict = {}


def cached(key, build) -> bytes:
    """The pack for `key`, built at most once however many ask at the same time."""
    with _lock:
        if key in _cache:
            return _cache[key]
        event = _building.get(key)
        mine = event is None
        if mine:
            event = _building[key] = threading.Event()
    if not mine:
        event.wait()
        with _lock:
            if key in _cache:
                return _cache[key]
        return cached(key, build)               # the builder failed; try ourselves
    try:
        data = build()
        with _lock:
            for k in [k for k in _cache if k[0] == key[0]]:
                _cache.pop(k)                   # an older revision of this project
            _cache[key] = data
        return data
    finally:
        with _lock:
            _building.pop(key, None)
        event.set()
