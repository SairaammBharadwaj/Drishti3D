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


def _point_uncertainty(points, cam_list, K, obs_point, obs_frame, obs_uv):
    """Propagate per-point positional covariance for a COLMAP reconstruction.

    COLMAP returns geometry and a per-point reprojection error, but no
    covariance, and nothing downstream can invent one: an endpoint whose sigma
    is missing is reported ``not_observable``, so before this existed every
    measurement on a COLMAP reconstruction was refused for lack of an
    uncertainty the pipeline had simply never computed.

    The same estimator the in-repo engine uses is applied here on purpose, so
    the two engines' intervals mean the same thing and an engine comparison is
    not also a comparison of two noise models:

    * ``sigma_px`` comes from this reconstruction's own reprojection residuals
      via a normalised MAD, floored at 0.05 px.  A fixed 0.5 px on imagery whose
      residuals are 0.05 px inflates every interval about tenfold and makes the
      tolerance gate useless; the same constant on noisy imagery understates it.
      The MAD rather than an RMS because RANSAC and the reprojection filter
      leave a heavy tail.
    * :func:`uncertainty.point_covariances` then builds each point's normal
      matrix from the observations that actually produced it.

    Returns ``(PointUncertainty | None, sigma_px | None, error | None)``.
    Uncertainty is additive information: a failure here leaves the geometry
    intact and is *reported* in ``stats`` rather than raised -- and rather than
    swallowed, which is how the absence of this pass stayed invisible until a
    measurement refused itself for want of a sigma nobody had computed.
    """
    import numpy as np            # imported per-function, as elsewhere here

    if len(points) == 0 or len(cam_list) == 0 or len(obs_point) == 0:
        return None, None, "no points, cameras or observations"
    try:
        import cv2
        from . import uncertainty as _unc
        from . import bundle as _bundle

        # Observations carry the keyframe index; the covariance pass indexes
        # into the camera array. Map once, and drop observations whose camera
        # is not in the list rather than letting a stray index silently select
        # the wrong pose.
        row_of_frame = {int(c.frame_index): i for i, c in enumerate(cam_list)}
        cam_idx, pt_idx, uv = [], [], []
        for pi, fi, xy in zip(obs_point, obs_frame, obs_uv):
            r = row_of_frame.get(int(fi))
            if r is None:
                continue
            cam_idx.append(r)
            pt_idx.append(int(pi))
            uv.append(xy)
        if len(cam_idx) < 2:
            return None, None, "fewer than two usable observations"
        cam_idx = np.asarray(cam_idx, int)
        pt_idx = np.asarray(pt_idx, int)
        uv = np.asarray(uv, float).reshape(-1, 2)

        rvecs = np.array([cv2.Rodrigues(np.asarray(c.R, float))[0].ravel()
                          for c in cam_list], float)
        tvecs = np.array([np.asarray(c.t, float).ravel() for c in cam_list],
                         float)

        res = _bundle.reprojection_errors(rvecs, tvecs, points, cam_idx,
                                          pt_idx, uv, K)
        res = res[np.isfinite(res)]
        if len(res) >= 20:
            mad = float(np.median(np.abs(res - np.median(res))))
            sigma_px = max(1.4826 * mad, 0.05)
        else:
            sigma_px = _unc.DEFAULT_SIGMA_PX

        pu = _unc.point_covariances(points, cam_idx, pt_idx, uv, rvecs, tvecs,
                                    K, sigma_px=sigma_px)
        return pu, float(sigma_px), None
    except Exception as exc:          # noqa: BLE001 - never fatal, always named
        return None, None, f"{type(exc).__name__}: {exc}"


#: Below this many images, every pair is matched. n(n-1)/2 at 200 images is
#: 19,900 pairs, which is minutes; above it the quadratic cost stops being
#: worth paying and capture order is used instead.
EXHAUSTIVE_MATCH_MAX_IMAGES = 200


def reconstruct_frames(frames, K, *, progress=None, single_camera=True,
                       keep_workspace=None, fix_intrinsics=True):
    """Run COLMAP on in-memory BGR frames and return a ``sfm.ReconResult``.

    This lets the COLMAP engine drop into the same pipeline as the built-in
    OpenCV SfM (georegistration, fusion, exports, viewer all unchanged).
    Requires PyCOLMAP; raises with setup guidance otherwise.  COLMAP performs
    global bundle adjustment, which is what real wide-baseline aerial grids need.

    ``keep_workspace`` is a directory to move the scratch workspace into
    instead of deleting it.  Dense multi-view stereo needs the images and the
    sparse model COLMAP just wrote, and re-exporting them from the in-memory
    result would reconstruct by hand what is already on disk -- and risk
    disagreeing with it.  The path is recorded on ``result.stats`` so the
    caller can find it.
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
        modern = hasattr(pycolmap, "FeatureExtractionOptions")

        # The supplied calibration is handed to COLMAP and held fixed.
        #
        # This function took `K` and never used it. COLMAP therefore
        # self-calibrated from scratch, starting the principal point at the
        # image centre and the focal at its own heuristic. `reconstruct_dir`
        # was fixed for this ("previously this argument was accepted and
        # silently ignored") and this entry point -- the one the pipeline
        # actually calls -- was not.
        #
        # On a planar nadir flight the focal/depth ambiguity is barely
        # observable, so a free focal drifts and takes the scene depth with it.
        # Measured on UseGeo dataset 1 against a surveyed calibration: the
        # solved focal came out 1.45% low at 1600 px and 1.86% low at 3200 px,
        # and the reconstructed ground sat 1.25 m and 1.46 m too high at 80 m
        # range -- which is what a proportionally short depth looks like.
        # `fix_intrinsics` separates a measured calibration from an estimate.
        # DEC-038 fixed this path discarding a supplied calibration; holding
        # the *estimated* 0.9*max(w,h) focal fixed as well would be worse than
        # self-calibrating, because it freezes an arbitrary number instead of
        # solving for the real one. An estimate is still passed as the starting
        # value -- a good seed is worth having -- but bundle adjustment is left
        # free to move it.
        reader = None
        if K is not None:
            Kf = np.asarray(K, float)
            reader = pycolmap.ImageReaderOptions()
            reader.camera_model = "PINHOLE"
            reader.camera_params = ",".join(f"{v:.10g}" for v in (
                Kf[0, 0], Kf[1, 1], Kf[0, 2], Kf[1, 2]))
            mode = pycolmap.CameraMode.SINGLE

        try:
            if modern:
                ext = pycolmap.FeatureExtractionOptions()
                ext.num_threads = nthreads
                ext.max_image_size = max(f.shape[1] for f in frames)
                if reader is not None:
                    pycolmap.extract_features(
                        str(db), str(img_dir), camera_mode=mode,
                        reader_options=reader, extraction_options=ext,
                        device=pycolmap.Device.cpu)
                else:
                    pycolmap.extract_features(
                        str(db), str(img_dir), camera_mode=mode,
                        extraction_options=ext, device=pycolmap.Device.cpu)
            else:
                # Legacy pycolmap: no FeatureExtractionOptions, and no way to
                # pass reader options through this call signature. Warn rather
                # than silently self-calibrate, which is the failure this whole
                # block exists to stop.
                if K is not None:
                    import warnings as _w
                    _w.warn("pycolmap too old to accept fixed intrinsics here; "
                            "COLMAP will self-calibrate and depth may be biased",
                            RuntimeWarning)
                pycolmap.extract_features(str(db), str(img_dir), camera_mode=mode,
                                          sift_options=sift) if sift else \
                    pycolmap.extract_features(str(db), str(img_dir), camera_mode=mode)
        except TypeError:
            pycolmap.extract_features(str(db), str(img_dir), camera_mode=mode)
        _p("colmap: matching", 0.35)
        # Sequential matching only compares each image with its neighbours in
        # capture order. That is ideal for a straight pass and wrong for a
        # circuit: when the flight returns near where it began, the pair that
        # would close the loop is never attempted, the match graph comes apart,
        # and the mapper builds a scatter of small disconnected submaps.
        #
        # Measured on a 5m46 orbit of a church: 55 keyframes, sequential
        # matching, COLMAP restarted from a fresh initial pair **44 times** and
        # the largest surviving submap held 20 images -- 36% registered, and
        # analysing five times as many frames did not change that number,
        # because the missing information was the connections, not the frames.
        #
        # Exhaustive matching on 55 images is 1,485 pairs. The comment this
        # replaces was right that exhaustive is heavier -- it is O(n^2) -- but
        # at these counts that is seconds, and it is a superset of the
        # sequential pairs, so a straight pass loses nothing by it either.
        n_images = len(frames)
        exhaustive = n_images <= EXHAUSTIVE_MATCH_MAX_IMAGES
        _p(f"colmap: matching ({'exhaustive' if exhaustive else 'sequential'}, "
           f"{n_images} images, intrinsics "
           f"{'fixed' if fix_intrinsics else 'refined'})", 0.35)
        try:
            mopt = _with_threads(lambda: pycolmap.FeatureMatchingOptions() if modern
                                  else pycolmap.SequentialMatchingOptions())
            if exhaustive:
                pycolmap.match_exhaustive(str(db), matching_options=mopt) if mopt else \
                    pycolmap.match_exhaustive(str(db))
            else:
                pycolmap.match_sequential(str(db), matching_options=mopt) if mopt else \
                    pycolmap.match_sequential(str(db))
        except Exception:
            try:
                pycolmap.match_exhaustive(str(db)) if exhaustive else \
                    pycolmap.match_sequential(str(db))
            except Exception:
                pycolmap.match_exhaustive(str(db))
        _p("colmap: mapping", 0.6)
        mapopt = _with_threads(lambda: pycolmap.IncrementalPipelineOptions())
        if mapopt is not None and K is not None and fix_intrinsics:
            # Fixed, not merely initialised. Letting bundle adjustment refine a
            # focal it was handed defeats the point of supplying one, and on
            # this acquisition geometry it is exactly what drifted.
            try:
                mapopt.ba_refine_focal_length = False
                mapopt.ba_refine_principal_point = False
                mapopt.ba_refine_extra_params = False
            except Exception:                              # older pycolmap
                pass
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
        # image_id -> keyframe index. COLMAP's own image ids are database
        # identifiers; the rest of the pipeline keys everything off the keyframe
        # index encoded in the written filename, so the track observations below
        # are translated once here rather than leaking two numbering schemes.
        frame_of_image = {}
        for img in rec.images.values():
            if not img.has_pose:
                continue
            cfw = img.cam_from_world()
            R = np.asarray(cfw.rotation.matrix(), float)
            t = np.asarray(cfw.translation, float).ravel()
            fidx = int(Path(img.name).stem)
            frame_of_image[int(img.image_id)] = fidx
            cameras.append(Camera(fidx, R, t))

        pts, cols, conf, oc, rep, ang = [], [], [], [], [], []
        obs_point, obs_frame, obs_uv = [], [], []
        errs = [p.error for p in rec.points3D.values() if p.has_error]
        max_err = max(4.0, float(np.percentile(errs, 95)) if errs else 4.0)
        for p in rec.points3D.values():
            pi = len(pts)
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
            # COLMAP carries the full track: image id plus the index of the 2D
            # point within that image. Elements whose image never registered are
            # skipped -- their measurement contributed nothing to this point.
            for el in p.track.elements:
                fidx = frame_of_image.get(int(el.image_id))
                if fidx is None:
                    continue
                img = rec.images[el.image_id]
                obs_point.append(pi)
                obs_frame.append(fidx)
                obs_uv.append(np.asarray(
                    img.points2D[el.point2D_idx].xy, np.float32))

        # recover K from the (shared) COLMAP camera
        cam = next(iter(rec.cameras.values()))
        params = np.asarray(cam.params, float)
        fx = params[0]
        cx = cam.principal_point_x if hasattr(cam, "principal_point_x") else params[1]
        cy = cam.principal_point_y if hasattr(cam, "principal_point_y") else params[2]
        Kout = np.array([[fx, 0, cx], [0, fx, cy], [0, 0, 1.0]], float)

        pts = np.array(pts) if pts else np.zeros((0, 3))
        cam_list = sorted(cameras, key=lambda c: c.frame_index)
        pu, sig_px, unc_error = _point_uncertainty(pts, cam_list, Kout,
                                                    obs_point, obs_frame,
                                                    obs_uv)
        result = ReconResult(
            points=pts,
            colors=np.array(cols, np.uint8) if cols else np.zeros((0, 3), np.uint8),
            confidence=np.array(conf) if conf else np.zeros(0),
            obs_count=np.array(oc, int) if oc else np.zeros(0, int),
            reproj_err=np.array(rep) if rep else np.zeros(0),
            tri_angle=np.array(ang) if ang else np.zeros(0),
            cameras=cam_list,
            K=Kout,
            point_cov=None if pu is None else pu.cov,
            point_sigma=None if pu is None else pu.sigma,
            point_sigma_major=None if pu is None else pu.sigma_major,
            point_observable=None if pu is None else pu.observable,
            obs_point=(np.array(obs_point, np.int32) if obs_point
                       else np.zeros(0, np.int32)),
            obs_frame=(np.array(obs_frame, np.int32) if obs_frame
                       else np.zeros(0, np.int32)),
            obs_uv=(np.array(obs_uv, np.float32) if obs_uv
                    else np.zeros((0, 2), np.float32)),
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
            "n_observations": len(obs_point),
            "uncertainty": {
                "sigma_px_estimated": sig_px,
                "n_with_covariance": (0 if pu is None
                                      else int(np.isfinite(pu.sigma).sum())),
                "n_observable": (0 if pu is None
                                 else int(np.sum(pu.observable))),
                "error": unc_error,
                "median_sigma_recon_frame": (
                    None if pu is None or not np.any(np.isfinite(pu.sigma))
                    else float(np.median(pu.sigma[np.isfinite(pu.sigma)]))),
            },
        }
        if keep_workspace is not None:
            kept = Path(keep_workspace)
            shutil.rmtree(kept, ignore_errors=True)
            kept.parent.mkdir(parents=True, exist_ok=True)
            (work / "sparse").mkdir(parents=True, exist_ok=True)
            rec.write(str(work / "sparse"))
            shutil.move(str(work), str(kept))
            work = kept                    # so the finally clause does not
            result.stats["workspace"] = str(kept)   # delete what we just kept
        _p("colmap: done", 1.0)
        return result
    finally:
        if keep_workspace is None:
            shutil.rmtree(work, ignore_errors=True)


def reconstruct(image_dir, work_dir, intrinsics=None, *,
                num_threads=8, max_image_size=1920, single_camera=True,
                position_priors=None, prior_sigma_m=5.0):
    """Run a COLMAP sparse reconstruction if available.

    Returns a dict with points/cameras compatible with the pipeline, or raises
    if PyCOLMAP is not installed.  This is a thin, optional path; the default
    verified engine is :func:`drishti_recon.sfm.reconstruct`.

    ``num_threads`` is capped deliberately.  COLMAP otherwise sizes its SIFT
    thread pool from the core count -- 24 extractors on this machine -- and each
    holds full-resolution scale-space buffers.  That took a 64-frame 1080p run
    past a 10 GB cgroup limit and returned SIGKILL.  ``max_image_size`` bounds
    the same buffers; COLMAP's own default is 3200, above our native width.

    ``intrinsics``, when given, is a dict with ``fx``, ``fy``, ``cx``, ``cy`` and
    optionally ``k1``, ``k2``, ``p1``, ``p2``.  They are held fixed rather than
    refined.  Previously this argument was accepted and silently ignored.

    ``position_priors`` maps image filename -> (x, y, z) in a metric Cartesian
    frame (UTM, say).  Supplying it turns on COLMAP's prior-position bundle
    adjustment, which is what keeps a straight single pass from bowing: with no
    loop closure, small rotation errors accumulate into a low-frequency bend that
    a free reconstruction has nothing to correct against.  ``prior_sigma_m`` is
    the per-axis 1-sigma of those priors; a robust loss is used so individual GNSS
    outliers do not drag the solution.
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

    # Camera handling.  Left to itself COLMAP's AUTO mode gives every image its
    # own camera and self-calibrates each one.  On a well-conditioned capture
    # that converges (a 64-frame pass agreed on f to within 1%), but on a nearly
    # straight trajectory the focal/depth ambiguity is barely observable and the
    # per-image estimates diverge -- measured 1062..2044 px against a surveyed
    # 893.4.  So: share one camera across the pass, and when the true intrinsics
    # are known, fix them instead of solving for them.
    reader = pycolmap.ImageReaderOptions()
    mode = pycolmap.CameraMode.SINGLE if single_camera else pycolmap.CameraMode.AUTO
    if intrinsics is not None:
        fx, fy, cx, cy = intrinsics["fx"], intrinsics["fy"], intrinsics["cx"], intrinsics["cy"]
        k1, k2, p1, p2 = (intrinsics.get(k, 0.0) for k in ("k1", "k2", "p1", "p2"))
        reader.camera_model = "OPENCV"
        reader.camera_params = ",".join(
            f"{v:.10g}" for v in (fx, fy, cx, cy, k1, k2, p1, p2))
        mode = pycolmap.CameraMode.SINGLE
        mapper.ba_refine_focal_length = False
        mapper.ba_refine_extra_params = False

    pycolmap.extract_features(db_path, image_dir, camera_mode=mode,
                              reader_options=reader, extraction_options=ext)
    pycolmap.match_exhaustive(db_path, matching_options=match)

    prior_offset = None
    if position_priors:
        # Centre the priors. UTM northings run to 5.2e6; handing Ceres residuals
        # built from coordinates that large costs significant conditioning, and
        # the solved frame is shifted back afterwards so the caller still gets
        # coordinates in the original datum.
        import numpy as _np
        _P = _np.asarray(list(position_priors.values()), float)
        prior_offset = _P.mean(axis=0)
        centred = {k: (_np.asarray(v, float) - prior_offset)
                   for k, v in position_priors.items()}
        n = _write_position_priors(pycolmap, db_path, centred, prior_sigma_m)
        if n:
            mapper.use_prior_position = True
            mapper.use_robust_loss_on_prior_position = True

    maps = pycolmap.incremental_mapping(db_path, image_dir, work_dir, options=mapper)
    if not maps:
        raise RuntimeError("COLMAP produced no reconstruction")
    rec = maps[0]
    if prior_offset is not None:
        # Shift back into the caller's datum -- and write it, so the model on disk
        # agrees with the object returned. Transforming only the in-memory copy
        # left every saved reconstruction sitting at the centred origin, which
        # reads as a ~5.2e6 m error against any georeferenced check.
        rec.transform(pycolmap.Sim3d(1.0, pycolmap.Rotation3d(), prior_offset))
        for sub in sorted(work_dir.glob("*")):
            if sub.is_dir() and (sub / "images.bin").exists():
                rec.write(str(sub))
                break
    pts = np.array([p.xyz for p in rec.points3D.values()])
    cols = np.array([p.color for p in rec.points3D.values()], np.uint8)
    track = float(np.mean([p.track.length() for p in rec.points3D.values()])) if len(pts) else 0.0
    return {"points": pts, "colors": cols, "engine": "colmap",
            "num_images": rec.num_images(), "num_points": len(pts),
            "mean_track_length": track, "reconstruction": rec,
            "prior_offset": None if prior_offset is None else prior_offset.tolist()}


def _write_position_priors(pycolmap, db_path, priors, sigma_m):
    """Attach metric position priors to the database images. Returns the count.

    COLMAP already populates a pose prior per image from EXIF GPS during feature
    extraction, in WGS84 and with an undefined covariance.  Inserting alongside
    those trips a uniqueness constraint, so existing rows are updated in place --
    which is also what we want, since it lets us state the covariance rather than
    leave it NaN.
    """
    import numpy as np
    db = pycolmap.Database.open(str(db_path))
    try:
        cov = np.eye(3) * float(sigma_m) ** 2
        by_image = {}
        for pp in db.read_all_pose_priors():
            by_image[int(pp.corr_data_id.id)] = pp
        written = 0
        for img in db.read_all_images():
            xyz = priors.get(img.name)
            if xyz is None:
                continue
            pp = by_image.get(int(img.image_id))
            if pp is None:
                pp = pycolmap.PosePrior()
                pp.corr_data_id = pycolmap.data_t(
                    pycolmap.sensor_t(pycolmap.SensorType.CAMERA, img.camera_id),
                    img.image_id)
            pp.position = np.asarray(xyz, float)
            pp.position_covariance = cov
            pp.coordinate_system = pycolmap.PosePriorCoordinateSystem.CARTESIAN
            if int(getattr(pp, "pose_prior_id", 2**32 - 1)) != 2**32 - 1:
                db.update_pose_prior(pp)
            else:
                db.write_pose_prior(pp)
            written += 1
    finally:
        db.close()
    return written
