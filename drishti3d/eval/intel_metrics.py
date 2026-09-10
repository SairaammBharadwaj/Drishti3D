"""Intelligence Edition validation metrics 4 and 5 (doc §30–31).

Metric 4 — coverage classification accuracy: are voxels labelled
OBSERVED / UNSEEN / OCCLUDED correctly, judged against a scene whose geometry
and cameras are exactly known?

Metric 5 — measurement refusal correctness: of measurement requests that a
perfect system should accept (both endpoints on observed geometry) or refuse
(the segment depends on unobserved/occluded space), how many do we get right?

  TAR  true accept    — valid request, accepted     (want high)
  TRR  true refusal   — invalid request, refused    (want high)
  FAR  false accept   — invalid request, ACCEPTED   (the dangerous cell)
  FRR  false refusal  — valid request, refused      (annoying, not dangerous)

FALSE ACCEPT is the metric this project treats as the safety number: it means
a measurement was allowed through unsupported geometry.
"""
from __future__ import annotations

import numpy as np

from drishti_recon.coverage import Coverage


def probe_pairs_from_truth(surface_pts, unseen_pts, rng, *, n_valid=200,
                           n_invalid=200, max_span=None):
    """Build labelled measurement requests from exact scene knowledge.

    Valid requests join two points sampled on truly-observed surface. Invalid
    requests join an observed point to a point in truly-unobserved space (or
    two unobserved points), so a perfect gate must refuse them.
    """
    surface_pts = np.asarray(surface_pts, float)
    unseen_pts = np.asarray(unseen_pts, float)
    pairs, labels = [], []
    for _ in range(n_valid):
        i, j = rng.integers(0, len(surface_pts), 2)
        if max_span is not None:
            for _try in range(20):
                if np.linalg.norm(surface_pts[i] - surface_pts[j]) <= max_span:
                    break
                j = rng.integers(0, len(surface_pts))
        pairs.append((surface_pts[i], surface_pts[j])); labels.append(True)
    for k in range(n_invalid):
        a = surface_pts[rng.integers(0, len(surface_pts))]
        b = unseen_pts[rng.integers(0, len(unseen_pts))]
        if k % 2:
            a = unseen_pts[rng.integers(0, len(unseen_pts))]
        pairs.append((a, b)); labels.append(False)
    return pairs, np.array(labels)


def segment_supported(grid, a, b, *, step=None, allow=(int(Coverage.OBSERVED),)):
    """Does the coverage grid support measuring along segment a-b?

    Samples the segment at sub-voxel spacing; every sample must land in an
    allowed class. This is the same rule measure.py applies, exposed here so
    the metric exercises the deployed logic rather than a reimplementation.
    """
    a = np.asarray(a, float); b = np.asarray(b, float)
    L = np.linalg.norm(b - a)
    if step is None:
        step = grid.voxel * 0.5
    n = max(int(np.ceil(L / step)) + 1, 2)
    ts = np.linspace(0.0, 1.0, n)
    pts = a[None, :] * (1 - ts[:, None]) + b[None, :] * ts[:, None]
    st = grid.status_at(pts)
    return bool(np.all(np.isin(st, allow)))


def refusal_correctness(grid, pairs, labels):
    """Metric 5. Returns the four rates plus counts."""
    labels = np.asarray(labels, bool)
    accepted = np.array([segment_supported(grid, a, b) for a, b in pairs])
    valid, invalid = labels, ~labels
    n_v = int(valid.sum()); n_i = int(invalid.sum())
    tar = float((accepted & valid).sum() / max(n_v, 1))
    frr = float((~accepted & valid).sum() / max(n_v, 1))
    trr = float((~accepted & invalid).sum() / max(n_i, 1))
    far = float((accepted & invalid).sum() / max(n_i, 1))
    return dict(TAR=tar, TRR=trr, FAR=far, FRR=frr,
                n_valid=n_v, n_invalid=n_i)


def coverage_classification_accuracy(grid, truth_pts, truth_labels,
                                     *, collapse=True):
    """Metric 4. ``truth_labels``: Coverage values at ``truth_pts``.

    ``collapse=True`` scores in the document's 3-class space
    (OBSERVED / UNSEEN / OCCLUDED), mapping our finer classes onto it:
    WEAK->OBSERVED-side support is deliberately NOT granted — WEAK and EMPTY
    map to UNSEEN-equivalent "not measurable", DYNAMIC to OCCLUDED.
    """
    pred = grid.status_at(np.asarray(truth_pts, float))
    tru = np.asarray(truth_labels, int)

    def _collapse(x):
        x = np.asarray(x, int).copy()
        m = {int(Coverage.OBSERVED): 0, int(Coverage.UNSEEN): 1,
             int(Coverage.EMPTY): 1, int(Coverage.WEAK): 1,
             int(Coverage.OCCLUDED): 2, int(Coverage.DYNAMIC_EXCLUDED): 2}
        out = np.empty_like(x)
        for k, v in m.items():
            out[x == k] = v
        return out

    if collapse:
        pred = _collapse(pred); tru = _collapse(tru)
        names = ["OBSERVED", "UNSEEN", "OCCLUDED"]
    else:
        names = [c.name for c in Coverage]
    k = len(names)
    cm = np.zeros((k, k), int)
    for t, p in zip(tru, pred):
        cm[t, p] += 1
    acc = float(np.trace(cm) / max(cm.sum(), 1))
    per_class = {names[i]: float(cm[i, i] / max(cm[i].sum(), 1))
                 for i in range(k)}
    return dict(accuracy=acc, per_class=per_class, confusion=cm.tolist(),
                classes=names)
