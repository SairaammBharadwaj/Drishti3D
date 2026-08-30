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
from .geo import robust_sim3

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
    gravity_align: bool = True          # level the cloud so the ground is horizontal
    # Densification: "none" keeps the pure classical (sparse, all-observed) cloud;
    # "depth" fuses a monocular depth prior (Depth Anything V2) to fill the single-
    # pass holes, tagging every added point AI_ASSISTED (excluded from measurement).
    densify: str = "none"               # none | depth
    depth_stride: int = 8               # pixel grid stride for depth back-projection


@dataclass
class PipelineResult:
    project_dir: str
    artifacts: dict = field(default_factory=dict)
    report: dict = field(default_factory=dict)
    warnings: list = field(default_factory=list)


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
            treport = tel.TelemetryReport([], 0, 0, [], False, None)
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
    with stage_timer("frames"):
        cap = cv2.VideoCapture(str(video_path))
        fps = vinfo.fps
        stride = max(1, int(np.ceil(vinfo.frame_count / params.max_analyze_frames)))
        sf = 1.0
        frames = []          # (frame_index, timestamp, bgr) at processing scale
        idx = 0
        while True:
            ok, fr = cap.read()
            if not ok:
                break
            if idx % stride == 0:
                if fr.shape[1] > params.proc_max_width:
                    sf = params.proc_max_width / fr.shape[1]
                    fr = cv2.resize(fr, (params.proc_max_width,
                                         int(round(fr.shape[0] * sf))))
                frames.append((idx, idx / fps, fr))
                _emit(progress, "frames", len(frames) /
                      (vinfo.frame_count / stride + 1), "decoding")
            idx += 1
        cap.release()
        if len(frames) < 2:
            raise RuntimeError("could not decode enough frames from video")
        proc_h, proc_w = frames[0][2].shape[:2]

    # intrinsics (override -> telemetry -> estimate), scaled to processing size
    K = _resolve_intrinsics(params.intrinsics or treport.intrinsics,
                            vinfo.width, vinfo.height, proc_w, proc_h, sf, warnings)

    # 4) FRAME QUALITY -------------------------------------------------------
    with stage_timer("quality"):
        _emit(progress, "quality", 0.2, "scoring frames")
        metrics = frame_quality.analyze(frames)
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
        kf_frames = [frames[i][2] for i in sel]
        kf_gps = gps_enu_all[sel] if gps_enu_all is not None else None
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
            recon = colmap_adapter.reconstruct_frames(
                kf_frames, K, progress=lambda m, f: _emit(progress, "sfm", f, m))
        else:
            recon = sfm.reconstruct(
                kf_frames, K, masks=masks, positions=kf_gps,
                progress=lambda m, f: _emit(progress, "sfm", f, m))
        if recon.stats["n_points"] == 0:
            raise RuntimeError("reconstruction produced no 3D points")

    # 8b) DENSIFY (optional monocular depth-prior fusion) --------------------
    dense_local = None
    dense_cols_local = None
    with stage_timer("densify"):
        if params.densify == "depth":
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

    # 9) GEOREGISTRATION (Sim3 to GPS ENU) -----------------------------------
    with stage_timer("georegistration"):
        _emit(progress, "georegistration", 0.3,
              "relative scale" if no_gps else "aligning to GPS")
        reg_local_idx = [c.frame_index for c in recon.cameras]  # index into sel
        cam_centers = np.array([c.center for c in recon.cameras])
        align = None
        scale_source = "relative"
        dense_enu = None
        if not no_gps and kf_gps is not None and len(cam_centers) >= 3:
            gps_for_cams = kf_gps[reg_local_idx]
            acc_for_cams = [kf_acc[i] for i in reg_local_idx]
            weights = np.array([1.0 / a if a else 1.0 for a in acc_for_cams])
            align = robust_sim3(cam_centers, gps_for_cams, weights=weights,
                                threshold=3.0)
            scale_source = "rtk" if treport.has_rtk else "gps"
            pts_enu = align.transform.apply(recon.points)
            cams_enu = [align.transform.apply(c.center)[0] for c in recon.cameras]
            if dense_local is not None:
                dense_enu = align.transform.apply(dense_local)
        else:
            if not no_gps:
                warnings.append("fewer than 3 registered cameras; metric scale unavailable")
            pts_enu = recon.points
            cams_enu = [c.center for c in recon.cameras]
            dense_enu = dense_local
        # Level the scene: correct residual tilt so the ground is horizontal and
        # "up" is truly up (nadir GPS barely constrains the vertical axis).
        if params.gravity_align and len(pts_enu) > 200:
            from .geo import level_rotation
            Rlvl = level_rotation(pts_enu)
            if Rlvl is not None:
                c0 = pts_enu.mean(0)
                pts_enu = (Rlvl @ (pts_enu - c0).T).T + c0
                cams_enu = [(Rlvl @ (np.asarray(ce) - c0)) + c0 for ce in cams_enu]
                if dense_enu is not None:
                    dense_enu = (Rlvl @ (dense_enu - c0).T).T + c0
                warnings.append("applied gravity/level correction so the ground "
                                "plane is horizontal in the viewer")
        _emit(progress, "georegistration", 1.0,
              f"scale={align.transform.scale:.3f}" if align else "relative scale")

    # 10) FUSION -------------------------------------------------------------
    with stage_timer("fusion"):
        _emit(progress, "fusion", 0.3, "cleaning cloud")
        cloud = fusion.fuse(pts_enu, recon.colors, recon.confidence,
                            voxel=params.voxel)
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
            cloud = fusion.add_inferred_layer(cloud, dpts, dcols)
        _emit(progress, "fusion", 1.0, f"{len(cloud)} points")

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
        report = quality.build_report(
            video_info=vinfo, telemetry_report=treport, frame_metrics=metrics,
            keyframe_count=len(sel), recon_stats=recon.stats, align_result=align,
            cloud=cloud, timings=timings, gt_eval=gt_eval, warnings=warnings,
            scale_source=scale_source)
        _emit(progress, "report", 1.0, "report ready")

    # 13) EXPORTS + viewer payload ------------------------------------------
    with stage_timer("exports"):
        cameras_enu = [{"frame_index": int(sel[c.frame_index]),
                        "C": list(map(float, ce))}
                       for c, ce in zip(recon.cameras, cams_enu)]
        artifacts = _write_artifacts(art_dir, cloud, cameras_enu, enu_frame,
                                     report, timeline, gps_enu_all, sel, metrics)
        if mesh_path:
            artifacts["mesh_glb"] = mesh_path
        _emit(progress, "exports", 1.0, "artifacts written")

    _write_manifest(project_dir, vinfo, treport, params, artifacts, warnings)
    result = PipelineResult(str(project_dir), artifacts, report, warnings)
    return result


class _StageTimer:
    def __init__(self, name, sink):
        self.name, self.sink = name, sink

    def __enter__(self):
        self.t = time.time()
        return self

    def __exit__(self, *a):
        self.sink[self.name] = round(time.time() - self.t, 3)


def _resolve_intrinsics(intr, ow, oh, pw, ph, sf, warnings):
    if intr and all(k in intr for k in ("fx", "fy", "cx", "cy")):
        s = pw / ow
        return np.array([[intr["fx"] * s, 0, intr["cx"] * s],
                         [0, intr["fy"] * s, intr["cy"] * s],
                         [0, 0, 1.0]], float)
    if intr and "focal_length" in intr:
        f = intr["focal_length"] * (pw / ow)
        return np.array([[f, 0, pw / 2], [0, f, ph / 2], [0, 0, 1.0]], float)
    warnings.append("camera intrinsics not provided; estimated focal = 0.9*max(w,h). "
                    "Provide fx,fy,cx,cy for higher accuracy.")
    f = 0.9 * max(pw, ph)
    return np.array([[f, 0, pw / 2], [0, f, ph / 2], [0, 0, 1.0]], float)


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


def _write_artifacts(art_dir, cloud, cameras_enu, enu_frame, report, timeline,
                     gps_enu_all, sel, metrics):
    artifacts = {}
    # binary npz for API + PLY/LAS exports
    np.savez_compressed(art_dir / "cloud.npz", points=cloud.points,
                        colors=cloud.colors, confidence=cloud.confidence,
                        provenance=cloud.provenance)
    artifacts["cloud_npz"] = str(art_dir / "cloud.npz")
    artifacts["ply"] = exports.export_ply(art_dir / "point_cloud.ply", cloud)
    try:
        artifacts["las"] = exports.export_las(art_dir / "point_cloud.las", cloud, enu_frame)
    except Exception as e:
        report.setdefault("warnings", []).append(f"LAS export skipped: {e}")

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


def _write_manifest(project_dir, vinfo, treport, params, artifacts, warnings):
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
    }
    (project_dir / "artifacts" / "manifest.json").write_text(json.dumps(manifest, indent=2))
