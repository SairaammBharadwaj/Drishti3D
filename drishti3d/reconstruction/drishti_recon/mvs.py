"""Dense multi-view stereo: observed geometry, not inferred.

Why this exists
---------------
Until this module, the pipeline shipped only the **sparse** SfM cloud -- the
feature points that were matched and triangulated, and nothing else. On the AGZ
mission that is 17,898 points for 233 m of flight, and it looks like what it is:
a scattering of corners. Plan section 5.3 asks for dense geometry explicitly
("Create dense observed geometry using multi-view stereo where the capture
supports it") and it had not been built.

The distinction that matters
----------------------------
There are two ways to make a cloud look dense, and they are not
interchangeable:

* **Multi-view stereo**, here. Every point is triangulated from photometric
  agreement across several real images. It is *observed* geometry and carries
  the same provenance as the sparse points -- measurable, subject to the same
  uncertainty rules.
* **A monocular depth prior** (``densify="depth"``, :mod:`depth_prior`). A model
  predicts depth from one image. It fills holes convincingly and it is
  **inferred**: every point is tagged ``AI_ASSISTED`` and excluded from
  measurement by default.

Both make the viewer look better. Only one of them may be measured, and
confusing them is the failure this whole product is built to avoid.

Backends
--------
``colmap``
    COLMAP's PatchMatch stereo, via the ``colmap`` executable. The reference
    implementation and by far the best output. **Requires a CUDA-enabled
    COLMAP**: the PyPI ``pycolmap`` wheels are CPU-only and its own error is
    explicit -- *"Dense stereo reconstruction requires CUDA or HIP, neither of
    which is available on your system."* So this backend shells out to a
    separately installed binary rather than using the Python bindings.

``none``
    The default. Sparse only.

Whatever produced them, dense points enter the cloud as observed geometry and
must carry a positional uncertainty like any other measured point; see
:func:`depth_uncertainty`.
"""
from __future__ import annotations

import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np


@dataclass
class DenseResult:
    """Dense points in the *reconstruction* frame, with their support."""

    points: np.ndarray                  # (N,3)
    colors: np.ndarray                  # (N,3) uint8
    #: How many images contributed to each point, when the backend reports it.
    n_views: np.ndarray | None = None
    #: Ragged per-point lists of contributing images -- the dense equivalent of
    #: a sparse point's track. These are **keyframe indices**: `run_colmap`
    #: translates COLMAP's visibility positions through ``frame_order`` before
    #: returning, so consumers must not translate again. (This docstring used
    #: to describe the untranslated form and caused exactly that double
    #: translation.)
    vis_images: list | None = None
    #: The same tracks as ``(flat, offsets)``: point ``i``'s keyframes are
    #: ``flat[offsets[i]:offsets[i + 1]]``. What the pipeline consumes; the
    #: ragged list is built only on request (see :meth:`tracks`).
    vis_csr: tuple | None = None
    #: Frame index of each workspace image, in visibility-index order.
    frame_order: list | None = None
    #: Per-point 1-sigma, metres in the reconstruction frame.
    sigma: np.ndarray | None = None
    backend: str = ""
    stats: dict = field(default_factory=dict)

    def __len__(self) -> int:
        return int(self.points.shape[0])

    def tracks_csr(self):
        """``(flat, offsets)`` of keyframe indices, from whichever form is held."""
        if self.vis_csr is not None:
            return self.vis_csr
        if self.vis_images is not None:
            return ragged_to_csr(self.vis_images)
        return None


def colmap_executable() -> str | None:
    """Path to a usable ``colmap`` binary, or ``None``.

    The Python bindings are not enough: dense stereo needs CUDA and the
    published wheels are built without it.
    """
    return shutil.which("colmap")


def available() -> dict:
    """What dense backends this installation can actually run."""
    exe = colmap_executable()
    cuda = False
    if exe:
        try:
            out = subprocess.run([exe, "patch_match_stereo", "--help"],
                                 capture_output=True, text=True, timeout=60)
            blob = (out.stdout + out.stderr).lower()
            cuda = "requires cuda" not in blob
        except Exception:                  # noqa: BLE001
            cuda = False
    return {
        "colmap": {
            "executable": exe,
            "available": bool(exe) and cuda,
            "detail": ("ready" if exe and cuda else
                       "no colmap executable on PATH" if not exe else
                       "colmap found but built without CUDA; dense stereo "
                       "cannot run"),
            "setup": "Install a CUDA-enabled COLMAP, e.g. "
                     "`BUILD_CUDA=ON CUDA_ARCH=native yay -S colmap` on Arch. "
                     "The PyPI pycolmap wheels are CPU-only and cannot do this.",
        },
    }


#: Disparity precision of dense stereo, in pixels. **Not** the sparse
#: reconstruction's reprojection residual, which is feature-localisation
#: precision and far tighter: SIFT keypoints sit on corners and are found to a
#: fraction of a pixel, while patch-match matches a window over whatever texture
#: is there. Using the sparse residual (0.49 px on the AGZ mission) gave dense
#: points a median sigma of 5 mm against the bundle-adjusted sparse points'
#: 36 mm -- seven times more certain than the geometry they were triangulated
#: from, which is impossible.
DENSE_PIXEL_SIGMA = 1.0

#: Contributing views beyond this stop reducing the error. Fusion's supporting
#: images are consecutive frames of one pass looking at the same surface from
#: nearly the same place: their disparity errors are correlated, so ``sqrt(n)``
#: over all of them treats dependent measurements as independent ones.
MAX_INDEPENDENT_VIEWS = 4.0


#: Below this parallax a dense point is effectively unconstrained in depth and
#: the estimate is reported as such rather than as a very large but precise
#: number. Half a degree over a 50 m range is a 0.44 m baseline.
MIN_PARALLAX_DEG = 0.5


def ragged_to_csr(view_indices):
    """Ragged per-point index lists as ``(flat, offsets)``.

    ``offsets`` has one more entry than there are points; point ``i``'s indices
    are ``flat[offsets[i]:offsets[i + 1]]``. One concatenation instead of
    millions of small arrays is what makes per-point work vectorisable.
    """
    lens = np.fromiter((len(v) for v in view_indices), np.int64,
                       count=len(view_indices))
    offsets = np.zeros(len(lens) + 1, np.int64)
    np.cumsum(lens, out=offsets[1:])
    flat = (np.concatenate([np.asarray(v, np.int64).ravel() for v in view_indices])
            if offsets[-1] else np.zeros(0, np.int64))
    return flat, offsets


#: Bytes of scratch the vectorised parallax may use per chunk.
_PARALLAX_CHUNK_BYTES = 256 * 2**20


def contributing_parallax_deg(points, centres, view_indices=None, *,
                              csr=None) -> np.ndarray:
    """Widest angle between the rays that actually produced each point.

    ``view_indices`` is the ragged per-point list of contributing image indices
    -- a dense point's track -- or pass ``csr=(flat, offsets)`` directly. This
    is the quantity that decides how well depth is constrained, and it was
    previously not consulted at all: uncertainty was computed from range and a
    view *count*, so two images 40 degrees apart and two images half a degree
    apart produced the same number.

    Indices outside ``centres`` and rays of zero length are ignored. Returns
    NaN where fewer than two valid rays remain.

    Vectorised by track length: every point with the same number of views is
    one batched Gram matrix. On DJI_1003's 2.63 M dense points this took 37.5 s
    as a per-point loop.
    """
    pts = np.asarray(points, float).reshape(-1, 3)
    c = np.asarray(centres, float).reshape(-1, 3)
    out = np.full(len(pts), np.nan)
    if not len(c) or (view_indices is None and csr is None):
        return out
    flat, offsets = csr if csr is not None else ragged_to_csr(view_indices)
    flat = np.asarray(flat, np.int64)
    offsets = np.asarray(offsets, np.int64)
    lens = np.diff(offsets)
    for L in np.unique(lens):
        if L < 2:
            continue
        rows_all = np.flatnonzero(lens == L)
        step = max(1, int(_PARALLAX_CHUNK_BYTES // (8 * (L * L + 4 * L))))
        for s0 in range(0, len(rows_all), step):
            rows = rows_all[s0:s0 + step]
            ids = flat[offsets[rows, None] + np.arange(L)]
            ok_id = (ids >= 0) & (ids < len(c))
            rays = c[np.where(ok_id, ids, 0)] - pts[rows, None, :]
            norms = np.linalg.norm(rays, axis=2)
            valid = ok_id & (norms > 1e-9)
            unit = rays / np.where(valid, norms, 1.0)[..., None]
            dots = np.einsum("nik,njk->nij", unit, unit)
            dots = np.where(valid[:, :, None] & valid[:, None, :], dots, 1.0)
            ang = np.degrees(np.arccos(np.clip(dots.min(axis=(1, 2)), -1.0, 1.0)))
            ang[valid.sum(axis=1) < 2] = np.nan
            out[rows] = ang
    return out


def depth_uncertainty(points, centres, n_views, *, sigma_px: float,
                      focal: float, floor=None, parallax_deg=None) -> np.ndarray:
    """1-sigma for a dense point, from the geometry that produced it.

    Each contributing ray localises the point transversely to within about
    ``eps = r * sigma_px / f`` at range ``r`` and focal length ``f``. Two rays
    meeting at angle ``alpha`` fix it to

        sigma ~= eps / sin(alpha)

    which diverges as the rays become parallel, is smallest at
    ``alpha = 90`` degrees where it equals ``eps``, and is symmetric about
    that: rays 120 degrees apart constrain a point exactly as well as rays
    60 degrees apart.

    Two earlier forms were wrong in opposite directions. The original omitted
    the angle entirely and reported ``eps`` -- the transverse localisation
    scale used as though it were the depth error, which silently asserts that
    every dense point was seen from 45 degrees apart. Its replacement used
    ``1 / tan(alpha)``, taken from the small-baseline derivation
    ``B ~= r * tan(alpha)``, which holds only for small angles: it reported
    **zero** uncertainty at exactly 90 degrees, making a point infinitely well
    known, and **negative** uncertainty beyond it. ``1 / sin(alpha)`` agrees
    with ``1 / tan(alpha)`` to 0.4% at 5 degrees, so the narrow-angle regime
    that dominates a drone pass is unchanged, and it stays correct over the
    whole domain :func:`contributing_parallax_deg` can return.

    ``parallax_deg`` supplies the measured angle per point (see
    :func:`contributing_parallax_deg`). Where it is absent or below
    :data:`MIN_PARALLAX_DEG` the point is reported as ``inf`` -- unconstrained
    in depth, which the measurement layer already reads as "not observable".
    Clamping the angle up to the threshold instead, as the previous version
    did, turned an unmeasurable point into a finite number and contradicted
    this paragraph.

    Contributing views reduce the result, but only up to
    :data:`MAX_INDEPENDENT_VIEWS` -- past which they are the same look from
    almost the same place.

    ``floor`` is the uncertainty of the sparse geometry this point sits in,
    combined in quadrature. It is the part that matters most. A dense point is
    triangulated from cameras whose poses are known only to the bundle
    adjustment's accuracy, so **it cannot be better known than the model it
    rides on** -- the same reasoning that puts a neighbourhood term on the local
    refit in DEC-014. Without it the stereo term alone reports millimetres on a
    model good to centimetres.

    This is deliberately a geometric estimate, not a propagated covariance:
    fusion does not report which images agreed at what disparity, so the full
    Jacobian of :mod:`uncertainty` cannot be formed. The caller says so in a
    warning on every run.
    """
    pts = np.asarray(points, float).reshape(-1, 3)
    if len(pts) == 0:
        return np.zeros(0)
    c = np.asarray(centres, float).reshape(-1, 3)
    from scipy.spatial import cKDTree
    rng = cKDTree(c).query(pts)[0] if len(c) else np.full(len(pts), np.nan)
    n = np.clip(np.asarray(n_views, float).reshape(-1)
                if n_views is not None else 2.0, 2.0, MAX_INDEPENDENT_VIEWS)

    # Transverse localisation of a single ray, before any triangulation.
    eps = rng * float(sigma_px) / max(float(focal), 1e-9) / np.sqrt(n)

    if parallax_deg is None:
        ang = np.full(len(pts), np.nan)
    else:
        ang = np.asarray(parallax_deg, float).reshape(-1).astype(float)

    # No measured angle, or one too small to constrain depth: the point is
    # unconstrained, not merely uncertain. Reporting inf is what lets the
    # measurement layer refuse it rather than quote a number for it.
    unconstrained = ~np.isfinite(ang) | (ang < MIN_PARALLAX_DEG)
    sin = np.sin(np.radians(np.where(unconstrained, 90.0, ang)))
    stereo = np.where(unconstrained, np.inf, eps / sin)

    if floor is None:
        return stereo
    # hypot(inf, floor) is inf, so an unconstrained point stays unconstrained.
    return np.hypot(stereo, float(floor))


def _read_ply(path: Path):
    """Points and colours from a COLMAP fused PLY (binary or ascii)."""
    import numpy as np
    with open(path, "rb") as fh:
        header, fmt, count, props = [], None, 0, []
        while True:
            line = fh.readline().decode("ascii", "replace").strip()
            header.append(line)
            if line.startswith("format"):
                fmt = line.split()[1]
            elif line.startswith("element vertex"):
                count = int(line.split()[-1])
            elif line.startswith("property") and count and not header[-2].startswith("element face"):
                props.append(line.split()[-1])
            elif line == "end_header":
                break
        if fmt == "binary_little_endian":
            dtype = []
            for line in header:
                if line.startswith("property "):
                    parts = line.split()
                    if parts[1] == "list":
                        continue
                    t = {"float": "<f4", "float32": "<f4", "double": "<f8",
                         "uchar": "u1", "uint8": "u1", "int": "<i4"}.get(parts[1])
                    if t:
                        dtype.append((parts[2], t))
            arr = np.frombuffer(fh.read(np.dtype(dtype).itemsize * count),
                                dtype=dtype, count=count)
            xyz = np.stack([arr["x"], arr["y"], arr["z"]], 1).astype(float)
            if all(k in arr.dtype.names for k in ("red", "green", "blue")):
                rgb = np.stack([arr["red"], arr["green"], arr["blue"]],
                               1).astype(np.uint8)
            else:
                rgb = np.full((count, 3), 200, np.uint8)
            return xyz, rgb
        rows = np.loadtxt(path, skiprows=len(header), max_rows=count)
        xyz = rows[:, :3].astype(float)
        rgb = (rows[:, 3:6].astype(np.uint8) if rows.shape[1] >= 6
               else np.full((count, 3), 200, np.uint8))
        return xyz, rgb


def _read_visibility_csr(path: Path, n_points: int):
    """COLMAP's ``.vis`` sidecar as ``(counts, flat, offsets)``, or Nones.

    The file is ``uint64 n`` then, per point, ``uint32 k`` and ``k`` uint32
    image indices. Where each record starts depends on every earlier count, so
    finding the heads is one integer walk; the rest is array slicing. The old
    reader did two file reads per point and built 2.6 M arrays (3.7 s on
    DJI_1003); consumers now take the flat form.
    """
    if not path.exists():
        return None, None, None
    try:
        raw = path.read_bytes()
        n = int(np.frombuffer(raw[:8], dtype="<u8", count=1)[0])
        if n != n_points:
            return None, None, None
        body = np.frombuffer(raw[8:], dtype="<u4")
        b = body.tolist()
        heads = np.empty(n, np.int64)
        pos = 0
        for i in range(n):
            heads[i] = pos
            pos += 1 + b[pos]
        if pos != len(body):
            return None, None, None
        counts = body[heads].astype(np.int32)
        offsets = np.zeros(n + 1, np.int64)
        np.cumsum(counts, out=offsets[1:])
        # Every body entry that is not a head is an index, in order.
        is_head = np.zeros(len(body), bool)
        is_head[heads] = True
        flat = body[~is_head].astype(np.int32)
        return counts, flat, offsets
    except Exception:                      # noqa: BLE001 - optional detail
        return None, None, None


def _read_visibility(path: Path, n_points: int):
    """Ragged form of :func:`_read_visibility_csr`: ``(counts, [indices...])``."""
    counts, flat, offsets = _read_visibility_csr(path, n_points)
    if counts is None:
        return None, None
    return counts, np.split(flat, offsets[1:-1])


def translate_csr(flat, offsets, table):
    """Map CSR indices through ``table``, dropping any past its end.

    Returns the new ``(flat, offsets)``. Dropping rather than clamping matches
    the ragged form this replaces, where an out-of-range visibility index was
    filtered out of that point's list.
    """
    flat = np.asarray(flat, np.int64)
    offsets = np.asarray(offsets, np.int64)
    table = np.asarray(table)
    keep = (flat >= 0) & (flat < len(table))
    row = np.repeat(np.arange(len(offsets) - 1), np.diff(offsets))
    lens = np.bincount(row[keep], minlength=len(offsets) - 1)
    new_off = np.zeros(len(offsets), np.int64)
    np.cumsum(lens, out=new_off[1:])
    return table[flat[keep]].astype(np.int32), new_off


def csr_rows(flat, offsets):
    """Ragged list view of a CSR pair, for callers that still want one."""
    return np.split(np.asarray(flat), np.asarray(offsets)[1:-1])


def _workspace_frame_order(dense: Path):
    """Frame index of each workspace image, in the order visibility refers to.

    ``stereo_fusion``'s visibility indices are positions in the
    reconstruction's image list -- not COLMAP image ids, and not our frame
    numbers. `colmap_adapter` names each workspace image after its keyframe
    index, so the name carries the mapping, but the *order* has to come from the
    model. Getting it wrong would attribute every dense point to the wrong
    cameras, silently.
    """
    try:
        import pycolmap
        rec = pycolmap.Reconstruction(str(dense / "sparse"))
        pairs = sorted((int(i), im.name) for i, im in rec.images.items())
        return [int(Path(name).stem) for _i, name in pairs]
    except Exception:                      # noqa: BLE001 - optional detail
        return None


#: COLMAP's own PatchMatch defaults for the controls exposed below, as of
#: 4.1.0. Recorded so a run's stats say what was used even when a caller left
#: a setting alone.
PATCH_MATCH_DEFAULTS = {"num_src_images": 20, "window_step": 1,
                        "num_iterations": 5, "num_samples": 15}


def _limit_source_images(dense: Path, n: int) -> None:
    """Rewrite ``patch-match.cfg`` so each reference uses ``n`` source images.

    ``image_undistorter`` writes ``__auto__, 20`` per image: COLMAP picks the
    20 best-overlapping images by shared sparse points. There is no command-line
    flag for that number, so the config is the interface.
    """
    cfg = dense / "stereo" / "patch-match.cfg"
    lines = cfg.read_text().splitlines()
    out = []
    for line in lines:
        if line.strip().startswith("__auto__"):
            line = f"__auto__, {int(n)}"
        out.append(line)
    cfg.write_text("\n".join(out) + "\n")


def _dense_focal(dense: Path, max_image_size: int | None = None):
    """Mean focal length, in pixels, of the images dense stereo actually used.

    Stereo can work on smaller images than the sparse model
    (``max_image_size``), so its pixel noise is in *those* pixels. Converting
    it with the sparse model's focal length would claim unchanged confidence
    for a lower-resolution run. Stereo downscales each image so its longer
    side is at most ``max_image_size``; the focal scales with it.
    """
    try:
        import pycolmap
        rec = pycolmap.Reconstruction(str(dense / "sparse"))
        fs = []
        for c in rec.cameras.values():
            s = 1.0
            if max_image_size and max_image_size > 0:
                s = min(1.0, float(max_image_size) / max(c.width, c.height))
            fs.append(float(c.mean_focal_length()) * s)
        return float(np.mean(fs)) if fs else None
    except Exception:                      # noqa: BLE001 - optional detail
        return None


def run_colmap(workspace, *, max_image_size: int = 1600,
               geom_consistency: bool = True, min_num_pixels: int = 5,
               num_src_images: int | None = None,
               window_step: int | None = None,
               num_iterations: int | None = None,
               num_samples: int | None = None,
               gpu_index: str | None = None,
               cache_size_gb: float | None = None,
               keep_depth_maps: bool = True,
               log_dir=None,
               progress=None) -> DenseResult:
    """PatchMatch stereo and fusion over a COLMAP workspace.

    ``workspace`` is the directory `colmap_adapter.reconstruct_frames` kept:
    ``images/`` and ``sparse/`` as COLMAP itself wrote them. Reusing its own
    output avoids re-exporting by hand what is already on disk, and avoids the
    two disagreeing.

    The PatchMatch controls default to ``None``, meaning COLMAP's own default
    (:data:`PATCH_MATCH_DEFAULTS`); ``stats["settings"]`` records the resolved
    values and ``stats["timings_s"]`` each substage. A value COLMAP would
    reject raises rather than silently falling back.
    """
    import time
    exe = colmap_executable()
    if not exe:
        raise RuntimeError(available()["colmap"]["setup"])
    for name, v, lo in (("num_src_images", num_src_images, 1),
                        ("window_step", window_step, 1),
                        ("num_iterations", num_iterations, 1),
                        ("num_samples", num_samples, 1)):
        if v is not None and (int(v) != v or v < lo):
            raise ValueError(f"{name} must be an integer >= {lo}, got {v!r}")
    if window_step is not None and window_step > 2:
        # COLMAP's CUDA kernel supports steps 1 and 2 only.
        raise ValueError("window_step must be 1 or 2")
    work = Path(workspace)
    images, sparse = work / "images", work / "sparse"
    if not images.is_dir() or not sparse.is_dir():
        raise RuntimeError(f"{work} is not a COLMAP workspace")
    dense = work / "dense"
    timings: dict = {}
    logs = Path(log_dir) if log_dir else None
    if logs:
        logs.mkdir(parents=True, exist_ok=True)

    def _p(msg, frac):
        if progress:
            progress(msg, frac)

    def _run(args, stage):
        t0 = time.perf_counter()
        out = subprocess.run([exe, *args], capture_output=True, text=True)
        timings[stage] = round(time.perf_counter() - t0, 2)
        if logs:
            (logs / f"{stage}.log").write_text(
                " ".join([exe, *args]) + "\n\n" + (out.stdout or "")
                + "\n" + (out.stderr or ""))
        if out.returncode != 0:
            tail = (out.stderr or out.stdout or "").strip().splitlines()
            raise RuntimeError(f"colmap {stage} failed: "
                               + " | ".join(tail[-3:] or ["no output"]))
        return out

    _p("mvs: undistorting", 0.1)
    # Undistort at native size and let stereo and fusion downscale. Resizing
    # in the undistorter crashes COLMAP 4.1's patch_match_stereo ("Check
    # failed: width_ == bitmap.Width() (1600 vs. 1280)"); it was never hit
    # before because every mission so far ran at its native width.
    _run(["image_undistorter", "--image_path", str(images),
          "--input_path", str(sparse), "--output_path", str(dense),
          "--output_type", "COLMAP"], "image_undistorter")
    if num_src_images is not None:
        _limit_source_images(dense, num_src_images)

    pm = ["--PatchMatchStereo.geom_consistency",
          "true" if geom_consistency else "false",
          "--PatchMatchStereo.max_image_size", str(max_image_size)]
    for flag, v in (("window_step", window_step),
                    ("num_iterations", num_iterations),
                    ("num_samples", num_samples)):
        if v is not None:
            pm += [f"--PatchMatchStereo.{flag}", str(int(v))]
    if gpu_index is not None:
        pm += ["--PatchMatchStereo.gpu_index", str(gpu_index)]
    if cache_size_gb is not None:
        pm += ["--PatchMatchStereo.cache_size", str(cache_size_gb)]

    _p("mvs: patch-match stereo", 0.3)
    _run(["patch_match_stereo", "--workspace_path", str(dense),
          "--workspace_format", "COLMAP", *pm], "patch_match_stereo")

    _p("mvs: fusing", 0.8)
    fused = dense / "fused.ply"
    fu = ["--StereoFusion.max_image_size", str(max_image_size)]
    if cache_size_gb is not None:
        fu += ["--StereoFusion.cache_size", str(cache_size_gb)]
    _run(["stereo_fusion", "--workspace_path", str(dense),
          "--workspace_format", "COLMAP",
          "--input_type", "geometric" if geom_consistency else "photometric",
          "--output_path", str(fused),
          "--StereoFusion.min_num_pixels", str(min_num_pixels), *fu],
         "stereo_fusion")
    if not fused.exists():
        raise RuntimeError("stereo_fusion produced no output")

    t0 = time.perf_counter()
    xyz, rgb = _read_ply(fused)
    vis, vflat, voff = _read_visibility_csr(dense / "fused.ply.vis", len(xyz))
    order = _workspace_frame_order(dense)
    # Translate visibility indices into frame numbers once, here, so nothing
    # downstream has to know about COLMAP's image ordering. Validated by
    # reprojection: 99.9% of the observations this produces land inside the
    # image that claims to have seen the point.
    vis_csr = None
    if vflat is not None and order is not None:
        vis_csr = translate_csr(vflat, voff, np.asarray(order, np.int32))
    focal = _dense_focal(dense, max_image_size)
    timings["read_outputs"] = round(time.perf_counter() - t0, 2)
    if not keep_depth_maps:
        # The depth and normal maps are gigabytes and nothing reads them after
        # fusion; the fused cloud and its visibility are what is kept.
        shutil.rmtree(dense / "stereo" / "depth_maps", ignore_errors=True)
        shutil.rmtree(dense / "stereo" / "normal_maps", ignore_errors=True)
        shutil.rmtree(dense / "stereo" / "consistency_graphs", ignore_errors=True)
    _p("mvs: done", 1.0)
    settings = {"max_image_size": max_image_size,
                "geom_consistency": geom_consistency,
                "min_num_pixels": min_num_pixels,
                "num_src_images": (num_src_images if num_src_images is not None
                                   else PATCH_MATCH_DEFAULTS["num_src_images"]),
                "window_step": (window_step if window_step is not None
                                else PATCH_MATCH_DEFAULTS["window_step"]),
                "num_iterations": (num_iterations if num_iterations is not None
                                   else PATCH_MATCH_DEFAULTS["num_iterations"]),
                "num_samples": (num_samples if num_samples is not None
                                else PATCH_MATCH_DEFAULTS["num_samples"]),
                "gpu_index": gpu_index if gpu_index is not None else "-1",
                "cache_size_gb": cache_size_gb}
    return DenseResult(points=xyz, colors=rgb, n_views=vis,
                       vis_csr=vis_csr, frame_order=order,
                       backend="colmap",
                       stats={"n_points": int(len(xyz)),
                              **settings,
                              "settings": settings,
                              "timings_s": timings,
                              "dense_focal_px": focal,
                              "workspace": str(work)})
