"""Same-pass evidence recovery: spend compute on one measurement, not the scene.

Plan feature F4 and section 5.7.  A uniform reconstruction budget treats every
frame of a pass the same, so the frames that would have constrained *this*
particular width are indistinguishable from the ones that constrain a roof
40 m away.  Keyframe selection then discards most of them -- 104 of 184 decoded
frames on the AGZ development mission.  Those frames still exist, they were
flown, and the evidence in them was never processed.

What this module does
---------------------
Given a measurement and the artifacts of the reconstruction that produced it:

1. Index every decoded frame of the pass and mark which ones the reconstruction
   actually used (:meth:`RefinementEngine.candidates`).
2. Give each unused frame a *tentative* pose by interpolating between the
   registered cameras that bracket it in time, and back-project the
   measurement's endpoints into it.  Tentative visibility is kept distinct from
   verified support throughout: an interpolated pose is a guess about where a
   camera was, and nothing is counted as evidence on its strength.
3. Reject candidates that cannot help, each with a reason: unusable image
   quality, no bracketing cameras to interpolate from, the endpoint not in
   frame, or a viewing direction that adds no parallax.
4. Rank the survivors by the parallax they would add at the endpoint, which is
   what makes depth observable, discounted by range because a more distant view
   resolves less.
5. Process a bounded batch: decode, undistort to the geometry the solver used,
   match against registered anchor frames, recover a real pose by PnP against
   the existing model, locate the endpoint in the new image, and re-triangulate
   it from the enlarged ray set.
6. Recompute the measurement, its uncertainty and its verdict, and report the
   before and after side by side.

What it cannot do
-----------------
It cannot create parallax the flight never flew.  If every frame of the pass
looks along one direction, every candidate looks along that direction too, and
the honest outcome is that no candidate clears the parallax-gain floor and the
measurement is returned unchanged with ``no_candidate_adds_parallax``.  That is
a result, not a failure to report.

Nor does it re-solve the global model.  New cameras are registered by PnP
against existing points, so they inherit the global frame and its error rather
than correcting it.  The plan's warning about this (section 5.7 step 5) is
handled by :data:`POSE_UNCERTAINTY_INFLATION`: a recovered camera's rays carry a
larger effective pixel uncertainty than an originally-solved one, so adding
views narrows the interval by less than the geometry alone would suggest.
Treating a PnP pose as exact would make the interval artificially certain,
which is the one outcome worse than not refining at all.
"""
from __future__ import annotations

import json
import time
from dataclasses import dataclass, field, asdict
from pathlib import Path

import numpy as np

from . import questions as qmod
from . import uncertainty as unc

#: Rays from a camera recovered by PnP against the existing model carry this
#: multiple of the baseline pixel uncertainty.  The camera's own pose error is
#: real, correlated with the model it was fitted to, and not modelled per-ray;
#: folding it into the ray as extra angular slop is a conservative stand-in.
#: 2.0 is a judgement, not a measurement -- it has not been calibrated against
#: observed error, and is deliberately on the pessimistic side.
POSE_UNCERTAINTY_INFLATION = 2.0

#: Baseline 1-sigma of a feature location, in pixels at solving resolution.
BASE_PIXEL_SIGMA = 1.0

#: A candidate must add at least this much parallax at the endpoint to be worth
#: processing.  Below it the new ray is nearly parallel to one the measurement
#: already has, so it adds redundancy rather than geometry.
MIN_PARALLAX_GAIN_DEG = 2.0

#: Viewpoint change, in degrees, beyond which a descriptor match to an existing
#: observation becomes unreliable.  This is the tension at the heart of the
#: feature: the frames that would add the most parallax are the same frames
#: whose view of the surface has changed the most, and past roughly this angle
#: SIFT no longer recognises it as the same feature.  Measured on the AGZ
#: mission, a candidate 70 deg from the nearest measuring ray produced a
#: best-to-second descriptor ratio of 0.85 -- correctly refused as ambiguous,
#: and a wasted decode.  Ranking therefore peaks here rather than at the
#: maximum available parallax.
MATCHABLE_GAIN_DEG = 25.0

#: Reprojection inlier threshold for PnP, pixels at solving resolution.
PNP_REPROJ_PX = 4.0

#: A recovered pose is rejected below this many PnP inliers.  Six is the
#: minimum for a well-posed P3P-plus-verification solve; accepting fewer means
#: accepting a pose that a handful of bad matches could have invented.
MIN_PNP_INLIERS = 12

#: How near a match in an anchor frame must land to a known observation of the
#: endpoint before it is accepted as the same feature, in pixels.
OBSERVATION_MATCH_PX = 3.0

#: Radius, in pixels, of the window searched around the endpoint's *predicted*
#: position in a newly posed frame.  The prediction comes from the recovered
#: pose and the endpoint's current estimate, so it is only a prior: what is
#: accepted is an independently detected keypoint inside the window whose
#: descriptor matches the endpoint's appearance in a frame that measured it.
#: Wide enough to absorb the recovered pose's own error (about 2 px reprojection
#: RMSE on the AGZ mission) plus the endpoint's positional uncertainty.
LOCATE_SEARCH_PX = 40.0

#: Lowe ratio for the guided descriptor match inside that window.  Tighter than
#: the front end's 0.75 because the window already removes most of the wrong
#: candidates, so a loose ratio here buys nothing and admits near-duplicates.
LOCATE_RATIO = 0.7


#: Why a candidate frame was not used. Stable, reportable codes.
REJECT_ALREADY_USED = "already_in_reconstruction"
REJECT_QUALITY = "frame_quality_rejected"
REJECT_NO_BRACKET = "no_bracketing_registered_cameras"
REJECT_NOT_IN_FRAME = "endpoint_not_in_frame"
REJECT_NO_PARALLAX_GAIN = "adds_no_parallax"
REJECT_PNP_FAILED = "pose_recovery_failed"
REJECT_NOT_LOCATED = "endpoint_not_located_in_image"

REJECT_GUIDANCE = {
    REJECT_ALREADY_USED: "This frame already contributed to the reconstruction.",
    REJECT_QUALITY: "Blur or exposure put this frame below the quality floor "
                    "the reconstruction applied.",
    REJECT_NO_BRACKET: "No registered cameras surround this frame in time, so "
                       "its pose cannot even be guessed at.",
    REJECT_NOT_IN_FRAME: "The endpoint does not fall inside this frame.",
    REJECT_NO_PARALLAX_GAIN: "This view is nearly parallel to one the "
                             "measurement already has.",
    REJECT_PNP_FAILED: "Too few verified 2D-3D correspondences to place this "
                       "camera in the existing model.",
    REJECT_NOT_LOCATED: "The endpoint could not be matched into this image.",
}


@dataclass
class Candidate:
    """One unused frame of the pass, and what it would contribute."""

    frame_index: int
    timestamp: float
    blur: float = float("nan")
    accepted_by_quality: bool = False
    #: Interpolated between bracketing registered cameras. A guess, used only to
    #: decide whether the frame is worth decoding -- never counted as evidence.
    tentative_pose: bool = False
    projects_in: bool = False
    #: Parallax this frame would add at the endpoint, degrees, under the
    #: tentative pose. The ranking signal.
    parallax_gain_deg: float = 0.0
    range_m: float = float("nan")
    score: float = 0.0
    rejected: str | None = None

    def to_dict(self) -> dict:
        d = asdict(self)
        for k in ("blur", "parallax_gain_deg", "range_m", "score", "timestamp"):
            v = d.get(k)
            if v is not None and not np.isfinite(v):
                d[k] = None
        if self.rejected:
            d["rejection_explanation"] = REJECT_GUIDANCE.get(self.rejected, "")
        return d


@dataclass
class AddedFrame:
    """A frame that was actually processed and entered the measurement."""

    frame_index: int
    pnp_inliers: int
    pnp_reproj_rmse_px: float
    endpoint_index: int
    pixel: tuple
    parallax_gain_deg: float

    def to_dict(self) -> dict:
        return {**asdict(self), "pixel": list(self.pixel)}


@dataclass
class RefinementRun:
    """The record plan section 5.9 asks a refinement to leave behind."""

    question_kind: str
    tolerance_m: float | None
    budget_frames: int
    before: dict = field(default_factory=dict)
    after: dict = field(default_factory=dict)
    added_frames: list = field(default_factory=list)
    rejected: list = field(default_factory=list)
    considered: int = 0
    #: The endpoint positions after refinement, in ENU. Identical to the input
    #: when nothing was recovered. Needed by anything that wants to re-measure,
    #: display or export the refined geometry rather than only its verdict.
    refined_points_enu: list = field(default_factory=list)
    termination_reason: str = ""
    wall_seconds: float = 0.0
    notes: list = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "question_kind": self.question_kind,
            "tolerance_m": self.tolerance_m,
            "budget_frames": self.budget_frames,
            "before": self.before,
            "after": self.after,
            "added_frames": [a.to_dict() for a in self.added_frames],
            "rejected": self.rejected,
            "n_considered": self.considered,
            "refined_points_enu": [list(map(float, p))
                                   for p in self.refined_points_enu],
            "n_added": len(self.added_frames),
            "termination_reason": self.termination_reason,
            "wall_seconds": round(self.wall_seconds, 2),
            "notes": self.notes,
            "improved": self.improved,
            "status_regressed": self.status_regressed,
            "interval_narrowed": self.interval_narrowed,
            "reasons_cleared": self.reasons_cleared,
            "reasons_added": self.reasons_added,
            "value_change_m": (None if self.value_change_m is None
                               else round(self.value_change_m, 4)),
        }

    @property
    def interval_narrowed(self) -> bool:
        b, a = self.before.get("sigma"), self.after.get("sigma")
        return (b is not None and a is not None and np.isfinite(b)
                and np.isfinite(a) and a < b)

    #: Verdicts ordered worst to best. A refinement that moves a measurement
    #: down this ladder has made it worse, however its reason list changed.
    _STATUS_ORDER = ["not_observable", "needs_refinement", "estimated_only",
                     "meets_requirement"]

    @property
    def reasons_cleared(self) -> list:
        """Blocking reasons present before and absent after.

        A literal set difference, and on its own it is *not* evidence of
        improvement: a verdict that degrades to ``not_observable`` returns only
        its hard-refusal reasons, so every soft reason vanishes from the list.
        Measured on the AGZ mission, two runs in thirty cleared reasons that way
        while making the measurement unusable. :attr:`improved` therefore checks
        :attr:`status_regressed` as well.
        """
        before = set(self.before.get("reasons") or [])
        after = set(self.after.get("reasons") or [])
        return sorted(before - after)

    @property
    def reasons_added(self) -> list:
        """Reasons the refinement introduced."""
        before = set(self.before.get("reasons") or [])
        after = set(self.after.get("reasons") or [])
        return sorted(after - before)

    @property
    def status_regressed(self) -> bool:
        """Did the verdict move down the ladder?"""
        try:
            b = self._STATUS_ORDER.index(self.before.get("status", ""))
            a = self._STATUS_ORDER.index(self.after.get("status", ""))
        except ValueError:
            return False
        return a < b

    @property
    def value_change_m(self) -> float | None:
        b, a = self.before.get("value"), self.after.get("value")
        if b is None or a is None:
            return None
        return float(a - b)

    @property
    def improved(self) -> bool:
        """Did the measurement's standing actually change for the better?

        Deliberately not "the interval got narrower". On the AGZ mission a run
        that recovered three frames moved the value by 0.10 m and the interval
        by 0.001 m, because the interval was dominated by the other endpoint
        and by the metric scale -- yet it cleared ``insufficient_views``, which
        is what had been blocking the measurement. Judging refinement on
        interval width alone would have called that a failure, and judging it
        on width alone in the other direction is how a narrower interval gets
        mistaken for a better answer.

        Equally deliberately, a run whose verdict regressed is never an
        improvement, whatever happened to its reason list or its interval. A
        refined endpoint can land outside established coverage, and the verdict
        then drops to ``not_observable`` carrying only hard-refusal reasons --
        which reads as a clean sweep of the soft ones unless the status is
        checked too.
        """
        if self.status_regressed:
            return False
        return bool(self.reasons_cleared) or self.interval_narrowed


def _slerp(R0: np.ndarray, R1: np.ndarray, t: float) -> np.ndarray:
    from scipy.spatial.transform import Rotation, Slerp
    key = Rotation.from_matrix(np.stack([R0, R1]))
    return Slerp([0.0, 1.0], key)([float(np.clip(t, 0.0, 1.0))]).as_matrix()[0]


def _angle_between(u: np.ndarray, v: np.ndarray) -> float:
    c = float(np.clip(np.dot(u, v), -1.0, 1.0))
    return float(np.degrees(np.arccos(c)))


class FrameSource:
    """Decodes frames of the original clip into the geometry the solver used.

    The reconstruction worked on frames that were resized to
    ``proc_max_width`` and then undistorted once, and every stored pixel and the
    stored ``K`` belong to that geometry.  A frame decoded any other way cannot
    be compared against them, so this reproduces the same two steps rather than
    approximating them.
    """

    def __init__(self, video_path, manifest: dict, K_solved: np.ndarray,
                 image_size: tuple):
        self.video_path = str(video_path)
        self.K = np.asarray(K_solved, float)
        self.width, self.height = int(image_size[0]), int(image_size[1])
        params = manifest.get("params") or {}
        self.proc_max_width = int(params.get("proc_max_width") or self.width)
        intr = params.get("intrinsics") or {}
        self.distortion = intr.get("distortion")
        self._K_orig = None
        if all(k in intr for k in ("fx", "fy", "cx", "cy")):
            self._K_orig = np.array([[intr["fx"], 0, intr["cx"]],
                                     [0, intr["fy"], intr["cy"]],
                                     [0, 0, 1.0]], float)
        self._cap = None
        self._cache: dict = {}

    def _open(self):
        import cv2
        if self._cap is None:
            self._cap = cv2.VideoCapture(self.video_path)
            if not self._cap.isOpened():
                raise RuntimeError(f"cannot open {self.video_path}")
        return self._cap

    def close(self):
        if self._cap is not None:
            self._cap.release()
            self._cap = None

    def gray(self, frame_index: int):
        """Greyscale frame at solving geometry, or ``None`` if unavailable."""
        import cv2
        if frame_index in self._cache:
            return self._cache[frame_index]
        cap = self._open()
        cap.set(cv2.CAP_PROP_POS_FRAMES, int(frame_index))
        ok, img = cap.read()
        if not ok or img is None:
            return None
        ow = img.shape[1]
        scale = 1.0
        if ow > self.proc_max_width:
            scale = self.proc_max_width / ow
            img = cv2.resize(img, (self.proc_max_width,
                                   int(round(img.shape[0] * scale))))
        if self.distortion is not None and self._K_orig is not None:
            from . import sensors as sensormod
            K_scaled = self._K_orig.copy()
            # The stored intrinsics are for the original frame size; scale them
            # to the processing size before undistorting, exactly as the
            # pipeline does. The factor is the resize ratio measured on this
            # frame -- deriving it from the principal point instead assumes the
            # optical centre is the image centre, which is off by 1% on the AGZ
            # calibration and puts every feature ~10 px from where the stored
            # observations say it should be.
            K_scaled[:2, :] *= scale
            imgs, _K_new, applied = sensormod.undistort_frames(
                [img], K_scaled, self.distortion)
            if applied:
                img = imgs[0]
        g = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        if len(self._cache) > 48:
            self._cache.clear()
        self._cache[frame_index] = g
        return g


class RefinementEngine:
    """Plans and performs same-pass evidence recovery for one reconstruction."""

    def __init__(self, evidence, artifacts_dir, video_path=None,
                 matcher: str = "sift"):
        self.ev = evidence
        self.art = Path(artifacts_dir)
        self.manifest = {}
        man = self.art / "manifest.json"
        if man.exists():
            try:
                self.manifest = json.loads(man.read_text())
            except (OSError, ValueError):
                self.manifest = {}
        self.frame_metrics = self._load_json("frame_metrics.json") or []
        self.keyframes = self._load_json("keyframes.json") or []
        self.used_frames = {int(k["frame_index"]) for k in self.keyframes
                            if "frame_index" in k}
        # Registered cameras, ordered by the decoded frame index they came from.
        order = np.argsort([f if f is not None else -1
                           for f in self.ev.frame_indices])
        self._cam_order = [int(i) for i in order
                           if self.ev.frame_indices[int(i)] is not None]
        self._cam_frames = np.array(
            [int(self.ev.frame_indices[i]) for i in self._cam_order], int)
        self.video_path = video_path
        self.matcher_name = matcher
        self._source = None
        self._backend = None

    def _load_json(self, name):
        p = self.art / name
        if not p.exists():
            return None
        try:
            return json.loads(p.read_text())
        except (OSError, ValueError):
            return None

    # ---- planning --------------------------------------------------------- #
    def _interpolated_pose(self, frame_index: int):
        """(R, C) between the registered cameras bracketing this frame in time.

        Returns ``None`` when the frame lies outside the registered span.
        Extrapolating past the ends would invent a camera trajectory, and the
        whole point of tentative visibility is that it is a cheap guess used to
        decide what to decode -- not a pose anything is measured against.
        """
        if len(self._cam_frames) < 2:
            return None
        j = int(np.searchsorted(self._cam_frames, frame_index))
        if j <= 0 or j >= len(self._cam_frames):
            return None
        f0, f1 = self._cam_frames[j - 1], self._cam_frames[j]
        if f1 == f0:
            return None
        a, b = self._cam_order[j - 1], self._cam_order[j]
        if self.ev.rotations is None:
            return None
        t = (frame_index - f0) / (f1 - f0)
        R = _slerp(self.ev.rotations[a], self.ev.rotations[b], t)
        C = (1.0 - t) * self.ev.centres[a] + t * self.ev.centres[b]
        return R, C

    def _projects(self, R, C, point) -> bool:
        cam = R @ (np.asarray(point, float) - C)
        if cam[2] <= 1e-6 or self.ev.K is None:
            return False
        u = self.ev.K[0, 0] * cam[0] / cam[2] + self.ev.K[0, 2]
        v = self.ev.K[1, 1] * cam[1] / cam[2] + self.ev.K[1, 2]
        w, h = self.ev.image_size or (0, 0)
        return bool(0 <= u < w and 0 <= v < h)

    def _existing_rays(self, point) -> np.ndarray:
        """Unit rays from the cameras that already measured this endpoint."""
        p = np.asarray(point, float).reshape(3)
        obs = self.ev.observations_of(p)
        rows = [self.ev._camera_of_frame.get(int(f))
                for f in obs["frame_index"]]
        rows = sorted({r for r in rows if r is not None})
        if not rows:
            rows = list(self.ev.visible_cameras(p))
        if not rows:
            return np.zeros((0, 3))
        d = p[None, :] - self.ev.centres[rows]
        n = np.linalg.norm(d, axis=1, keepdims=True)
        return d / np.where(n > 1e-9, n, 1.0)

    def candidates(self, point, *, include_used: bool = False) -> list:
        """Rank every frame of the pass by what it would add for this endpoint.

        Every frame is returned, rejected ones included with their reason, so a
        caller can show why a measurement cannot be improved rather than only
        that it cannot.
        """
        p = np.asarray(point, float).reshape(3)
        rays = self._existing_rays(p)
        out = []
        for m in self.frame_metrics:
            fi = int(m["frame_index"])
            c = Candidate(frame_index=fi,
                          timestamp=float(m.get("timestamp", float("nan"))),
                          blur=float(m.get("blur", float("nan"))),
                          accepted_by_quality=bool(m.get("accepted", False)))
            if fi in self.used_frames and not include_used:
                c.rejected = REJECT_ALREADY_USED
                out.append(c)
                continue
            if not c.accepted_by_quality:
                c.rejected = REJECT_QUALITY
                out.append(c)
                continue
            pose = self._interpolated_pose(fi)
            if pose is None:
                c.rejected = REJECT_NO_BRACKET
                out.append(c)
                continue
            R, C = pose
            c.tentative_pose = True
            if not self._projects(R, C, p):
                c.rejected = REJECT_NOT_IN_FRAME
                out.append(c)
                continue
            c.projects_in = True
            d = p - C
            c.range_m = float(np.linalg.norm(d))
            if c.range_m < 1e-6:
                c.rejected = REJECT_NOT_IN_FRAME
                out.append(c)
                continue
            u = d / c.range_m
            c.parallax_gain_deg = (min(_angle_between(u, r) for r in rays)
                                   if len(rays) else 180.0)
            if c.parallax_gain_deg < MIN_PARALLAX_GAIN_DEG:
                c.rejected = REJECT_NO_PARALLAX_GAIN
                out.append(c)
                continue
            # Parallax is what makes depth observable, so the score rises with
            # it -- but only until the viewpoint has changed so much that the
            # surface can no longer be recognised as the same one, past which
            # the frame cannot contribute however good its geometry is. Range
            # is a mild discount, not a competing objective: a distant view
            # from the right angle still resolves depth better than a near view
            # from the wrong one.
            excess = max(0.0, c.parallax_gain_deg - MATCHABLE_GAIN_DEG)
            matchable = float(np.exp(-excess / MATCHABLE_GAIN_DEG))
            c.score = (c.parallax_gain_deg * matchable
                       / (1.0 + c.range_m / 50.0))
            out.append(c)
        out.sort(key=lambda x: (x.rejected is not None, -x.score))
        return out

    # ---- execution -------------------------------------------------------- #
    def _source_for(self):
        if self._source is None:
            if not self.video_path:
                raise RuntimeError("refinement needs the original video")
            self._source = FrameSource(self.video_path, self.manifest,
                                       self.ev.K, self.ev.image_size)
        return self._source

    def _backend_for(self):
        if self._backend is None:
            from . import features
            self._backend = features.create(self.matcher_name)
        return self._backend

    def _pnp_anchors(self, frame_index: int, limit: int = 3) -> list:
        """Registered frames nearest *in time* to a candidate, for posing it.

        Deliberately not the frames that measured the endpoint.  Those can sit
        anywhere in the pass -- on the AGZ mission the nearest ones to a given
        endpoint were 25 frames away, about 32 m of flight -- and SIFT across
        that baseline returned 74 matches out of 4000 keypoints, almost all
        wrong, so every PnP solve failed.  Posing a camera only needs frames
        that share texture with it and whose pixels have known 3D points, and
        temporal neighbours are the best available on both counts.

        Locating the endpoint is the separate job of :meth:`_endpoint_anchors`,
        which does need frames that measured it.
        """
        if self.ev.observations is None:
            return []
        seen = set(self.ev.observations["frame_index"].tolist())
        rows = [(abs(int(f) - int(frame_index)), int(f), r)
                for f, r in self.ev._camera_of_frame.items() if int(f) in seen]
        rows.sort()
        return [(f, r, None) for _d, f, r in rows[:limit]]

    def _endpoint_anchors(self, point, limit: int = 3) -> list:
        """Registered frames that measured this endpoint, nearest range first.

        Used to find where the endpoint appears in a newly posed frame: a match
        into one of these lands on a pixel whose 3D identity is known to be the
        endpoint itself, rather than merely something nearby.
        """
        obs = self.ev.observations_of(point)
        rows = []
        for f, uv in zip(obs["frame_index"], obs["uv"]):
            r = self.ev._camera_of_frame.get(int(f))
            if r is not None:
                rows.append((int(f), r, np.asarray(uv, float)))
        rows.sort(key=lambda t: np.linalg.norm(
            np.asarray(point, float) - self.ev.centres[t[1]]))
        return rows[:limit]

    def _register(self, frame_index: int, anchors: list):
        """Recover a real pose for a candidate frame by PnP against the model.

        ``anchors`` come from :meth:`_pnp_anchors`. Matches into an anchor whose
        pixel sits within :data:`OBSERVATION_MATCH_PX` of a stored observation
        inherit that observation's 3D point, which is what turns a 2D-2D match
        into the 2D-3D correspondence PnP needs.

        Returns ``(R, C, inliers, rmse, kp_new, desc_new, pt_idx, uv)`` or
        ``None``.  The last two are the model point indices and pixels of the
        PnP inliers: they are this camera's observations of existing geometry,
        and the local refit needs them to connect it to the rest of the model.
        """
        import cv2
        src = self._source_for()
        g_new = src.gray(frame_index)
        if g_new is None:
            return None
        be = self._backend_for()
        kp_new, desc_new = be.detect(g_new)
        if desc_new is None or len(kp_new) < 8:
            return None

        obs = self.ev.observations
        pts3d, pts2d, pt_ids = [], [], []
        for f, row, _uv in anchors:
            g_a = src.gray(f)
            if g_a is None:
                continue
            kp_a, desc_a = be.detect(g_a)
            if desc_a is None or len(kp_a) < 8:
                continue
            m = be.match(desc_new, desc_a, kp_new, kp_a, g_new.shape)
            if not m:
                continue
            # Anchor observations in this frame, with the 3D point each measures.
            sel = obs["frame_index"] == f
            a_uv = obs["uv"][sel]
            a_pi = obs["point_index"][sel]
            if len(a_uv) == 0:
                continue
            from scipy.spatial import cKDTree
            tree = cKDTree(a_uv)
            qi = np.array([kp_a[j] for _, j in m], float)
            d, nn = tree.query(qi)
            ok = d <= OBSERVATION_MATCH_PX
            for k in np.flatnonzero(ok):
                pts3d.append(self.ev.points[a_pi[nn[k]]])
                pts2d.append(kp_new[m[k][0]])
                pt_ids.append(int(a_pi[nn[k]]))
        if len(pts3d) < MIN_PNP_INLIERS:
            return None

        obj = np.asarray(pts3d, np.float64).reshape(-1, 1, 3)
        img = np.asarray(pts2d, np.float64).reshape(-1, 1, 2)
        ok, rvec, tvec, inl = cv2.solvePnPRansac(
            obj, img, self.ev.K, None, reprojectionError=PNP_REPROJ_PX,
            iterationsCount=500, confidence=0.999,
            flags=cv2.SOLVEPNP_SQPNP)
        if not ok or inl is None or len(inl) < MIN_PNP_INLIERS:
            return None
        rvec, tvec = cv2.solvePnPRefineLM(obj[inl.ravel()], img[inl.ravel()],
                                          self.ev.K, None, rvec, tvec)
        proj, _ = cv2.projectPoints(obj[inl.ravel()], rvec, tvec, self.ev.K, None)
        rmse = float(np.sqrt(np.mean(np.sum(
            (proj.reshape(-1, 2) - img[inl.ravel()].reshape(-1, 2)) ** 2, 1))))
        R = cv2.Rodrigues(rvec)[0]
        C = (-R.T @ tvec).ravel()
        keep = inl.ravel()
        return (R, C, int(len(inl)), rmse, kp_new, desc_new,
                np.asarray(pt_ids, int)[keep],
                np.asarray(pts2d, float)[keep])

    def _endpoint_descriptors(self, anchors):
        """Every descriptor the endpoint's keypoint carries, across anchors.

        Plural on purpose.  SIFT emits a separate keypoint for each dominant
        gradient orientation at a location, so one pixel commonly carries two or
        three descriptors that are mutually unrelated.  Taking the nearest
        keypoint and its single descriptor picks one arbitrarily: measured on
        the AGZ mission, the same physical point's two observations compared at
        599 when the orientations were mismatched, worse than the 5th percentile
        of random descriptors -- while the correct pairing compared at 122.9 and
        was rank 0 among all 4000 in the frame.  Every match then failed the
        ratio test and no frame was ever recovered.

        So all descriptors within :data:`OBSERVATION_MATCH_PX` are returned and
        a match against any of them counts.
        """
        src = self._source_for()
        be = self._backend_for()
        out, frames = [], []
        for f, _row, uv in anchors:
            g_a = src.gray(f)
            if g_a is None:
                continue
            kp_a, desc_a = be.detect(g_a)
            if desc_a is None or len(kp_a) == 0:
                continue
            d = np.linalg.norm(np.asarray(kp_a, float) - np.asarray(uv, float),
                               axis=1)
            for k in np.flatnonzero(d <= OBSERVATION_MATCH_PX):
                out.append(desc_a[int(k)])
                frames.append(int(f))
        if not out:
            return None, []
        return np.asarray(out, np.float32), frames

    def _locate(self, point, R, C, anchors, kp_new, desc_new):
        """Find the endpoint in a newly posed frame, by guided descriptor match.

        The recovered pose and the endpoint's current estimate predict where it
        should appear.  That prediction is used **only** to bound the search:
        accepting the predicted pixel itself would be circular -- the new ray
        would pass exactly through the estimate it came from, adding no
        information while narrowing the interval, which is worse than not
        refining at all.

        What is accepted is a keypoint the detector found independently inside
        the window, whose descriptor matches the endpoint's appearance in a
        frame that actually measured it.  That is a new observation.
        """
        if self.ev.K is None or not len(kp_new):
            return None
        desc_ref, _src_frames = self._endpoint_descriptors(anchors)
        if desc_ref is None:
            return None
        cam = np.asarray(R, float) @ (np.asarray(point, float)
                                      - np.asarray(C, float))
        if cam[2] <= 1e-6:
            return None
        pred = np.array([self.ev.K[0, 0] * cam[0] / cam[2] + self.ev.K[0, 2],
                         self.ev.K[1, 1] * cam[1] / cam[2] + self.ev.K[1, 2]])
        kp = np.asarray(kp_new, float)
        near = np.flatnonzero(
            np.linalg.norm(kp - pred, axis=1) <= LOCATE_SEARCH_PX)
        if len(near) < 2:
            return None
        # Distance from each windowed keypoint to its best-matching reference
        # orientation. The ratio test then compares the best windowed keypoint
        # against the second best, which is what rejects a location where two
        # different features fit the reference equally well.
        cand = desc_new[near].astype(np.float32)
        d = np.min(np.linalg.norm(cand[:, None, :] - desc_ref[None, :, :],
                                  axis=2), axis=1)
        order = np.argsort(d)
        if d[order[0]] >= LOCATE_RATIO * d[order[1]]:
            return None            # ambiguous: two candidates fit equally well
        return kp[near[order[0]]]

    #: Cap on the points entering a local refit. Large enough that the
    #: endpoint's neighbourhood is genuinely connected to the boundary, small
    #: enough that the solve stays inside an interactive budget.
    MAX_REFIT_POINTS = 400

    #: A refit whose boundary cameras have to move further than this to be
    #: re-anchored has not stayed local, and its geometry is not comparable with
    #: the model it came from.
    MAX_BOUNDARY_DRIFT_M = 1.0

    #: How far a refit may move the endpoint before it stops being a refinement
    #: of that endpoint and becomes a relocation to somewhere else.
    MAX_ENDPOINT_MOVE_M = 2.0

    def _local_bundle(self, endpoint, recovered) -> dict | None:
        """Refit the endpoint's connected neighbourhood (plan section 5.7 step 4).

        The subproblem is the recovered cameras, the registered cameras that
        share observations with them, and the points those cameras see -- then
        bundle adjustment over all of it.

        **Gauge.** ``bundle.bundle_adjust`` has no fixed-camera mask, so a
        subproblem solved in isolation is free to drift in all seven similarity
        degrees of freedom and would come back in a frame of its own. Rather
        than restructure a well-tested solver, the refit is re-anchored
        afterwards by a Sim(3) fit of its boundary camera centres onto their
        stored ones, and rejected if they had to move further than
        :data:`MAX_BOUNDARY_DRIFT_M` -- which means the solve did not stay local
        and its geometry cannot be compared with the model it came from.

        **Uncertainty at the boundary** (plan section 5.7 step 5). The refit
        solves the endpoint *relative to a neighbourhood whose own position in
        the global model is uncertain*, and holding that neighbourhood fixed is
        what would make the interval artificially certain. Measured here: the
        refit alone reported 0.006 m on a point the surrounding cloud knows to
        about 0.036 m, an order of magnitude better than the model it sits in.

        So the returned sigma is the refit's own
        :func:`uncertainty.point_covariances` value -- with ``sigma_px`` from
        the refit's residuals, the same estimator the reconstruction used --
        combined in quadrature with the neighbourhood's existing uncertainty,
        taken as the median ``sigma_major`` of the refit's points in the stored
        cloud. Refinement can improve where the endpoint sits within its
        neighbourhood; it cannot improve where the neighbourhood sits.

        Returns a dict with the refined point, its sigma and diagnostics, or
        ``None`` when a refit is not possible or was rejected.
        """
        import cv2
        from . import bundle as _bundle
        from . import uncertainty as _unc
        from .geo import umeyama_sim3

        if (not recovered or self.ev.observations is None
                or self.ev.points is None or self.ev.rotations is None):
            return None
        ep = self.ev.lineage_point(endpoint)
        if ep < 0:
            return None

        obs = self.ev.observations
        # 1) Points: what the recovered cameras saw, plus the endpoint itself,
        #    nearest to the endpoint first so the cap keeps the neighbourhood
        #    rather than an arbitrary slice of the scene.
        cand = {int(ep)}
        for r in recovered:
            cand.update(int(x) for x in r["pt_idx"])
        cand = np.array(sorted(cand), int)
        if len(cand) > self.MAX_REFIT_POINTS:
            d = np.linalg.norm(self.ev.points[cand]
                               - np.asarray(endpoint, float), axis=1)
            cand = cand[np.argsort(d)[:self.MAX_REFIT_POINTS]]
            if ep not in set(cand.tolist()):
                cand = np.append(cand, ep)
        pt_row = {int(p): i for i, p in enumerate(cand)}

        # 2) Observations from the existing model, over those points only.
        keep = np.isin(obs["point_index"], cand)
        if keep.sum() < 20:
            return None
        frames = sorted({int(f) for f in obs["frame_index"][keep]})
        boundary = [f for f in frames if f in self.ev._camera_of_frame]
        if len(boundary) < 3:
            return None

        cam_row = {int(f): i for i, f in enumerate(boundary)}
        rvecs, tvecs = [], []
        for f in boundary:
            row = self.ev._camera_of_frame[int(f)]
            R = np.asarray(self.ev.rotations[row], float)
            rvecs.append(cv2.Rodrigues(R)[0].ravel())
            tvecs.append(-R @ np.asarray(self.ev.centres[row], float))
        n_boundary = len(boundary)

        cam_idx = [cam_row[int(f)] for f in obs["frame_index"][keep]]
        pt_idx = [pt_row[int(p)] for p in obs["point_index"][keep]]
        uv = [np.asarray(x, float) for x in obs["uv"][keep]]

        # 3) The recovered cameras, free, with their PnP inliers and their
        #    measurement of the endpoint.
        for r in recovered:
            row = len(rvecs)
            rvecs.append(cv2.Rodrigues(np.asarray(r["R"], float))[0].ravel())
            tvecs.append(-np.asarray(r["R"], float) @ np.asarray(r["C"], float))
            for pi, xy in zip(r["pt_idx"], r["uv"]):
                if int(pi) in pt_row:
                    cam_idx.append(row)
                    pt_idx.append(pt_row[int(pi)])
                    uv.append(np.asarray(xy, float))
            cam_idx.append(row)
            pt_idx.append(pt_row[int(ep)])
            uv.append(np.asarray(r["endpoint_uv"], float))

        try:
            ba = _bundle.bundle_adjust(
                np.asarray(rvecs, float), np.asarray(tvecs, float),
                self.ev.points[cand].copy(), np.asarray(cam_idx, int),
                np.asarray(pt_idx, int), np.asarray(uv, float), self.ev.K,
                max_nfev=300)
        except Exception:                      # noqa: BLE001 - never fatal
            return None
        if not np.isfinite(ba.rmse_after) or ba.rmse_after > ba.rmse_before:
            return None                        # the refit did not help

        # 4) Re-anchor onto the boundary cameras' stored poses.
        centres_after = np.array(
            [(-cv2.Rodrigues(ba.rvecs[i])[0].T @ ba.tvecs[i]).ravel()
             for i in range(n_boundary)])
        centres_before = np.array(
            [self.ev.centres[self.ev._camera_of_frame[int(f)]]
             for f in boundary])
        sim = umeyama_sim3(centres_after, centres_before, with_scale=True)
        drift = float(np.median(np.linalg.norm(
            sim.apply(centres_after) - centres_before, axis=1)))
        if not np.isfinite(drift) or drift > self.MAX_BOUNDARY_DRIFT_M:
            return None
        points_anchored = sim.apply(ba.points)

        # 5) Uncertainty over the refit, with sigma_px from its own residuals.
        res = _bundle.reprojection_errors(ba.rvecs, ba.tvecs, ba.points,
                                          np.asarray(cam_idx, int),
                                          np.asarray(pt_idx, int),
                                          np.asarray(uv, float), self.ev.K)
        res = res[np.isfinite(res)]
        sigma_px = (max(1.4826 * float(np.median(np.abs(res - np.median(res)))),
                        0.05) if len(res) >= 20 else _unc.DEFAULT_SIGMA_PX)
        pu = _unc.point_covariances(ba.points, np.asarray(cam_idx, int),
                                    np.asarray(pt_idx, int),
                                    np.asarray(uv, float), ba.rvecs, ba.tvecs,
                                    self.ev.K, sigma_px=sigma_px)
        row = pt_row[int(ep)]
        sig_local = float(pu.sigma_major[row]) * float(sim.scale)

        # The neighbourhood's own uncertainty in the global model.
        sig_nb = float("nan")
        stored = getattr(self.ev, "sigma_major", None)
        if stored is not None and len(stored) > max(cand):
            vals = np.asarray(stored, float)[cand]
            vals = vals[np.isfinite(vals)]
            if len(vals):
                sig_nb = float(np.median(vals))
        sig = (float(np.hypot(sig_local, sig_nb)) if np.isfinite(sig_nb)
               else sig_local)

        moved_m = float(np.linalg.norm(points_anchored[row]
                                       - np.asarray(endpoint, float)))
        if moved_m > self.MAX_ENDPOINT_MOVE_M:
            return None                        # a relocation, not a refinement
        return {
            "point": points_anchored[row],
            "sigma": sig if np.isfinite(sig) else None,
            "sigma_local": sig_local if np.isfinite(sig_local) else None,
            "sigma_neighbourhood": sig_nb if np.isfinite(sig_nb) else None,
            "n_cameras": len(rvecs), "n_boundary_cameras": n_boundary,
            "n_recovered_cameras": len(recovered),
            "n_points": len(cand), "n_observations": len(cam_idx),
            "rmse_before": float(ba.rmse_before),
            "rmse_after": float(ba.rmse_after),
            "converged": bool(ba.converged),
            "sigma_px": float(sigma_px),
            "boundary_drift_m": round(drift, 4),
            "anchor_scale": float(sim.scale),
        }

    def refine(self, question, points_enu, *, value_fn, budget_frames: int = 6,
               max_decode: int = 24, provenances=None) -> RefinementRun:
        """Recover evidence for one measurement and re-decide it.

        ``value_fn(points) -> (value, sigma)`` recomputes the measurement from
        (possibly moved) endpoints, so this module stays ignorant of whether it
        is refining a width, a height or an area.

        ``provenances`` are the provenance classes of the endpoints as the
        measurement layer resolved them.  Pass them.  Without them the evidence
        built here falls back to the pessimistic default whenever an endpoint
        does not snap to observation lineage, and the before/after snapshots
        then disagree with the verdict the same measurement gets everywhere
        else -- which showed up in the F4 experiment as two measurements
        "regressing" to ``not_observable`` that had not changed at all.
        """
        t0 = time.time()
        pts = [np.asarray(p, float).reshape(3) for p in points_enu]
        run = RefinementRun(question_kind=question.kind,
                            tolerance_m=question.tolerance_m,
                            budget_frames=int(budget_frames))

        v0, s0 = _call_value_fn(value_fn, pts, None)
        ev0 = self.ev.for_points(pts, provenances=provenances)
        run.before = _snapshot(question, v0, s0, ev0)
        run.refined_points_enu = [np.asarray(p, float) for p in pts]

        if self.ev.K is None or self.ev.rotations is None:
            run.termination_reason = "no camera intrinsics or poses in artifacts"
            run.wall_seconds = time.time() - t0
            run.after = dict(run.before)
            return run
        if not self.ev.has_lineage:
            run.termination_reason = "no observation lineage to extend"
            run.wall_seconds = time.time() - t0
            run.after = dict(run.before)
            return run

        # Refine the endpoint whose support is worst: a measurement is no better
        # than its weakest end, so spending the budget anywhere else cannot move
        # the verdict.
        seps = [self.ev.measured_ray_separation_deg(p) for p in pts]
        target = int(np.argmin(seps))
        run.notes.append(
            f"refining endpoint {target} of {len(pts)}: it has the least "
            f"measured parallax ({seps[target]:.1f} deg)")

        cands = self.candidates(pts[target])
        usable = [c for c in cands if c.rejected is None]
        run.considered = len(cands)
        run.rejected = _rejection_summary(cands)
        if not usable:
            run.termination_reason = "no_candidate_adds_parallax"
            run.after = dict(run.before)
            run.wall_seconds = time.time() - t0
            return run

        anchors = self._endpoint_anchors(pts[target])
        if not anchors:
            run.termination_reason = "endpoint has no registered observations"
            run.after = dict(run.before)
            run.wall_seconds = time.time() - t0
            return run

        # Rays that already measure the endpoint, with their pixel sigmas.
        rays, sigmas = [], []
        obs = self.ev.observations_of(pts[target])
        for f, uv in zip(obs["frame_index"], obs["uv"]):
            r = self.ev._camera_of_frame.get(int(f))
            if r is None:
                continue
            rays.append((self.ev.rotations[r], self.ev.centres[r],
                         np.asarray(uv, float)))
            sigmas.append(BASE_PIXEL_SIGMA)

        added_rays = 0
        recovered: list = []
        for c in usable[:max_decode]:
            if len(run.added_frames) >= budget_frames:
                run.termination_reason = "budget_exhausted"
                break
            reg = self._register(c.frame_index,
                                 self._pnp_anchors(c.frame_index))
            if reg is None:
                run.rejected.append({"frame_index": c.frame_index,
                                     "reason": REJECT_PNP_FAILED,
                                     "explanation": REJECT_GUIDANCE[REJECT_PNP_FAILED]})
                continue
            R, C, inl, rmse, kp_new, desc_new, in_pts, in_uv = reg
            uv = self._locate(pts[target], R, C, anchors, kp_new, desc_new)
            if uv is None:
                run.rejected.append({"frame_index": c.frame_index,
                                     "reason": REJECT_NOT_LOCATED,
                                     "explanation": REJECT_GUIDANCE[REJECT_NOT_LOCATED]})
                continue
            d = pts[target] - C
            gain = min(_angle_between(d / np.linalg.norm(d),
                                      (pts[target] - cc) /
                                      np.linalg.norm(pts[target] - cc))
                       for _, cc, _ in rays) if rays else 180.0
            rays.append((R, C, uv))
            # A PnP-recovered camera is not as good as a solved one, and saying
            # otherwise here is what would make the interval artificially tight.
            sigmas.append(BASE_PIXEL_SIGMA * POSE_UNCERTAINTY_INFLATION
                          * max(1.0, rmse / PNP_REPROJ_PX))
            recovered.append({"frame_index": c.frame_index, "R": R, "C": C,
                              "pt_idx": in_pts, "uv": in_uv,
                              "endpoint_uv": np.asarray(uv, float)})
            added_rays += 1
            run.added_frames.append(AddedFrame(
                frame_index=c.frame_index, pnp_inliers=inl,
                pnp_reproj_rmse_px=round(rmse, 3), endpoint_index=target,
                pixel=(float(uv[0]), float(uv[1])),
                parallax_gain_deg=round(float(gain), 2)))
        else:
            if not run.termination_reason:
                run.termination_reason = ("candidate_pool_exhausted"
                                          if len(usable) <= max_decode
                                          else "decode_limit_reached")

        if added_rays == 0:
            run.termination_reason = run.termination_reason or "no_frame_recovered"
            run.after = dict(run.before)
            run.wall_seconds = time.time() - t0
            return run

        # Refit the connected neighbourhood (plan section 5.7 step 4) rather
        # than intersecting rays at one point in isolation. The first run of the
        # F4 gate lost to a uniform budget largely because the control re-solved
        # every pose while this arm could not touch any of them, so the whole
        # 39% interval improvement the control achieved was out of reach here.
        refit = self._local_bundle(pts[target], recovered)
        if refit is not None:
            moved, sig_pt = refit["point"], refit["sigma"]
            run.notes.append(
                f"local refit: {refit['n_cameras']} cameras, "
                f"{refit['n_points']} points, {refit['n_observations']} "
                f"observations, reprojection RMSE {refit['rmse_before']:.2f} -> "
                f"{refit['rmse_after']:.2f} px")
        else:
            moved, sig_pt = _triangulate(rays, sigmas, self.ev.K, pts[target])
            run.notes.append("local refit unavailable; fell back to a "
                             "standalone ray intersection")
        if moved is not None:
            pts[target] = moved
        run.notes.append(
            f"endpoint moved {float(np.linalg.norm(moved - np.asarray(points_enu[target], float))):.3f} m"
            if moved is not None else "re-triangulation did not converge")

        # The refined endpoint's own uncertainty is handed to `value_fn` so it
        # reaches the reported interval. Before the local refit existed this was
        # deliberately withheld: a standalone ray intersection produced a sigma
        # an order of magnitude *worse* than the reconstruction's bundle-adjusted
        # one, so substituting it would have widened every interval and called
        # that refinement. A sigma that came out of a refit of the same kind is
        # comparable, and withholding it was why the targeted arm's median
        # interval did not move at all in the first F4 run.
        #
        # It is passed, not forced: a refit that made the endpoint *less*
        # certain widens the interval, and that is the honest report.
        sig_out = None
        if (refit is not None and sig_pt is not None and np.isfinite(sig_pt)):
            sig_out = [None] * len(pts)
            sig_out[target] = float(sig_pt)
        v1, s1 = _call_value_fn(value_fn, pts, sig_out)
        # The refined endpoint is a position triangulated from real image
        # measurements -- the ones this run just recovered -- so it is observed
        # geometry by construction, whether or not it still lands within
        # snapping distance of a lineage-carrying cloud point. Deciding
        # otherwise would let a successful refinement report its own result as
        # unobserved.
        # The coverage grid was built from the pre-refinement cloud, and the
        # refined endpoint has moved within it. Measured on the AGZ mission,
        # refined endpoints landed in OCCLUDED cells -- occluded by their own
        # stale position, which is still in the grid's z-buffer sitting in front
        # of the corrected one along the same ray. A grid formed before the
        # point moved cannot judge where it moved to.
        #
        # What supersedes it is direct measurement: this run located the point
        # in each recovered image and re-triangulated it from those rays, so
        # cameras demonstrably see it. The other endpoints are still checked
        # against the grid as usual.
        others = [p for i, p in enumerate(pts) if i != target]
        within = all(self.ev.within_coverage(p) for p in others)
        ev1 = self.ev.for_points(pts, provenances=provenances,
                                 endpoints_observed=True,
                                 endpoints_within_coverage=within)
        # The refined endpoint came out of real image measurements, so its
        # support is triangulated even though it may no longer sit within
        # snapping distance of a lineage-carrying cloud point. Letting it fall
        # back to the frustum basis would have a successful refinement downgrade
        # its own evidence.
        ev1.view_support_basis = "triangulated_observations"
        run.notes.append(
            "coverage for the refined endpoint comes from the frames that "
            "measured it, not from the grid, which predates the refit")
        # Support now includes the recovered views, which lineage on disk does
        # not yet know about. Reporting the stale count would understate what
        # the refinement achieved, while claiming the on-disk lineage contains
        # them would be false until the artifacts are rewritten.
        ev1.n_supporting_views = int(ev1.n_supporting_views + added_rays)
        ev1.max_ray_separation_deg = max(
            ev1.max_ray_separation_deg,
            float(max(a.parallax_gain_deg for a in run.added_frames)))
        run.refined_points_enu = [np.asarray(p, float) for p in pts]
        run.after = _snapshot(question, v1, s1, ev1)
        run.after["endpoint_sigma"] = (None if sig_pt is None
                                       or not np.isfinite(sig_pt)
                                       else float(sig_pt))
        run.after["endpoint_sigma_applied"] = sig_out is not None
        if refit is not None:
            run.after["local_refit"] = {k: v for k, v in refit.items()
                                        if k not in ("point", "sigma")}
        run.after["endpoint_moved_m"] = (
            None if moved is None
            else float(np.linalg.norm(moved - np.asarray(points_enu[target], float))))
        if not run.termination_reason:
            run.termination_reason = "budget_exhausted"
        run.wall_seconds = time.time() - t0
        return run


def _call_value_fn(fn, points, sigmas):
    """Call a value function that may or may not accept per-call sigmas.

    Refinement produces a new uncertainty for the endpoint it refined, and that
    has to reach the reported interval or the whole exercise cannot move it.
    Callers written before this existed take one argument, so both shapes work
    rather than one of them breaking.
    """
    if sigmas is None:
        return fn(points)
    try:
        return fn(points, sigmas)
    except TypeError:
        return fn(points)


def measurement_value_fn(kind: str, endpoint_sigmas, *,
                         scale_sigma_rel: float = 0.0):
    """A ``value_fn`` for :meth:`RefinementEngine.refine` that does not re-snap.

    The obvious implementation -- call :mod:`measure` on the moved endpoints --
    is wrong here, and quietly so. ``measure`` snaps every input point to the
    nearest cloud point, which is correct for an operator clicking in space and
    fatal after refinement: the refined endpoint would snap straight back to the
    unrefined point it started from, the measurement would be unchanged, and
    the run would report a successful refinement that did nothing.

    So this computes from the given positions directly, with the same
    uncertainty propagation :mod:`measure` uses.  ``endpoint_sigmas`` are the
    per-endpoint worst-axis 1-sigmas as the measurement layer resolved them.

    The returned callable also accepts an optional second argument: a
    per-endpoint list whose non-``None`` entries override the stored sigma. That
    is how a refined endpoint's new uncertainty reaches the reported interval
    instead of only being printed beside it.
    """
    sig = [float(x) for x in endpoint_sigmas]

    def fn(points, overrides=None):
        P = [np.asarray(p, float).reshape(3) for p in points]

        def cov(i):
            s = sig[i] if i < len(sig) else float("inf")
            if (overrides is not None and i < len(overrides)
                    and overrides[i] is not None):
                s = float(overrides[i])
            if not np.isfinite(s):
                return np.full((3, 3), np.nan)
            return np.eye(3) * s ** 2

        if kind == "distance" and len(P) >= 2:
            total, var = 0.0, 0.0
            for i in range(len(P) - 1):
                d, s = unc.distance_uncertainty(P[i], P[i + 1], cov(i),
                                                cov(i + 1),
                                                scale_sigma_rel=scale_sigma_rel)
                total += d
                var = (np.inf if not (np.isfinite(s) and np.isfinite(var))
                       else var + s * s)
            return float(total), (float(np.sqrt(var)) if np.isfinite(var)
                                  else float("inf"))
        if kind == "height" and len(P) >= 2:
            h, s = unc.height_uncertainty(P[0], P[1], cov(0), cov(1),
                                          scale_sigma_rel=scale_sigma_rel)
            return float(h), float(s)
        if kind == "area" and len(P) >= 3:
            A = np.asarray(P, float)
            c = A.mean(0)
            _, _, vt = np.linalg.svd(A - c)
            xy = np.stack([(A - c) @ vt[0], (A - c) @ vt[1]], 1)
            x, y = xy[:, 0], xy[:, 1]
            area = 0.5 * abs(np.dot(x, np.roll(y, -1)) - np.dot(y, np.roll(x, -1)))
            _, s = unc.area_uncertainty(A, [cov(i) for i in range(len(P))],
                                        scale_sigma_rel=scale_sigma_rel)
            return float(area), float(s)
        return None, float("inf")

    return fn


def _rejection_summary(cands) -> list:
    counts: dict = {}
    for c in cands:
        if c.rejected:
            counts[c.rejected] = counts.get(c.rejected, 0) + 1
    return [{"reason": k, "n_frames": v,
             "explanation": REJECT_GUIDANCE.get(k, "")}
            for k, v in sorted(counts.items(), key=lambda kv: -kv[1])]


def _snapshot(question, value, sigma, evidence) -> dict:
    verdict = qmod.evaluate(question, value=value, sigma=sigma,
                            evidence=evidence, profile=None)
    return {
        "value": None if value is None else float(value),
        "sigma": (None if sigma is None or not np.isfinite(sigma)
                  else float(sigma)),
        "interval_half_width": verdict.to_dict()["interval_half_width"],
        "status": verdict.status.value,
        "reasons": [r.value for r in verdict.reasons],
        "dominant_limitation": verdict.dominant_limitation,
        "n_supporting_views": evidence.n_supporting_views,
        "max_ray_separation_deg": round(
            float(evidence.max_ray_separation_deg), 2),
        "view_support_basis": evidence.view_support_basis,
    }


def _triangulate(rays, sigmas, K, seed):
    """Weighted least-squares point from (R, C, uv) rays.

    Each observation constrains the point to its ray; the normal equations are
    solved in closed form.  Weights are inverse *positional* variance in metres,
    not inverse pixel variance: a pixel error of ``s`` at focal length ``f`` and
    range ``r`` displaces the point by about ``r * s / f`` across the ray, so
    weighting by pixels alone would make a distant observation count as heavily
    as a near one and would leave the recovered covariance in units that are not
    metres.  A PnP-recovered camera's inflated pixel sigma therefore genuinely
    reduces its pull on the solution, rather than only being reported.
    """
    if len(rays) < 2:
        return None, None
    Kf = np.asarray(K, float)
    Kinv = np.linalg.inv(Kf)
    A = np.zeros((3, 3))
    b = np.zeros(3)
    dirs, centres, w = [], [], []
    for (R, C, uv), s in zip(rays, sigmas):
        ray_cam = Kinv @ np.array([uv[0], uv[1], 1.0])
        d = R.T @ ray_cam
        n = np.linalg.norm(d)
        if n < 1e-12:
            continue
        d = d / n
        # Cross-ray positional 1-sigma this observation implies, in metres.
        rng_m = float(np.linalg.norm(np.asarray(seed, float)
                                     - np.asarray(C, float)))
        focal = 0.5 * (float(Kf[0, 0]) + float(Kf[1, 1]))
        sigma_m = max(rng_m * max(float(s), 1e-6) / max(focal, 1e-9), 1e-6)
        wi = 1.0 / sigma_m ** 2
        P = np.eye(3) - np.outer(d, d)      # projector onto the ray's normal plane
        A += wi * P
        b += wi * P @ np.asarray(C, float)
        dirs.append(d)
        centres.append(np.asarray(C, float))
        w.append(wi)
    if len(dirs) < 2:
        return None, None
    try:
        X = np.linalg.solve(A, b)
    except np.linalg.LinAlgError:
        return None, None
    if not np.all(np.isfinite(X)):
        return None, None
    # Guard against a degenerate solve running away: a point that moves further
    # than the scene's own extent is a solver artefact, not a refinement.
    if np.linalg.norm(X - np.asarray(seed, float)) > 50.0:
        return None, None
    # Positional sigma from the weighted normal matrix: its inverse is the
    # covariance of the estimate in metres squared, given the per-ray
    # cross-ray sigmas above. The worst axis is reported, for the same reason
    # measurements use `sigma_major`: an anisotropic error quoted along its
    # best-constrained direction understates the risk.
    try:
        cov = np.linalg.inv(A)
        sig = float(np.sqrt(max(np.max(np.linalg.eigvalsh(cov)), 0.0)))
    except np.linalg.LinAlgError:
        sig = float("nan")
    return X, sig
