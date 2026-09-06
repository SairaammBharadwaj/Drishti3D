"""Optional COLMAP / PyCOLMAP verified-reconstruction adapter.

If PyCOLMAP is installed it can be used as a higher-accuracy alternative to the
built-in OpenCV SfM.  The default pipeline does not require it; ``is_available``
reflects the real install and the pipeline falls back to :mod:`sfm` otherwise.
"""
from __future__ import annotations

import importlib.util


def is_available() -> bool:
    try:
        return importlib.util.find_spec("pycolmap") is not None
    except (ImportError, ValueError):
        return False


SETUP = (
    "Install COLMAP (https://colmap.github.io) or `pip install pycolmap`. "
    "On Windows, prebuilt COLMAP binaries are available; add to PATH. "
    "GPU acceleration (CUDA) is optional but speeds up dense reconstruction."
)


def reconstruct_frames(frames, K, *, progress=None, single_camera=True):
    """Run COLMAP on in-memory BGR frames and return a ``sfm.ReconResult``.

    This lets the COLMAP engine drop into the same pipeline as the built-in
    OpenCV SfM (georegistration, fusion, exports, viewer all unchanged).
    Requires PyCOLMAP; raises with setup guidance otherwise.  COLMAP performs
    global bundle adjustment, which is what real wide-baseline aerial grids need.
    """
    if not is_available():
        raise RuntimeError("PyCOLMAP not installed. " + SETUP)
    import tempfile
    import shutil
    from pathlib import Path
    import numpy as np
    import cv2
    import pycolmap

    from .sfm import Camera, ReconResult

    def _p(msg, frac):
        if progress:
            progress(msg, frac)

    work = Path(tempfile.mkdtemp(prefix="drishti_colmap_"))
    img_dir = work / "images"
    img_dir.mkdir()
    for i, f in enumerate(frames):
        cv2.imwrite(str(img_dir / f"{i:04d}.jpg"), f, [cv2.IMWRITE_JPEG_QUALITY, 95])

    db = work / "db.db"
    # Cap threads so COLMAP cannot pin every core and freeze the machine.
    import os
    nthreads = max(1, min(4, (os.cpu_count() or 4) // 2))
    os.environ.setdefault("OMP_NUM_THREADS", str(nthreads))

    def _with_threads(factory):
        try:
            o = factory()
            if hasattr(o, "num_threads"):
                o.num_threads = nthreads
            return o
        except Exception:
            return None

    try:
        _p("colmap: features", 0.1)
        mode = pycolmap.CameraMode.SINGLE if single_camera else pycolmap.CameraMode.AUTO
        sift = _with_threads(lambda: pycolmap.SiftExtractionOptions())
        try:
            pycolmap.extract_features(str(db), str(img_dir), camera_mode=mode,
                                      sift_options=sift) if sift else \
                pycolmap.extract_features(str(db), str(img_dir), camera_mode=mode)
        except TypeError:
            pycolmap.extract_features(str(db), str(img_dir), camera_mode=mode)
        _p("colmap: matching", 0.35)
        # sequential matching is far lighter than exhaustive on CPU
        try:
            mopt = _with_threads(lambda: pycolmap.SequentialMatchingOptions())
            pycolmap.match_sequential(str(db), matching_options=mopt) if mopt else \
                pycolmap.match_sequential(str(db))
        except Exception:
            try:
                pycolmap.match_sequential(str(db))
            except Exception:
                pycolmap.match_exhaustive(str(db))
        _p("colmap: mapping", 0.6)
        mapopt = _with_threads(lambda: pycolmap.IncrementalPipelineOptions())
        try:
            maps = pycolmap.incremental_mapping(str(db), str(img_dir), str(work),
                                                options=mapopt) if mapopt else \
                pycolmap.incremental_mapping(str(db), str(img_dir), str(work))
        except TypeError:
            maps = pycolmap.incremental_mapping(str(db), str(img_dir), str(work))
        if not maps:
            raise RuntimeError("COLMAP produced no reconstruction")
        rec = maps[max(maps, key=lambda k: maps[k].num_reg_images()
                       if hasattr(maps[k], "num_reg_images") else len(maps[k].images))]

        cameras = []
        for img in rec.images.values():
            if not img.has_pose:
                continue
            cfw = img.cam_from_world()
            R = np.asarray(cfw.rotation.matrix(), float)
            t = np.asarray(cfw.translation, float).ravel()
            fidx = int(Path(img.name).stem)
            cameras.append(Camera(fidx, R, t))

        pts, cols, conf, oc, rep, ang = [], [], [], [], [], []
        errs = [p.error for p in rec.points3D.values() if p.has_error]
        max_err = max(4.0, float(np.percentile(errs, 95)) if errs else 4.0)
        for p in rec.points3D.values():
            pts.append(np.asarray(p.xyz, float))
            cols.append(np.asarray(p.color, np.uint8))
            tl = p.track.length()
            err = p.error if p.has_error else max_err
            oc.append(int(tl))
            rep.append(float(err))
            ang.append(0.0)
            c_obs = min(1.0, (tl - 2) / 4.0)
            c_rep = max(0.0, 1.0 - err / max_err)
            conf.append(float(0.5 * c_obs + 0.5 * c_rep))

        # recover K from the (shared) COLMAP camera
        cam = next(iter(rec.cameras.values()))
        params = np.asarray(cam.params, float)
        fx = params[0]
        cx = cam.principal_point_x if hasattr(cam, "principal_point_x") else params[1]
        cy = cam.principal_point_y if hasattr(cam, "principal_point_y") else params[2]
        Kout = np.array([[fx, 0, cx], [0, fx, cy], [0, 0, 1.0]], float)

        pts = np.array(pts) if pts else np.zeros((0, 3))
        result = ReconResult(
            points=pts,
            colors=np.array(cols, np.uint8) if cols else np.zeros((0, 3), np.uint8),
            confidence=np.array(conf) if conf else np.zeros(0),
            obs_count=np.array(oc, int) if oc else np.zeros(0, int),
            reproj_err=np.array(rep) if rep else np.zeros(0),
            tri_angle=np.array(ang) if ang else np.zeros(0),
            cameras=sorted(cameras, key=lambda c: c.frame_index),
            K=Kout,
        )
        result.stats = {
            "engine": "colmap",
            "n_keyframes": len(frames),
            "n_registered": len(cameras),
            "registered_fraction": len(cameras) / max(1, len(frames)),
            "n_points": int(pts.shape[0]),
            "median_reproj_err": float(np.median(rep)) if rep else None,
            "p90_reproj_err": float(np.percentile(rep, 90)) if rep else None,
            "mean_track_length": float(np.mean(oc)) if oc else None,
            "mean_tri_angle": None,
        }
        _p("colmap: done", 1.0)
        return result
    finally:
        shutil.rmtree(work, ignore_errors=True)


def reconstruct(image_dir, work_dir, intrinsics=None, *,
                num_threads=8, max_image_size=1920):
    """Run a COLMAP sparse reconstruction if available.

    Returns a dict with points/cameras compatible with the pipeline, or raises
    if PyCOLMAP is not installed.  This is a thin, optional path; the default
    verified engine is :func:`drishti_recon.sfm.reconstruct`.

    ``num_threads`` is capped deliberately.  COLMAP otherwise sizes its SIFT
    thread pool from the core count -- 24 extractors on this machine -- and each
    holds full-resolution scale-space buffers.  That took a 64-frame 1080p run
    past a 10 GB cgroup limit and returned SIGKILL.  ``max_image_size`` bounds
    the same buffers; COLMAP's own default is 3200, above our native width.
    """
    if not is_available():
        raise RuntimeError("PyCOLMAP not installed. " + SETUP)
    import pycolmap  # type: ignore
    import numpy as np
    from pathlib import Path

    work_dir = Path(work_dir)
    work_dir.mkdir(parents=True, exist_ok=True)
    db_path = work_dir / "database.db"

    ext = pycolmap.FeatureExtractionOptions()
    ext.num_threads = num_threads
    ext.max_image_size = max_image_size
    match = pycolmap.FeatureMatchingOptions()
    match.num_threads = num_threads
    mapper = pycolmap.IncrementalPipelineOptions()
    mapper.num_threads = num_threads

    pycolmap.extract_features(db_path, image_dir, extraction_options=ext)
    pycolmap.match_exhaustive(db_path, matching_options=match)
    maps = pycolmap.incremental_mapping(db_path, image_dir, work_dir, options=mapper)
    if not maps:
        raise RuntimeError("COLMAP produced no reconstruction")
    rec = maps[0]
    pts = np.array([p.xyz for p in rec.points3D.values()])
    cols = np.array([p.color for p in rec.points3D.values()], np.uint8)
    track = float(np.mean([p.track.length() for p in rec.points3D.values()])) if len(pts) else 0.0
    return {"points": pts, "colors": cols, "engine": "colmap",
            "num_images": rec.num_images(), "num_points": len(pts),
            "mean_track_length": track, "reconstruction": rec}
