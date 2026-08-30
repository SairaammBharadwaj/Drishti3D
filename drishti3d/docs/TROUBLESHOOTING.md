# Troubleshooting & air-gapped deployment

## Common issues

**"could not decode enough frames from video"** — the container/codec isn't
readable by the bundled FFmpeg. Re-encode: `ffmpeg -i in.mov -c:v libx264 out.mp4`.

**"telemetry has fewer than 2 valid GPS samples"** — check column names against
`docs/TELEMETRY.md`; out-of-range lat/lon rows are dropped (see run warnings).

**Few keyframes registered / poor cloud** — the pass may lack parallax or
texture, or intrinsics are wrong. Provide `fx,fy,cx,cy`; try the **quality**
preset; ensure the flight actually translates (not a pure rotation).

**Meshing skipped** — Open3D missing or too few points. The point cloud is still
produced and exported; `pip install open3d` to enable meshing.

**LAS export skipped** — `pip install laspy`.

**Dynamic masking removed too much** — the lightweight optical-flow residual
masker can mistake strong parallax (tall buildings, low altitude) for motion.
It is **off by default**. Use `semantic` masking with local weights
(`DRISHTI_SEG_WEIGHTS`) for people/vehicles, or keep masking off for structures.

**GPU not used** — the default classical path is CPU-only by design. Learned
models (MASt3R-SLAM/VGGT) are optional and off unless configured.

## Air-gapped / offline deployment

- The default pipeline makes **no network calls** during processing.
- Model weights are **never auto-downloaded**; optional models require a local
  path (`DRISHTI_MAST3R_PATH`, `DRISHTI_VGGT_PATH`, `DRISHTI_SEG_WEIGHTS`).
- Pre-build the Docker images on a connected machine, `docker save`/`docker load`
  onto the target, then `docker compose up`. Or pre-download Python/npm wheels
  into a local cache.
- The API binds to `127.0.0.1` by default; set `DRISHTI_HOST=0.0.0.0` only when
  you intend LAN access.
- SQLite + the on-disk `data/` directory hold all state; back up `data/` to
  preserve projects and artifacts.

## Security notes

- Uploads are extension- and size-validated; filenames are sanitised and
  project ids are validated to prevent path traversal.
- Uploaded data is never executed. Originals are stored immutably with SHA-256.
- Mission deletion is scoped to the project's own directory.
