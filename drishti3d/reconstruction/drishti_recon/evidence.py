"""What supports a measurement, assembled from the stored artifacts.

This is the evidence side of plan features F3 and F5.  Given a reconstruction's
artifacts and a point in ENU metres, it answers: which cameras could see this,
how much parallax do they provide, is it on established surface, and where did
the metric scale come from.

Two bases for view support, and the difference matters
------------------------------------------------------
When ``observations.npz`` is present, support comes from **observation
lineage**: the image measurements that actually produced each point, carried
from the solver's tracks through fusion's reindexing.  Support is then counted
over the frames that measured the point, and the parallax reported is the
parallax those measurements provided.  Evidence built this way is stamped
``view_support_basis="triangulated_observations"`` and can license acceptance.

Without it, support falls back to camera *geometry*: a camera counts if the
point falls in front of it and inside its image and the coverage grid says the
sight line is clear.  That is a real test and useful for ranking candidate
frames, but it counts cameras that may never have contributed an observation,
so its parallax is an **upper bound**.  Such evidence is stamped
``frustum_upper_bound``, which :func:`~.questions.evaluate` treats as blocking
acceptance -- overstating parallax is exactly the error that would let a
one-direction measurement pass the degeneracy check.

An endpoint is matched to lineage by snapping to the nearest cloud point within
:data:`LINEAGE_SNAP_FACTOR` times the local point spacing.  A selection that
lands further than that from any reconstructed point has no lineage to inherit,
and falls back rather than borrowing a distant point's evidence.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from .questions import Evidence
from .provenance import Provenance


#: How far an operator's selection may sit from a reconstructed point and still
#: inherit its observation lineage, as a multiple of the median nearest-neighbour
#: spacing of the cloud. Two spacings is roughly "the selection is on this
#: point"; beyond that the nearest point is a different piece of surface and its
#: measurements are not evidence for what was selected.
LINEAGE_SNAP_FACTOR = 2.0


@dataclass
class ReconstructionEvidence:
    """Camera geometry, coverage and observation lineage for one reconstruction."""

    centres: np.ndarray               # (M,3) ENU camera centres
    rotations: np.ndarray | None      # (M,3,3) world->camera in ENU, or None
    frame_indices: list
    K: np.ndarray | None
    image_size: tuple | None
    coverage: object | None = None    # CoverageGrid
    scale_source: str = "none"
    scale_sigma_rel: float = float("nan")
    #: Cloud positions, needed only to snap a selection onto a point that has
    #: lineage. ``None`` when ``cloud.npz`` was not loadable.
    points: np.ndarray | None = None
    #: Observation lineage from ``observations.npz``: ``point_index`` rows
    #: indexing ``points``, the keyframe and decoded frame each measurement came
    #: from, and its pixel. ``None`` when the engine recorded none.
    observations: dict | None = None
    #: Camera row for each *decoded* frame index, so a measurement's frame can
    #: be turned back into a pose without a linear scan. Keyed by the decoded
    #: index, not the solver's keyframe index: the exported cameras carry the
    #: decoded one, and observations carry both precisely so the two numbering
    #: schemes never have to be guessed between.
    _camera_of_frame: dict = None

    # ---- construction ---------------------------------------------------- #
    @classmethod
    def load(cls, artifacts_dir) -> "ReconstructionEvidence":
        art = Path(artifacts_dir)
        traj = json.loads((art / "trajectory.json").read_text())
        cams = traj.get("cameras_enu") or []
        centres = np.array([c["C"] for c in cams], float).reshape(-1, 3)
        Rs = ([np.asarray(c["R"], float) for c in cams]
              if cams and "R" in cams[0] else None)
        rotations = np.stack(Rs) if Rs else None
        K = np.asarray(traj["K"], float) if traj.get("K") else None
        size = tuple(traj["image_size"]) if traj.get("image_size") else None

        cov = None
        npz = art / "coverage.npz"
        if npz.exists():
            from .coverage import CoverageGrid
            d = np.load(npz)
            cov = CoverageGrid(origin=d["origin"], voxel=float(d["voxel"][0]),
                               shape=tuple(int(x) for x in d["shape"]),
                               status=d["status"], view_count=d["view_count"],
                               best_incidence_deg=d["best_incidence_deg"],
                               free_count=d["free_count"]
                               if "free_count" in d.files else None)

        scale_source, scale_sigma = "none", float("nan")
        man = art / "manifest.json"
        if man.exists():
            try:
                m = json.loads(man.read_text())
                al = (m.get("alignment") or {})
                scale_source = al.get("scale_source") or "none"
                # `scale_sigma` is the absolute 1-sigma of the fitted similarity
                # scale *factor*, whose magnitude depends on the reconstruction's
                # arbitrary internal units. Dividing by the factor is what makes
                # it the relative scale error that multiplies every measured
                # length -- using it raw would report a 1.2% scale error as 19%
                # on one run and 5% on another purely because the two solvers
                # chose different internal units.
                sig = al.get("scale_sigma")
                sc = al.get("scale")
                if (sig is not None and sc and np.isfinite(float(sig))
                        and np.isfinite(float(sc)) and float(sc) > 0):
                    scale_sigma = float(sig) / float(sc)
            except (ValueError, KeyError, TypeError):
                pass
        points = None
        cloud_npz = art / "cloud.npz"
        if cloud_npz.exists():
            try:
                points = np.load(cloud_npz)["points"]
            except (OSError, ValueError, KeyError):
                points = None

        observations = None
        obs_npz = art / "observations.npz"
        if obs_npz.exists():
            try:
                d = np.load(obs_npz)
                observations = {"point_index": d["point_index"],
                                "keyframe_index": d["keyframe_index"],
                                "frame_index": d["frame_index"],
                                "uv": d["uv"]}
            except (OSError, ValueError, KeyError):
                observations = None

        frame_indices = [c.get("frame_index") for c in cams]
        cam_of_frame = {int(f): i for i, f in enumerate(frame_indices)
                        if f is not None}
        return cls(centres, rotations, frame_indices, K, size, cov,
                   scale_source, scale_sigma, points, observations,
                   cam_of_frame)

    # ---- observation lineage ---------------------------------------------- #
    @property
    def has_lineage(self) -> bool:
        return (self.observations is not None and self.points is not None
                and len(self.observations["point_index"]) > 0)

    def _spacing(self) -> float:
        """Median nearest-neighbour distance of the cloud, cached."""
        if getattr(self, "_spacing_cache", None) is not None:
            return self._spacing_cache
        from scipy.spatial import cKDTree
        pts = self.points
        if pts is None or len(pts) < 2:
            self._spacing_cache = float("inf")
            return self._spacing_cache
        # A sample is enough for a median and keeps this O(k log N) on a cloud
        # that can hold hundreds of thousands of points.
        idx = np.arange(len(pts)) if len(pts) <= 5000 else \
            np.random.default_rng(0).choice(len(pts), 5000, replace=False)
        d, _ = cKDTree(pts).query(pts[idx], k=2)
        self._spacing_cache = float(np.median(d[:, 1]))
        return self._spacing_cache

    #: Fallback radius when the cloud is too small to have a spacing at all.
    #: A single-point cloud has no neighbour distance, and treating that as an
    #: infinite tolerance would let any selection anywhere inherit its lineage,
    #: while treating it as zero would reject a selection sitting exactly on the
    #: point. Neither is right, so an exact hit is required instead.
    _DEGENERATE_SNAP_M = 1e-6

    def lineage_point(self, point) -> int:
        """Cloud index whose lineage a selection may inherit, or ``-1``.

        Returns ``-1`` when the selection is further from every reconstructed
        point than :data:`LINEAGE_SNAP_FACTOR` spacings. Inheriting a distant
        point's measurements would attribute evidence to a piece of surface that
        was never the one selected.
        """
        if self.points is None or len(self.points) == 0:
            return -1
        from scipy.spatial import cKDTree
        if getattr(self, "_tree", None) is None:
            self._tree = cKDTree(self.points)
        d, i = self._tree.query(np.asarray(point, float).reshape(3))
        spacing = self._spacing()
        radius = (LINEAGE_SNAP_FACTOR * spacing if np.isfinite(spacing)
                  else self._DEGENERATE_SNAP_M)
        if d > radius:
            return -1
        return int(i)

    def observations_of(self, point) -> dict:
        """The measurements that produced the point a selection snaps to.

        Returns ``{"point_index", "keyframe_index", "frame_index", "uv"}`` with
        one row per measurement, or empty arrays when there is no lineage for
        this selection.
        """
        empty = {"point_index": -1,
                 "keyframe_index": np.zeros(0, np.int32),
                 "frame_index": np.zeros(0, np.int32),
                 "uv": np.zeros((0, 2), np.float32)}
        if not self.has_lineage:
            return empty
        pi = self.lineage_point(point)
        if pi < 0:
            return empty
        obs = self.observations
        m = obs["point_index"] == pi
        if not m.any():
            return empty
        return {"point_index": pi,
                "keyframe_index": obs["keyframe_index"][m],
                "frame_index": obs["frame_index"][m],
                "uv": obs["uv"][m]}

    def measured_ray_separation_deg(self, point) -> float:
        """Parallax actually provided by the measurements that made this point.

        This is the figure that licenses acceptance, because it is computed over
        the cameras that contributed an observation rather than over every
        camera that happened to have the point in frame.
        """
        obs = self.observations_of(point)
        if len(obs["frame_index"]) < 2:
            return 0.0
        rows = [self._camera_of_frame.get(int(f)) for f in obs["frame_index"]]
        rows = [r for r in rows if r is not None]
        if len(rows) < 2:
            return 0.0
        return self.max_ray_separation_deg(point, np.asarray(sorted(set(rows))))

    # ---- queries ---------------------------------------------------------- #
    def visible_cameras(self, point) -> np.ndarray:
        """Indices of cameras with ``point`` in front of them and in frame.

        Without rotations or intrinsics the frustum test cannot be run at all,
        and this returns an empty set rather than falling back to "every camera
        within some distance", which would be a made-up answer.
        """
        p = np.asarray(point, float).reshape(3)
        if self.rotations is None or self.K is None or self.image_size is None:
            return np.zeros(0, int)
        w, h = self.image_size
        rel = p[None, :] - self.centres                 # (M,3)
        cam = np.einsum("mij,mj->mi", self.rotations, rel)
        z = cam[:, 2]
        ok = z > 1e-6
        if not ok.any():
            return np.zeros(0, int)
        u = self.K[0, 0] * cam[:, 0] / np.where(ok, z, 1.0) + self.K[0, 2]
        v = self.K[1, 1] * cam[:, 1] / np.where(ok, z, 1.0) + self.K[1, 2]
        ok &= (u >= 0) & (u < w) & (v >= 0) & (v < h)
        return np.flatnonzero(ok)

    def max_ray_separation_deg(self, point, cam_idx=None) -> float:
        """Largest angle between any two view rays to ``point``, in degrees.

        This is the quantity that makes depth observable. View count does not:
        fifty cameras strung along one line give one direction, and a point
        seen only that way has a depth the capture never constrained.
        """
        p = np.asarray(point, float).reshape(3)
        idx = self.visible_cameras(p) if cam_idx is None else np.asarray(cam_idx)
        if len(idx) < 2:
            return 0.0
        d = p[None, :] - self.centres[idx]
        n = np.linalg.norm(d, axis=1, keepdims=True)
        d = d / np.where(n > 1e-9, n, 1.0)
        cos = np.clip(d @ d.T, -1.0, 1.0)
        return float(np.degrees(np.arccos(cos.min())))

    def within_coverage(self, point) -> bool:
        """True when the point sits in space the capture actually established.

        With no coverage grid this returns ``True``: the grid is the only thing
        that can refuse here, and inventing a refusal without it would be as
        unfounded as inventing an acceptance.  The absence is reported
        separately in :meth:`for_points`.
        """
        if self.coverage is None:
            return True
        return bool(self.coverage.is_measurable(point))

    def for_points(self, points, *, provenances=None,
                   endpoints_observed: bool | None = None) -> Evidence:
        """Assemble the evidence record for a whole measurement.

        Support is aggregated across endpoints with the *worst* endpoint
        winning, because a measurement is no better supported than its weakest
        end: a width whose near edge is seen from twenty angles and whose far
        edge is seen from one is a one-view measurement.
        """
        pts = np.atleast_2d(np.asarray(points, float))
        per_point_views, per_point_sep = [], []
        within = True
        # Lineage is used only if *every* endpoint has it. A measurement whose
        # far end fell back to frustum geometry is a frustum-derived measurement
        # however well supported its near end is, and averaging the two bases
        # would hide that behind a figure belonging to neither.
        basis = "triangulated_observations" if self.has_lineage else \
            "frustum_upper_bound"
        for p in pts:
            obs = self.observations_of(p) if self.has_lineage else None
            if obs is not None and len(obs["frame_index"]) > 0:
                per_point_views.append(int(len(np.unique(obs["frame_index"]))))
                per_point_sep.append(self.measured_ray_separation_deg(p))
            else:
                if self.has_lineage:
                    basis = "frustum_upper_bound"
                idx = self.visible_cameras(p)
                per_point_views.append(len(idx))
                per_point_sep.append(self.max_ray_separation_deg(p, idx))
            within &= self.within_coverage(p)

        observed = endpoints_observed
        if observed is None and provenances is not None:
            observed = all(int(pr) in (int(Provenance.OBSERVED_HIGH_CONFIDENCE),
                                       int(Provenance.OBSERVED_LOW_CONFIDENCE))
                           for pr in provenances)
        inferred = bool(provenances is not None and any(
            int(pr) in (int(Provenance.AI_ASSISTED),
                        int(Provenance.AI_GEOMETRICALLY_VERIFIED))
            for pr in provenances))

        return Evidence(
            n_supporting_views=int(min(per_point_views)) if per_point_views else 0,
            max_ray_separation_deg=(float(min(per_point_sep))
                                    if per_point_sep else 0.0),
            view_support_basis=basis,
            touches_inferred=inferred,
            endpoints_observed=bool(observed) if observed is not None else False,
            endpoints_within_coverage=bool(within),
            dynamic_contamination=False,
            scale_source=self.scale_source,
            scale_sigma_rel=self.scale_sigma_rel,
        )

    def supporting_frames(self, point, *, limit: int = 12) -> list:
        """Frames for ``point``, most diverse in viewing direction first.

        When lineage exists these are the frames that actually measured the
        point, each with the pixel it was measured at -- the source pixels an
        evidence panel displays. Otherwise they are candidate frames from
        camera geometry, and ``measured`` on every row says which it is.
        """
        p = np.asarray(point, float).reshape(3)
        obs = self.observations_of(p) if self.has_lineage else None
        measured_uv = {}
        if obs is not None and len(obs["frame_index"]) > 0:
            rows = []
            for fi, uv in zip(obs["frame_index"], obs["uv"]):
                r = self._camera_of_frame.get(int(fi))
                if r is None:
                    continue
                rows.append(r)
                measured_uv[r] = (float(uv[0]), float(uv[1]))
            idx = np.asarray(sorted(set(rows)), int)
        else:
            idx = self.visible_cameras(p)
        if len(idx) == 0:
            return []
        d = p[None, :] - self.centres[idx]
        n = np.linalg.norm(d, axis=1, keepdims=True)
        u = d / np.where(n > 1e-9, n, 1.0)
        # Rank by how much a frame adds to the spread already available, so a
        # run of near-identical neighbours does not fill the list.
        chosen = [0]                       # seed with the first visible frame
        while len(chosen) < min(limit, len(idx)):
            best, best_gain = None, -1.0
            for j in range(len(idx)):
                if j in chosen:
                    continue
                gain = min(float(np.degrees(np.arccos(
                    np.clip(u[j] @ u[c], -1.0, 1.0)))) for c in chosen)
                if gain > best_gain:
                    best, best_gain = j, gain
            if best is None:
                break
            chosen.append(best)
        return [{"camera_index": int(idx[j]),
                 "frame_index": self.frame_indices[int(idx[j])],
                 "measured": int(idx[j]) in measured_uv,
                 "pixel": measured_uv.get(int(idx[j])),
                 "distance_m": float(n[j, 0]),
                 "min_separation_from_selected_deg": float(np.degrees(np.arccos(
                     np.clip(min(u[j] @ u[c] for c in chosen if c != j),
                             -1.0, 1.0)))) if len(chosen) > 1 else 0.0}
                for j in chosen]
