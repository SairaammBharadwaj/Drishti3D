# Optional reconstruction backends

The default verified path (OpenCV SfM + GPS Sim(3)) always runs. These backends
are optional accelerators/alternatives and are **auto-detected** — the app
reports availability honestly at `GET /api/capabilities` and never claims a
model ran when it did not.

## COLMAP / PyCOLMAP (verified, higher accuracy)
```bash
pip install pycolmap          # or install the COLMAP binary and add to PATH
```
Adapter: `drishti_recon.colmap_adapter`. Use for larger/harder captures where
full bundle adjustment and dense MVS help. CUDA optional (speeds dense MVS).

## MASt3R-SLAM (learned dense preview / recovery)
```bash
git clone https://github.com/rmurai0610/MASt3R-SLAM
export DRISHTI_MAST3R_PATH=/path/to/MASt3R-SLAM   # + checkpoints
```
- Fast dense preview / difficult-scene recovery / unknown-intrinsics tracking.
- **Licensing:** the MASt3R ecosystem weights are **CC BY-NC-SA** — review before
  any non-research use.
- Needs an NVIDIA GPU for usable speed; paper-reported FPS is not promised on an
  8 GB laptop GPU.

## VGGT (feed-forward geometry)
```bash
git clone https://github.com/facebookresearch/vggt
export DRISHTI_VGGT_PATH=/path/to/vggt              # + weights
```
Predicts poses/depth/point maps and can export COLMAP-compatible data.

## Provenance rule for AI output
Any learned-model geometry enters as `AI_ASSISTED` and is **excluded from
measurement by default**. It may be promoted to observed only after explicit
geometric verification against the classical reconstruction. Adapters implement
the interface in `drishti_recon.ai_adapter` (`is_available`, `prepare_inputs`,
`reconstruct`, `get_camera_poses`, `get_depth_maps`, `get_point_cloud`,
`get_uncertainty`).
