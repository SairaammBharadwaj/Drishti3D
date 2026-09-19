"""What supports a measurement, assembled from the stored artifacts.

This is the evidence side of plan features F3 and F5.  Given a reconstruction's
artifacts and a point in ENU metres, it answers: which cameras could see this,
how much parallax do they provide, is it on established surface, and where did
the metric scale come from.

The honest limit, stated here because it governs every verdict downstream
------------------------------------------------------------------------
The point cloud does not carry observation lineage.  ``cloud.npz`` stores
positions, colours, confidence and provenance, but not "this point came from
image observations in frames 12, 19 and 27 at these pixels".  Fusion's voxel
downsample and outlier removal reindex the cloud, and nothing carries track
identity across that.

So view support here is computed from camera *geometry*: a camera counts if the
point falls in front of it and inside its image, and if the coverage grid says
the sight line is not blocked.  That is a real test and it is useful, but it
counts cameras that may never have contributed an observation, so the parallax
it reports is an **upper bound**.  Every :class:`~.questions.Evidence` produced
here is therefore stamped ``view_support_basis="frustum_upper_bound"``, which
:func:`~.questions.evaluate` treats as blocking acceptance.  Persisting track
identity through fusion (work package WP1) is what lifts that block; until it
lands, no measurement can be accepted on view support, which is the correct
behaviour rather than a temporary inconvenience.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from .questions import Evidence
from .provenance import Provenance


@dataclass
class ReconstructionEvidence:
    """Camera geometry and coverage for one reconstruction, loaded once."""

    centres: np.ndarray               # (M,3) ENU camera centres
    rotations: np.ndarray | None      # (M,3,3) world->camera in ENU, or None
    frame_indices: list
    K: np.ndarray | None
    image_size: tuple | None
    coverage: object | None = None    # CoverageGrid
    scale_source: str = "none"
    scale_sigma_rel: float = float("nan")

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
        return cls(centres, rotations, [c.get("frame_index") for c in cams],
                   K, size, cov, scale_source, scale_sigma)

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
        for p in pts:
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
            view_support_basis="frustum_upper_bound",
            touches_inferred=inferred,
            endpoints_observed=bool(observed) if observed is not None else False,
            endpoints_within_coverage=bool(within),
            dynamic_contamination=False,
            scale_source=self.scale_source,
            scale_sigma_rel=self.scale_sigma_rel,
        )

    def supporting_frames(self, point, *, limit: int = 12) -> list:
        """Frames that could show ``point``, best parallax first.

        This is what an evidence panel lists and what a refinement scheduler
        ranks. It is candidate imagery, not proof that the point was
        triangulated from these frames -- see the module docstring.
        """
        p = np.asarray(point, float).reshape(3)
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
                 "distance_m": float(n[j, 0]),
                 "min_separation_from_selected_deg": float(np.degrees(np.arccos(
                     np.clip(min(u[j] @ u[c] for c in chosen if c != j),
                             -1.0, 1.0)))) if len(chosen) > 1 else 0.0}
                for j in chosen]
