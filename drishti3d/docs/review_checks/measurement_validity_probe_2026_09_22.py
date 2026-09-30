"""Small counterexamples for the September 22 measurement-evaluation review.

These diagnose inference limits, not an error measured on a real mission.
No saved mission or production database is written. Run from the repository:
  drishti3d/.venv/bin/python drishti3d/docs/review_checks/measurement_validity_probe_2026_09_22.py
"""
import json
from pathlib import Path
import sys

import numpy as np
from scipy.spatial import cKDTree

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'reconstruction'))
from drishti_recon.geo import _trajectory_conditioning, umeyama_sim3


def skew(v):
    x, y, z = v
    return np.array([[0, -z, y], [z, 0, -x], [-y, x, 0]])


def main():
    # A dense flat reference has returns at the WRONG reconstructed endpoint.
    # Nearest-surface matching therefore erases this known 5% length error.
    axis = np.arange(-20., 20.01, .05)
    xx, yy = np.meshgrid(axis, axis)
    ref = np.column_stack([xx.ravel(), yy.ravel(), np.zeros(xx.size)])
    truth_endpoints = np.array([[0., 0, 0], [10., 0, 0]])
    reconstructed = truth_endpoints * 1.05
    distances, idx = cKDTree(ref).query(reconstructed)
    predicted_length = np.linalg.norm(reconstructed[1] - reconstructed[0])
    nn_length = np.linalg.norm(ref[idx[1]] - ref[idx[0]])
    true_length = np.linalg.norm(truth_endpoints[1] - truth_endpoints[0])
    assert abs(predicted_length - nn_length) < 1e-8
    assert abs(predicted_length - true_length - .5) < 1e-8

    # Noncollinear planar correspondences still constrain a proper 7-DOF Sim(3).
    # This does NOT say image-derived depth or camera calibration is sound.
    planar = np.array([[-10., -10, 0], [10., -10, 0], [10., 10, 0], [-10., 10, 0]])
    theta = .3
    rotation = np.array([[1., 0, 0], [0, np.cos(theta), -np.sin(theta)], [0, np.sin(theta), np.cos(theta)]])
    target = 1.2 * (rotation @ planar.T).T + [3., -4., 7.]
    recovered = umeyama_sim3(planar, target)
    jacobian = np.vstack([np.column_stack([np.eye(3), -skew(p), p[:, None]]) for p in planar])
    rank = int(np.linalg.matrix_rank(jacobian))
    flagged, reason, _ = _trajectory_conditioning(planar)
    fit_error = float(np.max(np.linalg.norm(recovered.apply(planar) - target, axis=1)))
    assert rank == 7 and fit_error < 1e-10 and flagged

    # A low median error/sigma ratio does not establish interval coverage.
    errors = np.r_[np.zeros(60), np.ones(40)]
    sigma = np.full(100, .1)
    coverage = float(np.mean(errors <= 1.96 * sigma))
    assert coverage == .6
    out = {
        'nearest_neighbor_dimension_counterexample': {
            'true_identified_length_m': float(true_length),
            'reconstructed_length_m': float(predicted_length),
            'nearest_reference_pair_length_m': float(nn_length),
            'nearest_reference_score_m': float(abs(predicted_length - nn_length)),
            'actual_identified_length_error_m': float(abs(predicted_length - true_length)),
            'maximum_nearest_reference_distance_m': float(distances.max()),
        },
        'planar_similarity_counterexample': {
            'similarity_jacobian_rank': rank,
            'fit_max_error_m': fit_error,
            'production_planarity_flag': bool(flagged),
            'production_reason': reason,
        },
        'median_ratio_is_not_coverage': {
            'median_absolute_error_over_median_sigma': float(np.median(errors) / np.median(sigma)),
            'fraction_inside_1_96_sigma': coverage,
        },
    }
    print(json.dumps(out, indent=2))


if __name__ == '__main__':
    main()
