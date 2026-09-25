"""End-to-end reconstruction pipeline orchestrator.

Runs the verified path (ingest -> sync -> quality -> keyframes -> masking ->
SfM -> GPS georegistration -> fusion -> mesh -> report -> exports), emitting
staged progress and writing restart-friendly artifacts to a project directory.
Every stage is a separately testable module; this file only wires them together.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable
import json
import time
import numpy as np
import cv2

from . import ingestion, telemetry as tel, frame_quality, keyframes as kf
from . import sync as syncmod, masking, sfm, fusion, mesh as meshmod, quality, exports
from .geo import robust_sim3, Sim3, Sim3Result

Progress = Callable[[str, float, str], None]


def _noop(stage: str, frac: float, msg: str = "") -> None:
    pass


# Stage -> (start, end) fraction of the overall progress bar.
STAGE_SPANS = {
    "ingestion": (0.00, 0.05),
    "telemetry": (0.05, 0.08),
    "frames": (0.08, 0.20),
    "quality": (0.20, 0.28),
    "sync": (0.28, 0.32),
    "keyframes": (0.32, 0.40),
    "masking": (0.40, 0.48),
    "sfm": (0.48, 0.72),
    "densify": (0.72, 0.78),
    "georegistration": (0.78, 0.84),
    "fusion": (0.84, 0.90),
    "mesh": (0.90, 0.94),
    "report": (0.94, 0.97),
    "exports": (0.97, 1.00),
}


@dataclass
class PipelineParams:
    preset: str = "balanced"
    # Dynamic masking is OFF by default: the lightweight optical-flow residual
    # method can conflate scene parallax with motion for tall structures.
    # Enable "optical_flow" for near-nadir aerial passes, or "semantic" with a
    # local torchvision checkpoint (DRISHTI_SEG_WEIGHTS) for humans/vehicles.
    mask_backend: str = "none"
    do_mesh: bool = True
    proc_max_width: int = 1280
    max_analyze_frames: int = 240
    intrinsics: dict | None = None      # {fx,fy,cx,cy} optional override
    voxel: float = 0.15
    engine: str = "opencv"              # opencv (default, always works) | colmap | auto
    # Bundle adjustment jointly refines poses and points; without it the
    # incremental estimate keeps whatever error each step introduced.  Every
    # solve is accepted only if it lowers reprojection RMSE, so it is on by
    # default and can be disabled to reproduce the pre-BA behaviour.
    #: Feature backend: "sift" (default, unchanged) | "akaze" | "lightglue".
    #: The pair graph and every downstream threshold are identical across
    #: backends, so an A/B measures the matcher and nothing else.
    #: Epipolar RANSAC band in pixels; 1.0 when unset.
    #:
    #: Deliberately NOT auto-selected from "was distortion corrected". Absence of
    #: distortion coefficients does not imply a distorted lens -- synthetic
    #: renders are exact pinholes and carry none, and loosening the band there
    #: admits bad correspondences into the two-view initialisation and collapses
    #: the reconstruction to zero points. Real uncorrected imagery genuinely
    #: benefits from ~3 px, so that is an explicit opt-in per capture.
    e_ransac_px: float | None = None
    matcher: str = "sift"
    matcher_options: dict | None = None
    bundle_adjust: bool = True
    ba_every: int = 8                   # cameras registered between interim solves
    refine_focal: bool = False          # refine focal length in the final solve
    refine_distortion: bool = False     # refine k1,k2,p1,p2 in the final solve
    gravity_align: bool = True          # level the cloud so the ground is horizontal
    # Densification: "none" keeps the pure classical (sparse, all-observed) cloud;
    # "depth" fuses a monocular depth prior (Depth Anything V2) to fill the single-
    # pass holes, tagging every added point AI_ASSISTED (excluded from measurement).
    # Observation-space coverage: classifies the scene into observed / weak /
    # occluded / unseen / verified-empty, so unestablished space can be shown and
    # blocked rather than silently interpolated.  See :mod:`coverage`.
    # Sensor-model corrections between camera and GNSS/IMU (see :mod:`sensors`).
    #: Camera position relative to the GNSS antenna, body axes (x fwd, y right,
    #: z down), metres. Requires attitude in telemetry to be applied.
    lever_arm_body: tuple | None = None
    #: Estimate the constant video-to-telemetry time offset from the
    #: reconstructed motion, and re-synchronise if it is confidently non-zero.
    estimate_time_offset: bool = True
    time_offset_search_s: float = 2.0
    #: Sensor readout time, used only to judge rolling-shutter severity.
    rolling_shutter_readout_s: float = 1 / 60.0
    #: Verify depth-prior points against independent views and promote those
    #: that agree to AI_GEOMETRICALLY_VERIFIED. Only meaningful with densify.
    verify_inferred: bool = True
    #: Target 1-sigma positional accuracy, metres. When set, the capture
    #: assessment reports whether the flight could actually deliver it.
    required_sigma_m: float | None = None
    build_coverage: bool = True
    coverage_voxel: float = 1.0
    #: "none" keeps the sparse cloud only. "mvs" adds COLMAP PatchMatch stereo
    #: -- observed geometry, measurable, and the answer to a sparse cloud that
    #: looks like a scattering of corners. Needs a CUDA-enabled `colmap`
    #: executable; the PyPI pycolmap wheels cannot do dense stereo. "depth"
    #: adds monocular depth-prior points, which are inferred and excluded from
    #: measurement.
    densify: str = "none"               # none | mvs | depth
    #: Longest image edge the dense stage works at. Dense stereo cost scales
    #: with pixels, and 1600 keeps an 8 GB card inside its memory on 1080p.
    mvs_max_image_size: int = 1600
    #: Geometric consistency doubles the stereo cost and removes most of the
    #: speckle that makes an unfiltered dense cloud unusable.
    mvs_geometric: bool = True
    #: Dense settings chosen by the ladder in DEC-041 (UseGeo, LiDAR-scored,
    #: fixed sparse model). Against COLMAP's defaults -- 20 sources, patch
    #: step 1, 5 iterations, fusion at 5 views -- PatchMatch went 1,213 s ->
    #: 316 s while RMSE went 0.324 -> 0.316 m, p95 0.487 -> 0.461 m and
    #: completeness within 0.5 m 68.0% -> 70.0%. One calibrated scene: the
    #: defaults are revisited when a second reference exists. ``None`` on any
    #: PatchMatch control means COLMAP's own default
    #: (``mvs.PATCH_MATCH_DEFAULTS``); resolved values go to the report.
    #:
    #: Images that must agree before a fused point is kept. 4 rather than 5:
    #: with 10 sources, 5 cost DJI_1003 12% of its 2 m ground cells, and 4
    #: restored them at no accuracy cost on UseGeo.
    mvs_min_views: int = 4
    mvs_num_src_images: int | None = 10
    mvs_window_step: int | None = 2
    mvs_num_iterations: int | None = 3
    mvs_num_samples: int | None = None
    #: ``"0,0"`` runs two stereo workers on one GPU.
    mvs_gpu_index: str | None = None
    mvs_cache_gb: float | None = None
    #: Depth and normal maps are gigabytes (3.7 GB on DJI_1003) and nothing
    #: reads them after fusion.
    mvs_keep_depth_maps: bool = False
    #: COLMAP SfM threads; ``None`` is half the cores, at most 16.
    sfm_threads: int | None = None
    #: Match features on the GPU through the CUDA ``colmap`` executable.
    sfm_gpu_matching: bool = False
    depth_stride: int = 8               # pixel grid stride for depth back-projection
    #: Fill holes the cameras saw but stereo could not reconstruct -- open
    #: water above all -- with a rim-fitted surface written to ``fill.npz``,
    #: beside the cloud and never in it. Inferred, never measurable. See
    #: :mod:`holefill`.
    fill_holes: bool = True


@dataclass
class PipelineResult:
    project_dir: str
    artifacts: dict = field(default_factory=dict)
    report: dict = field(default_factory=dict)
    warnings: list = field(default_factory=list)


def _write_fill(art_dir, cloud, cameras_enu, recon, kf_frames, image_size):
    """Write ``fill.npz``/``fill.json``: inferred surface over the cloud's holes.

    Colours come from the keyframe that sees each fill point most squarely.
    ``cameras_enu[i]`` is ``recon.cameras[i]``, whose ``frame_index`` is a
    keyframe index -- the image list is indexed by that, not by the decoded
    frame number the exported camera carries.
    """
    from . import holefill
    res = holefill.fill_holes(cloud.points, cameras_enu, recon.K, image_size)
    imgs = [kf_frames[c.frame_index] if c.frame_index < len(kf_frames) else None
            for c in recon.cameras]
    colors = holefill.colorize(res.points, cameras_enu, recon.K, image_size,
                               lambda i: imgs[i])
    np.savez_compressed(art_dir / "fill.npz",
                        points=res.points.astype(np.float32),
                        colors=colors, hole_id=res.hole_id)
    (art_dir / "fill.json").write_text(json.dumps(res.summary(), indent=2))
    return {"fill_npz": str(art_dir / "fill.npz"),
            "fill": str(art_dir / "fill.json")}


def _emit(progress, stage, local_frac, msg=""):
    a, b = STAGE_SPANS[stage]
    progress(stage, a + (b - a) * max(0.0, min(1.0, local_frac)), msg)


def run(project_dir, video_path, telemetry_path, *,
        params: PipelineParams | None = None,
        progress: Progress = _noop) -> PipelineResult:
    params = params or PipelineParams()
    project_dir = Path(project_dir)
    art_dir = project_dir / "artifacts"
    art_dir.mkdir(parents=True, exist_ok=True)
    warnings: list[str] = []
    timings: dict[str, float] = {}
    # One monotonic clock around everything, exports included. The stage
    # timings in the quality report are summed before exports run, so they
    # understate the job; this is the number a deadline is judged against.
    t_wall0 = time.perf_counter()
    sub_timings: dict[str, float] = {}

    def stage_timer(name):
        return _StageTimer(name, timings)

    # 1) INGESTION -----------------------------------------------------------
    with stage_timer("ingestion"):
        _emit(progress, "ingestion", 0.2, "probing video")
        vinfo = ingestion.probe(video_path)
        _emit(progress, "ingestion", 1.0, f"{vinfo.width}x{vinfo.height} {vinfo.duration:.1f}s")

    # 2) TELEMETRY -----------------------------------------------------------
    with stage_timer("telemetry"):
        _emit(progress, "telemetry", 0.3, "parsing telemetry")
        no_gps = telemetry_path is None
        if no_gps:
            treport = tel.TelemetryReport([], 0, 0, [])
        else:
            treport = tel.load(telemetry_path)
            warnings += treport.warnings
            no_gps = not treport.ok
        if no_gps:
            # Relative-scale mode: reconstruct shape without georeferencing.
            from .geo import ENUFrame
            enu_frame = ENUFrame(0.0, 0.0, 0.0)
            warnings.append("no usable GPS telemetry -> relative scale "
                            "(shape only; not georeferenced, not metric)")
            _emit(progress, "telemetry", 1.0, "no GPS (relative scale)")
        else:
            enu_frame = syncmod.build_enu_frame(treport.samples)
            _emit(progress, "telemetry", 1.0, f"{treport.n_valid} samples")

    # 3) FRAMES (decode + sample, bounded) -----------------------------------
    # Frame scoring overlaps decoding: each kept frame is scored on a worker
    # thread while the decoder moves on. Only when nothing will change the
    # pixels afterwards -- lens undistortion does, so it scores after.
    _dist_known = (params.intrinsics or treport.intrinsics or {}).get("distortion")
    from concurrent.futures import ThreadPoolExecutor as _TPE
    _score_pool = _TPE(max_workers=4) if _dist_known is None else None
    _scored = []
    with stage_timer("frames"):
        cap = cv2.VideoCapture(str(video_path))
        fps = vinfo.fps
        stride = max(1, int(np.ceil(vinfo.frame_count / params.max_analyze_frames)))
        sf = 1.0
        frames = []          # (frame_index, timestamp, bgr) at processing scale
        store = None         # disk-backed pixels for `frames`; see _FrameStore
        pts_pre = []         # POS_MSEC sampled *before* read(), seconds
        pts_post = []        # POS_MSEC sampled *after* read(), seconds
        idx = 0
        while True:
            # Sample the position both sides of the read. Backends disagree about
            # what POS_MSEC means: some report the frame about to be decoded,
            # others the one just returned. Measured on OpenCV 5.0 here, the
            # pre-read value duplicates at the start and lags the true PTS by one
            # frame, while the post-read value is the decoded frame's own PTS.
            # Guessing one convention silently mis-associates every frame with a
            # GNSS sample on a variable-frame-rate clip, so both are recorded and
            # `_adopt_pts` decides which series is self-consistent.
            t_pre = cap.get(cv2.CAP_PROP_POS_MSEC) / 1000.0
            keep_frame = idx % stride == 0
            # `read()` is `grab()` plus `retrieve()`; only kept frames need the
            # retrieve (the colour conversion and copy out). The grab still
            # advances the decoder and the position, so the timestamps below
            # are the same either way. DJI_1003 keeps 1 frame in 17.
            if keep_frame:
                ok, fr = cap.read()
            else:
                ok, fr = cap.grab(), None
            if not ok:
                break
            t_post = cap.get(cv2.CAP_PROP_POS_MSEC) / 1000.0
            if keep_frame:
                if fr.shape[1] > params.proc_max_width:
                    sf = params.proc_max_width / fr.shape[1]
                    fr = cv2.resize(fr, (params.proc_max_width,
                                         int(round(fr.shape[0] * sf))))
                if store is None:
                    store = _FrameStore(project_dir / "frames.u8", fr.shape,
                                        vinfo.frame_count // stride + 1)
                fr = store.put(fr)
                frames.append((idx, idx / fps, fr))
                if _score_pool is not None:
                    _scored.append(_score_pool.submit(frame_quality._per_frame, fr))
                pts_pre.append(t_pre)
                pts_post.append(t_post)
                _emit(progress, "frames", len(frames) /
                      (vinfo.frame_count / stride + 1), "decoding")
            idx += 1
        cap.release()
        if len(frames) < 2:
            raise RuntimeError("could not decode enough frames from video")
        proc_h, proc_w = frames[0][2].shape[:2]

        # Prefer real timestamps over the nominal clock.  `frame_index / fps` is
        # only correct for constant-frame-rate video; a single dropped frame
        # shifts every later timestamp and silently pairs frames with the wrong
        # GNSS sample.
        timing_source, timing_note = _adopt_pts(frames, pts_pre, fps,
                                                pts_post=pts_post)
        if timing_note:
            warnings.append(timing_note)

    # intrinsics (override -> telemetry -> estimate), scaled to processing size
    # `calibrated` separates a measured calibration from the 0.9*max(w,h)
    # fallback. DEC-038 fixed the COLMAP path discarding a supplied
    # calibration, and then held *every* K fixed -- including the guess, which
    # is worse than self-calibrating: it freezes an arbitrary focal instead of
    # solving for the real one. Only a measured calibration is held.
    K, calibrated = _resolve_intrinsics(
        params.intrinsics or treport.intrinsics,
        vinfo.width, vinfo.height, proc_w, proc_h, sf, warnings, want_flag=True)

    # 4a) LENS DISTORTION ----------------------------------------------------
    # Correct once, up front, so every later stage can assume a pinhole camera.
    # Threading coefficients through triangulation, PnP, BA and uncertainty
    # would need a distortion-aware variant of each, and a missed one would fail
    # silently.
    _dist = (params.intrinsics or treport.intrinsics or {}).get("distortion")
    distortion_applied = False
    if _dist is not None:
        from . import sensors as sensormod
        # In place: returning new arrays held a second copy of every analysed
        # frame at once, which is what pushed 280 MARS-LVIG frames past 6 GB.
        _, K, distortion_applied = sensormod.undistort_frames(
            [f[2] for f in frames], K, _dist, inplace=True)
        if distortion_applied:
            warnings.append("lens distortion corrected; intrinsics updated to "
                            "the undistorted camera")

    # 4) FRAME QUALITY -------------------------------------------------------
    with stage_timer("quality"):
        _emit(progress, "quality", 0.2, "scoring frames")
        _pre = None
        if _score_pool is not None:
            _pre = [f.result() for f in _scored]
            _score_pool.shutdown()
        metrics = frame_quality.analyze(frames, precomputed=_pre)
        _emit(progress, "quality", 1.0,
              f"{sum(m.accepted for m in metrics)}/{len(metrics)} accepted")

    # 5) SYNC ----------------------------------------------------------------
    with stage_timer("sync"):
        if no_gps:
            synced = None
            gps_enu_all = None
            _emit(progress, "sync", 1.0, "no GPS to sync")
        else:
            synced = syncmod.synchronize([(fi, ts) for fi, ts, _ in frames],
                                         treport.samples, enu_frame)
            gps_enu_all = np.array([s.enu for s in synced])
            _emit(progress, "sync", 1.0, "telemetry interpolated")

    # 6) KEYFRAMES -----------------------------------------------------------
    with stage_timer("keyframes"):
        _emit(progress, "keyframes", 0.2, "selecting keyframes")
        if 2 <= len(frames) <= 80:
            # Sparse capture (e.g. an aerial photo grid): every frame is already
            # a valuable wide-baseline view -- keep them all rather than thin.
            sel = list(range(len(frames)))
            timeline = [{"frame_index": frames[i][0], "timestamp": frames[i][1]}
                        for i in sel]
        else:
            sel, timeline = kf.select(frames, metrics, preset=params.preset,
                                      gps_enu=gps_enu_all)
        # Copied out of the frame store, which is deleted below.
        kf_frames = [np.array(frames[i][2]) for i in sel]
        # Keyframe index -> decoded video frame index, built once and named for
        # what it is. `sel` holds positions in the *analysed* array, and
        # `frames[i][0]` is the decoded index of that analysed frame. The two
        # coincide only when every frame was analysed, which is why writing
        # `sel[k]` as a frame index survived every mission until one used
        # `--max-frames` on a long video: there `sel[k]` is off by the analysis
        # stride, and a camera at 292 s was recorded as being at 16 s.
        #
        # Fifth time these two numbering schemes have had to be separated by
        # hand (DEC-009, DEC-015, DEC-020, DEC-025).
        decoded_of_keyframe = [int(frames[i][0]) for i in sel]
        # Everything after this point needs the analysed frames' indices and
        # timestamps, and only the keyframes' pixels. Holding the rest is
        # 2,391 x 1600 x 900 x 3 = 10.3 GB on DJI_1003 against 346 MB for the
        # 80 keyframes, on a 16 GB machine.
        frames = [(fi, ts, None) for fi, ts, _ in frames]
        if store is not None:
            store.close()
            store = None
        kf_gps =gps_enu_all[sel] if gps_enu_all is not None else None
        kf_acc = [synced[i].gps_accuracy for i in sel] if synced is not None else None
        _emit(progress, "keyframes", 1.0, f"{len(sel)} keyframes")

    # 7) MASKING -------------------------------------------------------------
    with stage_timer("masking"):
        _emit(progress, "masking", 0.2, "computing dynamic masks")
        masks, mask_name, mwarn = masking.compute_masks(kf_frames, params.mask_backend)
        if mwarn:
            warnings.append(mwarn)
        _emit(progress, "masking", 1.0, f"backend={mask_name}")

    # 8) SFM (verified reconstruction) --------------------------------------
    with stage_timer("sfm"):
        from . import colmap_adapter
        use_colmap = (params.engine == "colmap" or
                      (params.engine == "auto" and colmap_adapter.is_available()))
        if use_colmap:
            # Dense stereo re-reads the images and the sparse model COLMAP
            # wrote, so the workspace has to outlive the sparse stage.
            keep = (project_dir / "colmap_workspace"
                    if params.densify == "mvs" else None)
            recon = colmap_adapter.reconstruct_frames(
                kf_frames, K, keep_workspace=keep, fix_intrinsics=calibrated,
                num_threads=params.sfm_threads,
                gpu_matching=params.sfm_gpu_matching,
                progress=lambda m, f: _emit(progress, "sfm", f, m))
        else:
            recon = sfm.reconstruct(
                kf_frames, K, masks=masks, positions=kf_gps,
                matcher=params.matcher, matcher_options=params.matcher_options,
                e_ransac_px=(params.e_ransac_px if params.e_ransac_px is not None
                             else 1.0),
                do_ba=params.bundle_adjust, ba_every=params.ba_every,
                refine_focal=params.refine_focal,
                refine_distortion=params.refine_distortion,
                progress=lambda m, f: _emit(progress, "sfm", f, m))
            # BA may refine the intrinsics; downstream stages and the report must
            # use the camera model the geometry was actually solved with.
            K = recon.K
        if recon.stats["n_points"] == 0:
            raise RuntimeError("reconstruction produced no 3D points")

    # 8b) DENSIFY -----------------------------------------------------------
    # Two paths that must not be confused. "mvs" triangulates from photometric
    # agreement across real images and is *observed* geometry, measurable like
    # any other point. "depth" predicts depth from a single image with a
    # learned model and is *inferred*: those points are tagged AI_ASSISTED and
    # excluded from measurement. Both make the viewer look better; only one may
    # be measured.
    dense_local = None
    dense_cols_local = None
    mvs_points = None          # observed: joins the measured cloud
    mvs_colors = None
    mvs_sigma = None
    mvs_conf = None
    mvs_vis = None             # per-point contributing keyframes, (flat, offsets)
    mvs_stats = None
    with stage_timer("densify"):
        if params.densify == "mvs":
            try:
                from . import mvs as mvsmod
                ws = recon.stats.get("workspace")
                if not ws:
                    raise RuntimeError(
                        "dense MVS needs the COLMAP engine; the in-repo engine "
                        "writes no COLMAP workspace")
                _emit(progress, "densify", 0.05, "dense stereo")
                dr = mvsmod.run_colmap(
                    ws, max_image_size=params.mvs_max_image_size,
                    geom_consistency=params.mvs_geometric,
                    min_num_pixels=params.mvs_min_views,
                    num_src_images=params.mvs_num_src_images,
                    window_step=params.mvs_window_step,
                    num_iterations=params.mvs_num_iterations,
                    num_samples=params.mvs_num_samples,
                    gpu_index=params.mvs_gpu_index,
                    cache_size_gb=params.mvs_cache_gb,
                    keep_depth_maps=params.mvs_keep_depth_maps,
                    log_dir=Path(project_dir) / "logs" / "mvs",
                    progress=lambda m, f: _emit(progress, "densify", f, m))
                if len(dr):
                    mvs_points = dr.points
                    mvs_colors = dr.colors
                    mvs_vis = dr.tracks_csr()
                    centres = np.array([c.center for c in recon.cameras], float)
                    # Dense pixel noise is in the dense images' pixels. They
                    # can be smaller than the sparse images (mvs_max_image_size),
                    # and using the sparse focal length there would claim the
                    # same confidence from fewer pixels.
                    focal = dr.stats.get("dense_focal_px") or (
                        0.5 * (float(recon.K[0, 0]) + float(recon.K[1, 1])))
                    # The floor is the sparse model's own accuracy in the
                    # reconstruction frame: a dense point cannot be better
                    # known than the geometry that fixed the cameras.
                    _ps = recon.point_sigma_major
                    floor = None
                    if _ps is not None and np.any(np.isfinite(_ps)):
                        floor = float(np.median(_ps[np.isfinite(_ps)]))
                    # The cameras that actually fused each point, so depth
                    # uncertainty responds to the triangulation angle instead
                    # of assuming one.
                    #
                    # `run_colmap` has already translated visibility indices
                    # into keyframe indices, so these are keyframe numbers, the
                    # same space `Camera.frame_index` uses -- mapping them
                    # through `frame_order` a second time would translate
                    # twice and attribute every point to the wrong cameras.
                    # This is the fourth place the two numbering schemes have
                    # had to be separated deliberately (DEC-009, DEC-015,
                    # DEC-020), and the first where the stale docstring on
                    # `DenseResult.vis_images` was what suggested the error.
                    _par = None
                    if mvs_vis is not None:
                        # Keyframe index -> position in recon.cameras, as a
                        # lookup table; -1 for keyframes that did not register.
                        _cam_of_kf = np.full(
                            max([int(c.frame_index) for c in recon.cameras]
                                + [int(mvs_vis[0].max()) if len(mvs_vis[0]) else 0]) + 1,
                            -1, np.int64)
                        for i, c in enumerate(recon.cameras):
                            _cam_of_kf[int(c.frame_index)] = i
                        _par = mvsmod.contributing_parallax_deg(
                            dr.points, centres,
                            csr=(_cam_of_kf[mvs_vis[0]], mvs_vis[1]))
                    mvs_sigma = mvsmod.depth_uncertainty(
                        dr.points, centres, dr.n_views,
                        sigma_px=mvsmod.DENSE_PIXEL_SIGMA, focal=focal,
                        floor=floor, parallax_deg=_par)
                    mvs_stats = dict(dr.stats)
                    # Confidence from how many images actually agreed. A point
                    # two images agree on is real but weakly held; one that
                    # survives many is the dense equivalent of a long track.
                    nv = (np.asarray(dr.n_views, float) if dr.n_views is not None
                          else np.full(len(dr), 3.0))
                    mvs_conf = np.clip((nv - 2.0) / 4.0, 0.0, 1.0) * 0.4 + 0.45
                    warnings.append(
                        f"dense MVS added {len(dr)} observed points; their "
                        f"uncertainty is a geometric estimate from range and "
                        f"view count, not a propagated covariance")
                _emit(progress, "densify", 1.0, f"{len(dr)} dense points")
            except Exception as e:
                warnings.append(f"dense MVS skipped: {e}")
                _emit(progress, "densify", 1.0, "skipped")
        elif params.densify == "depth":
            try:
                from . import depth_prior
                _emit(progress, "densify", 0.1, "loading depth model")
                dp, dc, dwarn = depth_prior.densify(
                    recon, kf_frames, pixel_stride=params.depth_stride,
                    progress=lambda f: _emit(progress, "densify", 0.1 + 0.85 * f,
                                             "depth prior"))
                warnings += dwarn
                if len(dp):
                    dense_local, dense_cols_local = dp, dc
                _emit(progress, "densify", 1.0, f"{len(dp)} inferred points")
            except Exception as e:
                warnings.append(f"depth densification skipped: {e}")
                _emit(progress, "densify", 1.0, "skipped")

    # 8c) SENSOR-MODEL CORRECTIONS ------------------------------------------
    # Done here rather than earlier because both need the reconstruction: the
    # time offset is estimated from the reconstructed motion, and the rolling-
    # shutter check reads the recovered poses.
    time_offset = None
    rs_check = None
    if not no_gps and synced is not None and len(recon.cameras) >= 4:
        from . import sensors as sensormod
        kf_times = [frames[sel[c.frame_index]][1] for c in recon.cameras]
        kf_centres = np.array([c.center for c in recon.cameras])
        if params.estimate_time_offset:
            tel_t = np.array([s.timestamp for s in treport.samples])
            tel_p = enu_frame.geodetic_to_enu(
                [s.latitude for s in treport.samples],
                [s.longitude for s in treport.samples],
                [s.altitude for s in treport.samples])
            time_offset = sensormod.estimate_time_offset(
                kf_times, kf_centres, tel_t, tel_p,
                search_s=params.time_offset_search_s)
            if time_offset.accepted and abs(time_offset.offset_s) > 0.02:
                # Re-synchronise every frame on the corrected clock; a constant
                # offset otherwise slides each frame onto the wrong GNSS sample
                # and the aligner absorbs it as a spurious translation.
                synced = syncmod.synchronize(
                    [(fi, ts) for fi, ts, _ in frames], treport.samples,
                    enu_frame, offset=time_offset.offset_s)
                gps_enu_all = np.array([s.enu for s in synced])
                kf_gps = gps_enu_all[sel]
                kf_acc = [synced[i].gps_accuracy for i in sel]
                warnings.append(
                    f"video-to-telemetry time offset {time_offset.offset_s:+.3f}s "
                    f"estimated (correlation {time_offset.correlation:.2f}) and applied")
            elif time_offset.reason:
                warnings.append(f"time offset not applied: {time_offset.reason}")

        rs_check = sensormod.detect_rolling_shutter(
            [c.R for c in recon.cameras], kf_times,
            readout_s=params.rolling_shutter_readout_s)
        if rs_check.message:
            warnings.append(rs_check.message)

    # 8d) LEVER ARM ----------------------------------------------------------
    lever_applied = False
    if params.lever_arm_body is not None and kf_gps is not None and synced is not None:
        from . import sensors as sensormod
        yaws = [synced[i].yaw for i in sel]
        if any(y is not None for y in yaws):
            kf_gps, lever_applied = sensormod.apply_lever_arm(
                kf_gps, params.lever_arm_body,
                yaw=[0.0 if y is None else y for y in yaws])
            if lever_applied:
                warnings.append(
                    f"GNSS antenna-to-camera lever arm {tuple(params.lever_arm_body)} m "
                    "applied using telemetry heading")
        else:
            warnings.append("lever arm supplied but telemetry has no heading; "
                            "cannot place a body-frame offset in the world")

    # 9) GEOREGISTRATION (Sim3 to GPS ENU) -----------------------------------
    with stage_timer("georegistration"):
        _emit(progress, "georegistration", 0.3,
              "relative scale" if no_gps else "aligning to GPS")
        reg_local_idx = [c.frame_index for c in recon.cameras]  # index into sel
        cam_centers = np.array([c.center for c in recon.cameras])
        align = None
        scale_source = "relative"
        dense_enu = None
        mvs_enu = None
        if not no_gps and kf_gps is not None and len(cam_centers) >= 3:
            gps_for_cams = kf_gps[reg_local_idx]
            acc_for_cams = [kf_acc[i] for i in reg_local_idx]
            weights = np.array([1.0 / a if a else 1.0 for a in acc_for_cams])
            align = robust_sim3(cam_centers, gps_for_cams, weights=weights,
                                threshold=3.0)
            # `has_rtk` is now a supermajority test, not `any()`, so a single
            # RTK-labelled sample can no longer describe a whole mission's
            # scale as RTK-derived.
            scale_source = "rtk" if treport.has_rtk else "gps"
            pts_enu = align.transform.apply(recon.points)
            cams_enu = [align.transform.apply(c.center)[0] for c in recon.cameras]
            if dense_local is not None:
                dense_enu = align.transform.apply(dense_local)
            if mvs_points is not None:
                mvs_enu = align.transform.apply(mvs_points)
        else:
            if not no_gps:
                warnings.append("fewer than 3 registered cameras; metric scale unavailable")
            pts_enu = recon.points
            cams_enu = [c.center for c in recon.cameras]
            dense_enu = dense_local
            mvs_enu = mvs_points
        # Level the scene: correct residual tilt so the ground is horizontal and
        # "up" is truly up (nadir GPS barely constrains the vertical axis).
        #
        # This rotates deliverables *after* they were fitted to GNSS, so it can
        # move the product away from the coordinates the alignment residual was
        # computed on.  It is therefore only applied when it can be composed into
        # the saved transform and shown not to degrade the GNSS fit -- otherwise
        # the report would publish a residual the exported coordinates cannot
        # reproduce.
        leveling = None
        leveling_rotation = None
        if params.gravity_align and len(pts_enu) > 200:
            from .geo import level_rotation
            Rlvl = level_rotation(pts_enu)
            if Rlvl is not None:
                c0 = pts_enu.mean(0)
                tilt_deg = float(np.degrees(np.arccos(np.clip(
                    (np.trace(Rlvl) - 1) / 2, -1, 1))))
                accept, align_after = True, align
                if align is not None:
                    # The levelled map is itself a similarity: compose it so the
                    # persisted transform IS the one that produced the export.
                    composed = Sim3(align.transform.scale,
                                    Rlvl @ align.transform.R,
                                    Rlvl @ (align.transform.t - c0) + c0)
                    diff = composed.apply(cam_centers) - gps_for_cams
                    inl = align.inliers
                    rmse = float(np.sqrt((diff[inl] ** 2).sum(1).mean()))
                    # Levelling is a correction, not a licence to worsen the fit.
                    # Allow a little slack (GNSS altitude is weak, so a genuine
                    # tilt fix can nudge the residual up) but refuse a real
                    # degradation.
                    accept = rmse <= max(align.rmse * 1.25, align.rmse + 0.25)
                    if accept:
                        align_after = Sim3Result(
                            composed, inl, rmse,
                            float(np.sqrt((diff[inl][:, :2] ** 2).sum(1).mean())),
                            float(np.sqrt((diff[inl][:, 2] ** 2).mean())),
                            int(inl.sum()), align.n_total,
                            normalized_rmse=align.normalized_rmse,
                            scale_sigma=align.scale_sigma,
                            degenerate=align.degenerate,
                            degeneracy=align.degeneracy,
                            conditioning=dict(align.conditioning))
                    else:
                        warnings.append(
                            f"gravity/level correction rejected: it would raise the "
                            f"GPS alignment residual from {align.rmse:.3f} m to "
                            f"{rmse:.3f} m. Scene left in its GPS-fitted orientation.")
                if accept:
                    leveling_rotation = Rlvl
                    pts_enu = (Rlvl @ (pts_enu - c0).T).T + c0
                    cams_enu = [(Rlvl @ (np.asarray(ce) - c0)) + c0 for ce in cams_enu]
                    if dense_enu is not None:
                        dense_enu = (Rlvl @ (dense_enu - c0).T).T + c0
                    align = align_after
                    leveling = {"applied": True,
                                "tilt_corrected_deg": tilt_deg,
                                "rotation": Rlvl.tolist(),
                                "pivot_enu": c0.tolist(),
                                "composed_into_alignment": align_after is not None,
                                "alignment_rmse_after_m":
                                    align.rmse if align is not None else None}
                    warnings.append(
                        f"applied gravity/level correction ({tilt_deg:.2f} deg); "
                        "composed into the saved transform and the reported GPS "
                        "residual recomputed against it")
                else:
                    leveling = {"applied": False,
                                "tilt_corrected_deg": tilt_deg,
                                "reason": "would degrade the GPS alignment residual"}
        _emit(progress, "georegistration", 1.0,
              f"scale={align.transform.scale:.3f}" if align else "relative scale")

    # Relative metric-scale uncertainty, which dominates long measurements.
    scale_sigma_rel = 0.0
    if align is not None and getattr(align, "scale_sigma", None):
        try:
            scale_sigma_rel = float(align.scale_sigma) / float(align.transform.scale)
        except Exception:
            scale_sigma_rel = 0.0

    # The world rotation induced by georegistration (and any levelling). Cameras
    # must be rotated by it before they can be used against the ENU cloud.
    R_world_for_cov = ((leveling_rotation if leveling_rotation is not None
                        else np.eye(3))
                       @ (align.transform.R if align is not None else np.eye(3)))
    verification_summary = None

    # 10) FUSION -------------------------------------------------------------
    with stage_timer("fusion"):
        _emit(progress, "fusion", 0.3, "cleaning cloud")
        # Uncertainty was propagated in the reconstruction frame; a similarity
        # multiplies lengths by its scale, so the metric sigma is scale * sigma.
        _s = float(align.transform.scale) if align is not None else 1.0
        _sig = None if recon.point_sigma is None else recon.point_sigma * _s
        _sigmaj = (None if recon.point_sigma_major is None
                   else recon.point_sigma_major * _s)
        # Dense stereo points are observed geometry, so they are fused into the
        # *same* cloud as the sparse ones rather than layered beside them like
        # the depth prior. They carry their own sigma, which is a geometric
        # estimate rather than a propagated covariance -- the warning raised in
        # the densify stage says so, and it is the same number a measurement
        # would be quoted from.
        _pts, _cols, _conf = pts_enu, recon.colors, recon.confidence
        if mvs_enu is not None and len(mvs_enu):
            _mv_sig = (mvs_sigma * _s) if mvs_sigma is not None else None
            _pts = np.vstack([_pts, mvs_enu])
            _cols = np.vstack([_cols, mvs_colors.astype(np.uint8)])
            _conf = np.concatenate([_conf, mvs_conf])
            if _sig is not None and _mv_sig is not None:
                _sig = np.concatenate([_sig, _mv_sig])
                _sigmaj = np.concatenate([_sigmaj, _mv_sig])
            else:
                # Mixing known and unknown uncertainty in one array would let a
                # dense point inherit a sparse point's sigma through indexing.
                _sig = _sigmaj = None
        cloud = fusion.fuse(_pts, _cols, _conf,
                            voxel=params.voxel, sigma=_sig, sigma_major=_sigmaj)
        # Merge depth-prior points as a SEPARATE, measurement-excluded layer so
        # the trust map can show observed (green) vs AI-inferred (purple) geometry.
        if dense_enu is not None and len(dense_enu):
            dvox = max(params.voxel, 0.25)
            dpts, dcols, _ = fusion._voxel_downsample_np(
                dense_enu, dense_cols_local,
                np.zeros(len(dense_enu)), dvox)
            # trim depth-prior flyers so the trust map stays clean
            if len(dpts) > 50:
                keep = fusion._statistical_outlier_np(dpts, k=8, std_ratio=2.0)
                dpts, dcols = dpts[keep], dcols[keep]
            n_before = len(cloud)
            cloud = fusion.add_inferred_layer(cloud, dpts, dcols)
            # Test the inferred points against views that did not produce them.
            if params.verify_inferred and len(cloud) > n_before:
                try:
                    from . import verify as verifymod
                    inferred_mask = np.zeros(len(cloud), bool)
                    inferred_mask[n_before:] = True
                    cams_v = [_EnuCam(np.asarray(c.R, float) @ R_world_for_cov.T,
                                      np.asarray(ce, float))
                              for c, ce in zip(recon.cameras, cams_enu)]
                    vres = verifymod.verify_inferred(
                        cloud.points[inferred_mask], cloud.colors[inferred_mask],
                        cloud.points[:n_before], cloud.colors[:n_before],
                        cams_v, K, (proc_w, proc_h))
                    verifymod.apply_verification(cloud, vres, inferred_mask)
                    verification_summary = vres.summary()
                except Exception as e:
                    warnings.append(f"inferred-geometry verification skipped: {e}")
        _emit(progress, "fusion", 1.0, f"{len(cloud)} points")

    # 10b) OBSERVATION-SPACE COVERAGE ---------------------------------------
    cov_grid = None
    if params.build_coverage and len(recon.cameras) >= 1 and len(cloud):
        try:
            from . import coverage as covmod
            # Rebuild each camera in the ENU frame the cloud now lives in.
            # The rotation is NOT unchanged by the similarity: with
            # X_enu = s*R_a*X_recon + t, the camera's world->camera rotation
            # becomes R_cam @ R_a^T. Keeping R_cam pointed every camera in the
            # wrong direction, so nothing fell inside any frustum and the whole
            # scene came back UNSEEN.
            R_world = R_world_for_cov
            cams_for_cov = [_EnuCam(np.asarray(c.R, float) @ R_world.T,
                                    np.asarray(ce, float))
                            for c, ce in zip(recon.cameras, cams_enu)]
            # Dynamic masks are keyed by keyframe; the registered cameras are a
            # subset, so index through `frame_index` rather than positionally.
            cov_masks = None
            if masks is not None:
                cov_masks = [masks[c.frame_index]
                             if c.frame_index < len(masks) else None
                             for c in recon.cameras]
            cov_grid = covmod.build(cloud.points, cams_for_cov, K,
                                    (proc_w, proc_h), masks=cov_masks,
                                    voxel=params.coverage_voxel)
        except Exception as e:
            warnings.append(f"coverage layer skipped: {e}")

    # 11) MESH (optional) ----------------------------------------------------
    mesh_path = None
    with stage_timer("mesh"):
        if params.do_mesh:
            try:
                _emit(progress, "mesh", 0.3, "meshing")
                verts, faces, vcols = meshmod.mesh_poisson(cloud)
                mesh_path = exports.export_glb(art_dir / "mesh.glb", verts, faces, vcols)
            except Exception as e:  # meshing is optional; preserve the cloud
                warnings.append(f"meshing skipped: {e}")
        _emit(progress, "mesh", 1.0, "")

    # 12) QUALITY REPORT (+ optional ground-truth eval) ----------------------
    with stage_timer("report"):
        _emit(progress, "report", 0.3, "computing metrics")
        gt_eval = _maybe_gt_eval(video_path, telemetry_path, enu_frame, cloud)
        cov_summary = cov_grid.summary() if cov_grid is not None else None
        from . import capture as capmod
        # Feed the assessment the uncertainty the capture actually delivered,
        # so "can it meet the requirement" is answered from measurement rather
        # than left as None.
        _unc_summary = None
        if getattr(cloud, "sigma_major", None) is not None:
            _sm = np.asarray(cloud.sigma_major, float)
            _fin = _sm[np.isfinite(_sm)]
            if len(_fin):
                _unc_summary = {"sigma_major_m": {
                    "median": float(np.median(_fin)),
                    "p90": float(np.percentile(_fin, 90))}}
        assessment = capmod.assess(
            recon_stats=recon.stats, coverage_summary=cov_summary,
            uncertainty_summary=_unc_summary, frame_metrics=metrics,
            required_sigma_m=params.required_sigma_m)
        recapture = capmod.plan_recapture(assessment, coverage_grid=cov_grid)
        # The fix-quality composition travels with the scale label, so a
        # reader can see what the word "rtk" or "gps" rests on rather than
        # having to trust it.
        report = quality.build_report(
            video_info=vinfo, telemetry_report=treport, frame_metrics=metrics,
            keyframe_count=len(sel), recon_stats=recon.stats, align_result=align,
            cloud=cloud, timings=timings, gt_eval=gt_eval, warnings=warnings,
            scale_source=scale_source, coverage=cov_summary,
            sensors={
                "time_offset": time_offset.to_dict() if time_offset else None,
                "rolling_shutter": rs_check.to_dict() if rs_check else None,
                "lever_arm_body_m": (list(params.lever_arm_body)
                                     if params.lever_arm_body else None),
                "lever_arm_applied": lever_applied,
                "lens_distortion_corrected": distortion_applied,
            },
            capture_assessment=assessment.to_dict(),
            recapture_plan=recapture.to_dict(),
            inferred_verification=verification_summary)
        if treport.fix_quality_counts:
            tsec = report.setdefault("input", {}).setdefault("telemetry", {})
            tsec["fix_quality_counts"] = dict(treport.fix_quality_counts)
            tsec["rtk_fixed_fraction"] = round(
                float(treport.rtk_fixed_fraction), 4)
        _emit(progress, "report", 1.0, "report ready")

    # 13) EXPORTS + viewer payload ------------------------------------------
    with stage_timer("exports"):
        # Rotations travel with the centres. Without them a stored camera can
        # place itself but cannot say what it was looking at, and any later
        # question about which frames see a given point -- evidence display,
        # view-support scoring, refinement candidate ranking -- has to
        # re-derive them or guess.
        # The world->camera rotation in the ENU frame. It is NOT the solver's
        # R: the similarity that moved the cloud into ENU rotated the world
        # under every camera, so the stored rotation is R_cam @ R_world^T --
        # the same composition the coverage grid uses. Exporting the raw R
        # would point every camera in the wrong direction downstream.
        cameras_enu = [{"frame_index": int(decoded_of_keyframe[c.frame_index]),
                        "C": list(map(float, ce)),
                        "R": (np.asarray(c.R, float)
                              @ R_world_for_cov.T).tolist()}
                       for c, ce in zip(recon.cameras, cams_enu)]
        _t_obs = time.perf_counter()
        observations = _remap_observations(recon, cloud, decoded_of_keyframe,
                                           n_sparse=len(recon.points),
                                           dense_vis=mvs_vis,
                                           dense_points=mvs_enu,
                                           voxel=params.voxel,
                                           cameras_enu=cameras_enu)
        sub_timings["exports.observations"] = round(time.perf_counter() - _t_obs, 3)
        _t_w = time.perf_counter()
        artifacts = _write_artifacts(art_dir, cloud, cameras_enu, enu_frame,
                                     report, timeline, gps_enu_all, sel, metrics,
                                     K=recon.K, image_size=(proc_w, proc_h),
                                     observations=observations)
        sub_timings["exports.write_artifacts"] = round(time.perf_counter() - _t_w, 3)
        _t_f = time.perf_counter()
        if params.fill_holes:
            try:
                artifacts.update(_write_fill(art_dir, cloud, cameras_enu, recon,
                                             kf_frames, (proc_w, proc_h)))
            except Exception as e:  # a fill is cosmetic; never lose the run
                warnings.append(f"hole fill skipped: {e}")
        sub_timings["exports.hole_fill"] = round(time.perf_counter() - _t_f, 3)
        if mesh_path:
            artifacts["mesh_glb"] = mesh_path
        if cov_grid is not None:
            artifacts["coverage_npz"] = cov_grid.to_npz(art_dir / "coverage.npz")
            (art_dir / "coverage.json").write_text(json.dumps({
                **cov_grid.summary(),
                "recapture_hints": __import__(
                    "drishti_recon.coverage", fromlist=["x"]
                ).recapture_hints(cov_grid),
            }, indent=2))
            artifacts["coverage"] = str(art_dir / "coverage.json")
        _emit(progress, "exports", 1.0, "artifacts written")

    _write_manifest(project_dir, vinfo, treport, params, artifacts, warnings,
                    leveling=leveling, align=align, timing_source=timing_source,
                    alignment=report.get("alignment"))
    wall = time.perf_counter() - t_wall0
    timing = {
        "wall_s": round(wall, 2),
        "video_s": round(float(vinfo.duration), 2) if vinfo.duration else None,
        "wall_over_video": (round(wall / float(vinfo.duration), 3)
                            if vinfo.duration else None),
        "stages_s": dict(timings),
        "substages_s": dict(sub_timings),
        "sfm": {"timings_s": recon.stats.get("timings_s"),
                "num_threads": recon.stats.get("num_threads")},
        "dense": ({"timings_s": mvs_stats.get("timings_s"),
                   "settings": mvs_stats.get("settings"),
                   "dense_focal_px": mvs_stats.get("dense_focal_px")}
                  if mvs_stats else None),
        "note": "wall_s is one monotonic clock from pipeline entry to the "
                "manifest; stages_s are sequential except that substages_s "
                "and dense timings sit inside their stage",
    }
    (art_dir / "timing.json").write_text(json.dumps(timing, indent=2))
    artifacts["timing"] = str(art_dir / "timing.json")
    report["timing_complete"] = timing
    result = PipelineResult(str(project_dir), artifacts, report, warnings)
    return result


class _EnuCam:
    """A camera expressed in the ENU frame (same rotation, moved centre)."""

    def __init__(self, R, centre):
        self.R = np.asarray(R, float)
        self.center = np.asarray(centre, float).ravel()
        self.t = -self.R @ self.center


class _StageTimer:
    def __init__(self, name, sink):
        self.name, self.sink = name, sink

    def __enter__(self):
        self.t = time.perf_counter()
        return self

    def __exit__(self, *a):
        self.sink[self.name] = round(time.perf_counter() - self.t, 3)


def _usable_pts(t, _np):
    """True when a PTS series carries real, strictly increasing timing."""
    return (len(t) >= 2 and bool(_np.all(_np.isfinite(t)))
            and not bool(_np.allclose(t, 0.0))
            and bool(_np.all(_np.diff(t) > 0)))


class _FrameStore:
    """Analysed frames in a disk-backed array instead of anonymous memory.

    Every analysed frame is held from decoding until keyframe selection. At
    1600 px from 2448x2048 MARS-LVIG video that is 6.4 MB a frame, and 280 of
    them (plus the undistortion copy since removed) OOM-killed a 6 GB job.
    Pages of a file mapping are reclaimable -- under memory pressure the kernel
    writes them out instead of killing the process -- and each slot is an
    ordinary ndarray view, so no consumer changes and the pixels are
    bit-identical to holding them in RAM.

    ``capacity`` comes from the container's frame count, which can be wrong;
    frames beyond it are kept in RAM rather than failing the run.
    """

    def __init__(self, path, shape, capacity):
        import weakref
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._mm = np.lib.format.open_memmap(
            self.path, mode="w+", dtype=np.uint8,
            shape=(max(int(capacity), 1),) + tuple(shape))
        self._n = 0
        # Removes the file even if the pipeline raises before close().
        self._finalizer = weakref.finalize(self, _FrameStore._unlink, self.path)

    @staticmethod
    def _unlink(path):
        try:
            path.unlink()
        except OSError:
            pass

    def put(self, img):
        if self._n >= len(self._mm) or img.shape != self._mm.shape[1:]:
            return img
        slot = self._mm[self._n]
        slot[...] = img
        self._n += 1
        return slot

    def close(self):
        self._mm = None
        self._finalizer()


def _adopt_pts(frames, pts_s, fps, *, pts_post=None):
    """Replace nominal timestamps with container PTS when they are trustworthy.

    Mutates ``frames`` in place.  Returns ``(source, warning_or_None)``.

    ``pts_s`` is ``CAP_PROP_POS_MSEC`` sampled before each ``read()`` and
    ``pts_post`` the same property sampled after it.  Backends disagree about
    which frame the property refers to, and the disagreement is worth exactly
    one frame interval -- 33 ms on a 30 Hz clip, but a full second on the
    variable-frame-rate missions built by ``scripts/build_agz_mission.py``,
    where it would pair every image with the GNSS sample of its predecessor.

    The series to trust is the one that is self-consistent: strictly increasing
    and not all zero.  When both qualify, the pre-read series wins, because a
    backend that reports the frame about to be decoded is the documented
    reading and the post-read series on such a backend is one frame ahead.  The
    remaining rejections -- all zeros, non-monotonic, or a span wildly
    inconsistent with the frame count and nominal rate -- keep the nominal
    clock, because silently trusting a broken PTS track would be worse than the
    assumption it replaces.
    """
    import numpy as _np
    t = _np.asarray(pts_s, float)
    source_note = None
    if not _usable_pts(t, _np) and pts_post is not None:
        t_post = _np.asarray(pts_post, float)
        if _usable_pts(t_post, _np):
            t = t_post
            source_note = ("video timestamps read after decode: this backend "
                           "reports POS_MSEC for the frame just returned")
    if len(t) < 2 or not _np.all(_np.isfinite(t)):
        return "nominal_fps", None
    if _np.allclose(t, 0.0):
        return "nominal_fps", None                    # no timing in the container
    if _np.any(_np.diff(t) <= 0):
        return ("nominal_fps",
                "video presentation timestamps are not strictly increasing; "
                "falling back to frame_index/fps timing (frame-to-GPS "
                "association may drift if the stream is variable-frame-rate)")
    nominal_span = (frames[-1][0] - frames[0][0]) / fps if fps else 0.0
    pts_span = float(t[-1] - t[0])
    if nominal_span > 0 and not (0.5 <= pts_span / nominal_span <= 2.0):
        return ("nominal_fps",
                f"video timestamps span {pts_span:.2f}s but the frame count and "
                f"fps imply {nominal_span:.2f}s; falling back to frame_index/fps")

    drift = float(_np.max(_np.abs(
        t - (t[0] + (_np.array([f[0] for f in frames]) - frames[0][0]) / fps))))
    for i, (fi, _, img) in enumerate(frames):
        frames[i] = (fi, float(t[i]), img)
    note = None
    if drift > 1.0 / max(fps, 1e-6):
        # Worth surfacing: this is exactly the case the nominal clock gets wrong.
        note = (f"using real video timestamps; they differ from frame_index/fps "
                f"by up to {drift:.3f}s (variable frame rate or dropped frames)")
    if source_note:
        note = f"{note}; {source_note}" if note else source_note
    return "container_pts", note


def _resolve_intrinsics(intr, ow, oh, pw, ph, sf, warnings, *, want_flag=False):
    """Build the processing-resolution camera matrix from supplied calibration.

    Intrinsics are only meaningful against the image size they were measured
    at. The scaling here used to assume that size was the video's own, which
    is right when the operator calibrated this camera at this resolution and
    silently wrong otherwise -- a calibration measured at 4K and applied to
    1080p footage is off by a factor of two in every term, and nothing said so.
    ``source_width``/``source_height`` let the operator state the calibration
    resolution; when they disagree with the video, the ratio is taken from the
    stated size and the substitution is recorded.
    """
    if intr and all(k in intr for k in ("fx", "fy", "cx", "cy")):
        cw = intr.get("source_width") or ow
        ch = intr.get("source_height") or oh
        if abs(cw / max(ch, 1) - ow / max(oh, 1)) > 0.02:
            warnings.append(
                f"calibration aspect ratio {cw}x{ch} does not match the video "
                f"{ow}x{oh}; a cropped or anamorphic source cannot be "
                "corrected by scaling alone and the result may be wrong")
        elif cw != ow:
            warnings.append(
                f"calibration was measured at {cw}x{ch} and the video is "
                f"{ow}x{oh}; intrinsics scaled by {pw / cw:.4f}")
        s = pw / cw
        K = np.array([[intr["fx"] * s, 0, intr["cx"] * s],
                      [0, intr["fy"] * s, intr["cy"] * s],
                      [0, 0, 1.0]], float)
        return (K, True) if want_flag else K
    if intr and "focal_length" in intr:
        f = intr["focal_length"] * (pw / ow)
        K = np.array([[f, 0, pw / 2], [0, f, ph / 2], [0, 0, 1.0]], float)
        # A focal length with no principal point is partial, not a calibration:
        # it seeds the solve but must not be frozen.
        return (K, False) if want_flag else K
    warnings.append("camera intrinsics not provided; estimated focal = 0.9*max(w,h). "
                    "Provide fx,fy,cx,cy for higher accuracy.")
    f = 0.9 * max(pw, ph)
    K = np.array([[f, 0, pw / 2], [0, f, ph / 2], [0, 0, 1.0]], float)
    return (K, False) if want_flag else K


def _maybe_gt_eval(video_path, telemetry_path, enu_frame, cloud):
    """If a ground_truth.json sits beside the video (synthetic fixture), evaluate."""
    gt_path = Path(video_path).parent / "ground_truth.json"
    if not gt_path.exists():
        return None
    try:
        gt = json.loads(gt_path.read_text())
        gt_pts = np.array(gt["scene_points_enu"])
        # ground_truth ENU is about its own origin; re-anchor to our enu_frame
        origin = gt["origin_wgs84"]
        from .geo import ENUFrame
        gt_frame = ENUFrame(origin["lat"], origin["lon"], origin["alt"])
        geo = gt_frame.enu_to_geodetic(gt_pts)
        gt_pts_ours = enu_frame.geodetic_to_enu(geo[:, 0], geo[:, 1], geo[:, 2])
        refs = gt.get("reference_distances")
        # re-anchor reference distance endpoints too
        refs_ours = []
        for rd in (refs or []):
            ab = gt_frame.enu_to_geodetic(np.array([rd["a"], rd["b"]]))
            ab2 = enu_frame.geodetic_to_enu(ab[:, 0], ab[:, 1], ab[:, 2])
            refs_ours.append({"name": rd["name"], "meters": rd["meters"],
                              "a": ab2[0].tolist(), "b": ab2[1].tolist()})
        return quality.evaluate_against_ground_truth(
            cloud.points, gt_pts_ours, refs_ours, cloud)
    except Exception:
        return None


#: How a single observation row came to exist. Recorded per row because the
#: two are different evidence: a sparse row's pixel was measured in that image
#: by a feature detector, while a dense row's pixel is the fused point
#: projected back into an image that `stereo_fusion` recorded as contributing
#: to it. Both name a genuine contributing image; only one is an original
#: image measurement.
OBS_SPARSE_FEATURE = 0
OBS_DENSE_FUSION_CONTRIBUTOR = 1
OBSERVATION_KIND_NAMES = {
    OBS_SPARSE_FEATURE: "sparse_feature_observation",
    OBS_DENSE_FUSION_CONTRIBUTOR: "dense_fusion_contributor",
}


def _dense_observations(recon, cloud, n_sparse, dense_vis,
                        dense_points=None, voxel=None, cameras_enu=None,
                        sel=None):
    """Observation rows for the dense points that survived fusion.

    A dense point's track is the set of images `stereo_fusion` fused it from --
    the same thing a sparse point's track is, arrived at photometrically rather
    than by feature matching. Without it a dense point falls back to the frustum
    basis and is refused `view_geometry_unverified`, which on the AGZ mission
    blocked all 60 sampled measurements despite the dense cloud producing *better*
    intervals than the sparse one.

    The pixel is obtained by projecting the point into each contributing camera.
    That is exact rather than circular here: fusion builds the point *from* those
    cameras' depth-map pixels, so the projection recovers the measurement rather
    than assuming it.

    Built after fusion, for survivors only -- 1.39 M dense points at five views
    each would be seven million rows, of which voxel downsampling keeps a fifth.

    Survivors are matched to their dense input **spatially**, not through
    ``source_index``. On the Open3D fusion path that index is a nearest-point
    mapping rather than a bijection (see DEC-009), so most dense survivors
    resolve to some other input and never find their own track: it attached
    lineage to 21.5% of the cloud instead of nearly all of it. A survivor is a
    voxel representative of the dense points around it, so the nearest dense
    input within half a voxel is the right attribution -- the same
    approximation Open3D already makes for confidence and sigma.
    """
    if dense_vis is None or recon.K is None or dense_points is None:
        return None
    if len(dense_points) == 0 or len(cloud) == 0:
        return None
    from scipy.spatial import cKDTree
    dense_points = np.asarray(dense_points, float).reshape(-1, 3)
    d, nn = cKDTree(dense_points).query(cloud.points)
    # One voxel diagonal: a survivor is a representative of the dense points in
    # its cell, so anything inside the cell is the same surface patch. Beyond
    # it the survivor came from somewhere else -- a sparse point, most likely --
    # and must not inherit a dense track.
    tol = float(voxel) * np.sqrt(3.0) if voxel else float(np.median(d)) * 3.0
    rows = np.flatnonzero(d <= tol)
    if len(rows) == 0:
        return None
    # The cloud is in ENU and `recon.cameras` are in the reconstruction frame.
    # Projecting one through the other puts most points behind the camera and
    # silently drops them: it attached lineage to 17% of the cloud. The ENU
    # poses are the ones that belong with ENU points.
    if not cameras_enu or sel is None:
        return None
    # `cameras_enu` is keyed by decoded frame index; visibility lists carry
    # keyframe indices. Translating once here is the third time this pair has
    # had to be kept apart explicitly (DEC-009, DEC-015) -- conflating them
    # finds no camera and drops the observation without complaint.
    #
    # Vectorised: one (point, view) pair per row, projected camera by camera.
    # The per-pair Python loop this replaces ran ~13 M iterations on DJI_1003.
    # Row order (by cloud point, then by the track's own order) is unchanged.
    from . import mvs as _mvs
    flat, offsets = (dense_vis if isinstance(dense_vis, tuple)
                     else _mvs.ragged_to_csr(dense_vis))
    flat = np.asarray(flat, np.int64)
    offsets = np.asarray(offsets, np.int64)
    src = nn[rows].astype(np.int64)
    lens = offsets[src + 1] - offsets[src]
    pair_row = np.repeat(rows, lens)
    starts = np.repeat(offsets[src], lens)
    within = np.arange(int(lens.sum())) - np.repeat(np.cumsum(lens) - lens, lens)
    pair_kf = flat[starts + within]

    sel_arr = np.asarray(sel, np.int64)
    ok = (pair_kf >= 0) & (pair_kf < len(sel_arr))
    frame_of_cam = {int(c["frame_index"]): j for j, c in enumerate(cameras_enu)}
    cam_j = np.full(len(pair_kf), -1, np.int64)
    cam_j[ok] = [frame_of_cam.get(int(f), -1) for f in sel_arr[pair_kf[ok]]] \
        if ok.any() else []
    K = np.asarray(recon.K, float)
    uv_all = np.zeros((len(pair_kf), 2), np.float64)
    keep = np.zeros(len(pair_kf), bool)
    for j, cam in enumerate(cameras_enu):
        m = np.flatnonzero(cam_j == j)
        if not len(m):
            continue
        R = np.asarray(cam["R"], float)
        C = np.asarray(cam["C"], float)
        c = (cloud.points[pair_row[m]] - C) @ R.T
        front = c[:, 2] > 1e-6
        m, c = m[front], c[front]
        uv_all[m, 0] = K[0, 0] * c[:, 0] / c[:, 2] + K[0, 2]
        uv_all[m, 1] = K[1, 1] * c[:, 1] / c[:, 2] + K[1, 2]
        keep[m] = True
    if not keep.any():
        return None
    return (pair_row[keep].astype(np.int32), pair_kf[keep].astype(np.int32),
            uv_all[keep].astype(np.float32))


def _remap_observations(recon, cloud, decoded_of_keyframe, *, n_sparse=None,
                        dense_vis=None, dense_points=None, voxel=None,
                        cameras_enu=None):
    """Re-express the reconstruction's observation lineage onto the fused cloud.

    The lineage `sfm`/`colmap_adapter` produce indexes the *pre-fusion* point
    array, and fusion reindexes the cloud. ``cloud.source_index`` is the map
    back, so this inverts it and drops observations whose point did not survive
    downsampling or outlier removal -- a discarded point's measurements are not
    evidence for whatever point happened to take its place.

    Returns ``None`` when the engine produced no lineage, which is what keeps
    every consumer able to tell "no observations were recorded" apart from "this
    point has no observations".
    """
    has_sparse = (getattr(recon, "obs_point", None) is not None
                  and len(recon.obs_point) > 0)
    if cloud.source_index is None or not (has_sparse or dense_vis is not None):
        return None

    n_src = int(cloud.source_index.max()) + 1 if len(cloud.source_index) else 0
    if has_sparse:
        n_src = max(n_src, int(recon.obs_point.max()) + 1)
    # Inverse of source_index: pre-fusion row -> fused row, or -1 if dropped.
    inverse = np.full(n_src, -1, np.int32)
    valid_rows = cloud.source_index >= 0          # inferred points carry -1
    inverse[cloud.source_index[valid_rows]] = np.flatnonzero(valid_rows).astype(
        np.int32)

    if has_sparse:
        fused = inverse[recon.obs_point]
        keep = fused >= 0
        pts_out = fused[keep].astype(np.int32)
        kf = recon.obs_frame[keep]
        uv_out = np.asarray(recon.obs_uv, np.float32)[keep]
    else:
        pts_out = np.zeros(0, np.int32)
        kf = np.zeros(0, np.int32)
        uv_out = np.zeros((0, 2), np.float32)

    # Dense points carry their own tracks, already in fused-cloud indices and
    # in frame numbers rather than keyframe indices.
    dense_rows = (_dense_observations(recon, cloud, n_sparse, dense_vis,
                                      dense_points, voxel, cameras_enu, decoded_of_keyframe)
                  if dense_vis is not None else None)
    if dense_rows is None and len(pts_out) == 0:
        return None
    # Two frame numberings exist and confusing them silently mislabels every
    # piece of evidence: `obs_frame` is the keyframe index the solver used,
    # while `decoded_of_keyframe` maps that to the decoded frame index the operator
    # mission's frame_index.csv speak in. Both are stored.
    sel_arr = np.asarray(decoded_of_keyframe, np.int32)
    decoded = np.where(kf < len(sel_arr), sel_arr[np.clip(kf, 0, len(sel_arr) - 1)],
                       -1).astype(np.int32)
    # Sparse and dense rows are not the same kind of record and must not be
    # readable as one. A sparse row's `uv` is the pixel a feature detector
    # measured and the solver triangulated from; a dense row's `uv` is that
    # point projected back into an image known to have contributed to it. Both
    # identify a real contributing image -- that is what licenses acceptance --
    # but only the first is an original image measurement, and evidence that
    # shows them to an operator has to say which it is holding.
    out = {"point_index": pts_out, "keyframe_index": kf.astype(np.int32),
           "frame_index": decoded, "uv": uv_out,
           "observation_kind": np.full(len(pts_out),
                                       OBS_SPARSE_FEATURE, np.uint8)}
    if dense_rows is not None:
        d_pt, d_kf, d_uv = dense_rows
        d_dec = np.where(d_kf < len(sel_arr),
                         sel_arr[np.clip(d_kf, 0, len(sel_arr) - 1)],
                         -1).astype(np.int32)
        out = {"point_index": np.concatenate([out["point_index"], d_pt]),
               "keyframe_index": np.concatenate([out["keyframe_index"], d_kf]),
               "frame_index": np.concatenate([out["frame_index"], d_dec]),
               "uv": np.vstack([out["uv"], d_uv]),
               "observation_kind": np.concatenate([
                   out["observation_kind"],
                   np.full(len(d_pt), OBS_DENSE_FUSION_CONTRIBUTOR, np.uint8)])}
    return out


def _write_artifacts(art_dir, cloud, cameras_enu, enu_frame, report, timeline,
                     gps_enu_all, sel, metrics, *, K=None, image_size=None,
                     observations=None):
    artifacts = {}
    # binary npz for API + PLY/LAS exports
    _extra = {}
    if cloud.sigma is not None:
        _extra["sigma"] = cloud.sigma
    if cloud.sigma_major is not None:
        _extra["sigma_major"] = cloud.sigma_major
    np.savez_compressed(art_dir / "cloud.npz", points=cloud.points,
                        colors=cloud.colors, confidence=cloud.confidence,
                        provenance=cloud.provenance, **_extra)
    artifacts["cloud_npz"] = str(art_dir / "cloud.npz")

    # Observation lineage: which image measurements produced each cloud point.
    # Written as its own artifact rather than into cloud.npz because it is one
    # row per observation, not per point, and a consumer that only wants
    # geometry should not have to load it.
    if observations is not None:
        np.savez_compressed(art_dir / "observations.npz",
                            point_index=observations["point_index"],
                            keyframe_index=observations["keyframe_index"],
                            frame_index=observations["frame_index"],
                            uv=observations["uv"],
                            observation_kind=observations["observation_kind"],
                            image_width=np.array([image_size[0] if image_size
                                                  else -1], np.int32),
                            image_height=np.array([image_size[1] if image_size
                                                   else -1], np.int32))
        artifacts["observations_npz"] = str(art_dir / "observations.npz")
    artifacts["ply"] = exports.export_ply(art_dir / "point_cloud.ply", cloud)

    # Whether this cloud may be placed on the earth is decided by the
    # alignment, never by the presence of a frame object. A relative-scale run
    # still builds an ENUFrame -- ENUFrame(0, 0, 0), a placeholder so later
    # stages have one -- and handing that to the exporter would project an
    # arbitrary-scale reconstruction into UTM off the coast of Africa and
    # label the result in metres. `build_report` also emits alignment=None for
    # such a run, so `.get("alignment", {})` returns None rather than the
    # default: the key is present, its value is not a dict.
    alignment = report.get("alignment") or {}
    scale_source = alignment.get("scale_source")
    georeferenced = bool(alignment) and scale_source not in (
        None, "", "none", "relative", "arbitrary")
    export_frame = enu_frame if georeferenced else None

    try:
        artifacts["las"] = exports.export_las(art_dir / "point_cloud.las",
                                              cloud, export_frame)
    except Exception as e:
        report.setdefault("warnings", []).append(f"LAS export skipped: {e}")
    # Every cloud export is local ENU; the sidecar is what makes it placeable,
    # or states plainly that it is not.
    artifacts["georeference"] = exports.export_georeference_sidecar(
        art_dir / "georeference.json", cloud, export_frame,
        extra={"scale_source": scale_source,
               "georeferenced": georeferenced,
               "units": "metres" if georeferenced else "reconstruction units"})

    # web viewer payload: downsample to <= 120k points for the browser
    n = len(cloud)
    keep = np.arange(n)
    if n > 120000:
        keep = np.random.default_rng(0).choice(n, 120000, replace=False)
    viewer = {
        "frame": enu_frame.to_dict(),
        "points": cloud.points[keep].round(3).tolist(),
        "colors": cloud.colors[keep].tolist(),
        "confidence": cloud.confidence[keep].round(3).tolist(),
        "provenance": cloud.provenance[keep].astype(int).tolist(),
        "cameras": cameras_enu,
        "bbox": {"min": cloud.points.min(0).tolist() if n else [0, 0, 0],
                 "max": cloud.points.max(0).tolist() if n else [0, 0, 0]},
    }
    (art_dir / "viewer.json").write_text(json.dumps(viewer))
    artifacts["viewer"] = str(art_dir / "viewer.json")

    # trajectory JSON (recon cameras + raw GPS track for the map)
    if gps_enu_all is not None:
        geo = enu_frame.enu_to_geodetic(gps_enu_all)
        gps_track = [[float(la), float(lo), float(al)] for la, lo, al in geo]
    else:
        gps_track = []   # no-GPS / relative-scale run
    traj = {
        "frame": enu_frame.to_dict(),
        # Intrinsics and the size they were solved at: a stored camera pose is
        # not usable for projection without them, and re-deriving them from a
        # config later is how a viewer and the backend end up disagreeing about
        # what a camera could see.
        "K": None if K is None else np.asarray(K, float).tolist(),
        "image_size": None if image_size is None else list(map(int, image_size)),
        "cameras_enu": cameras_enu,
        "gps_track_wgs84": gps_track,
        "cameras_wgs84": enu_frame.enu_to_geodetic(
            np.array([c["C"] for c in cameras_enu])).tolist() if cameras_enu else [],
    }
    (art_dir / "trajectory.json").write_text(json.dumps(traj))
    artifacts["trajectory"] = str(art_dir / "trajectory.json")

    artifacts["trajectory_csv"] = exports.export_trajectory_csv(
        art_dir / "trajectory.csv", cameras_enu)
    artifacts["geojson"] = exports.export_geojson(
        art_dir / "trajectory.geojson", cameras_enu, enu_frame)

    # frame metrics
    (art_dir / "frame_metrics.json").write_text(
        json.dumps([m.to_dict() for m in metrics]))
    artifacts["frame_metrics"] = str(art_dir / "frame_metrics.json")
    (art_dir / "keyframes.json").write_text(json.dumps(timeline))
    artifacts["keyframes"] = str(art_dir / "keyframes.json")

    artifacts["report_json"] = exports.export_report_json(
        art_dir / "quality_report.json", report)
    artifacts["report_html"] = exports.export_report_html(
        art_dir / "quality_report.html", report)
    return artifacts


def _write_manifest(project_dir, vinfo, treport, params, artifacts, warnings,
                    *, leveling=None, align=None, timing_source="nominal_fps",
                    alignment=None):
    manifest = {
        "version": "0.1.0",
        "created": time.time(),
        "video_sha256": vinfo.sha256,
        "params": params.__dict__,
        "telemetry_valid": treport.n_valid,
        "artifacts": {k: Path(v).name for k, v in artifacts.items()},
        "warnings": warnings,
        "coordinate_frame": "local ENU (metres) about telemetry origin",
        "units": "metres",
        "frame_timing_source": timing_source,
        # Every spatial transform applied to the deliverables, so an exported
        # coordinate can always be traced back to the fit that produced it.
        "transforms": {
            "recon_to_enu": align.transform.to_dict() if align is not None else None,
            "gravity_leveling": leveling,
        },
        # GNSS altitude is ellipsoidal here (EPSG:4979); it is NOT orthometric
        # height above a geoid.  Recorded explicitly so a consumer never assumes
        # the wrong vertical datum.
        "vertical_datum": "WGS84 ellipsoidal (EPSG:4979); not orthometric/geoid",
        # Where the metric scale came from and how well determined it is. A
        # measurement's interval is dominated by this on anything longer than a
        # few metres, so it belongs in the artifact manifest rather than only
        # in a report that is not written to disk.
        "alignment": alignment,
    }
    (project_dir / "artifacts" / "manifest.json").write_text(json.dumps(manifest, indent=2))
