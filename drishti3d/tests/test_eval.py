"""Tests for the evaluation harness.

The fast tests exercise the scoring math with a *fabricated* estimate (no SfM),
so they are deterministic and quick. The slow test runs the whole pipeline on a
tiny synthetic scene and is opt-in via ``-m slow``.
"""
import sys
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "reconstruction"))
sys.path.insert(0, str(ROOT))

from drishti_recon import geo  # noqa: E402
from eval.cases import EvalCase  # noqa: E402
from eval.harness import Estimate  # noqa: E402
from eval.metrics import score_case  # noqa: E402


def _cube_cloud(n=500, seed=1):
    rng = np.random.default_rng(seed)
    return rng.uniform(-5, 5, size=(n, 3))


def test_perfect_estimate_scores_near_zero():
    rng = np.random.default_rng(0)
    gt_centers = rng.uniform(-10, 10, size=(12, 3))
    gt_cloud = _cube_cloud()
    case = EvalCase(name="unit", kind="synthetic", images=[None] * 12,
                    gt_centers=gt_centers, gt_cloud_pts=gt_cloud)
    # a metric-perfect estimate lives under a *rigid* gauge only (rot+shift):
    # scale must stay 1, since scale_error is meant NOT to absorb metric error.
    theta = 0.7
    R = np.array([[np.cos(theta), -np.sin(theta), 0],
                  [np.sin(theta), np.cos(theta), 0], [0, 0, 1.0]])
    t = np.array([3.0, -1.0, 4.0])
    est_centers = ((R @ gt_centers.T).T + t)
    est_cloud = ((R @ gt_cloud.T).T + t)
    est = Estimate(project_dir=Path("."), est_frames=np.arange(12),
                   est_centers_enu=est_centers, cloud_pts=est_cloud,
                   report={}, warnings=[])
    sc = score_case(case, est, cloud_thr=0.1)
    assert sc.n_matched == 12
    assert sc.ate_rmse < 1e-6
    assert abs(sc.scale_error) < 1e-6
    assert sc.cloud_acc_median < 1e-6
    assert sc.cloud_completeness == pytest.approx(1.0)


def test_known_offset_produces_expected_ate():
    rng = np.random.default_rng(2)
    gt = rng.uniform(-10, 10, size=(20, 3))
    # add a constant 0.5 m east bias the Sim(3) cannot fully absorb (per-point noise)
    noise = rng.normal(0, 0.2, size=gt.shape)
    est = Estimate(project_dir=Path("."), est_frames=np.arange(20),
                   est_centers_enu=gt + noise, cloud_pts=np.zeros((0, 3)),
                   report={}, warnings=[])
    case = EvalCase(name="noisy", kind="synthetic", images=[None] * 20,
                    gt_centers=gt)
    sc = score_case(case, est)
    assert 0.05 < sc.ate_rmse < 0.6   # ~0.2 m residual after alignment
    assert sc.cloud_acc_median is None  # no cloud provided


def test_dim_error_pulled_from_report():
    case = EvalCase(name="d", kind="synthetic", images=[None] * 4,
                    gt_centers=np.zeros((4, 3)))
    report = {"ground_truth_evaluation": {
        "dimensional_accuracy": [{"pct_error": 2.0}, {"pct_error": 3.4}]}}
    est = Estimate(project_dir=Path("."), est_frames=np.arange(4),
                   est_centers_enu=np.zeros((4, 3)), cloud_pts=np.zeros((0, 3)),
                   report=report, warnings=[])
    sc = score_case(case, est)
    assert sc.dim_error_pct == pytest.approx(2.7)   # mean of 2.0 and 3.4


@pytest.mark.slow
def test_end_to_end_synthetic(tmp_path):
    from drishti_recon import synth
    from eval.cases import load_case
    from eval.harness import run_case
    scene = tmp_path / "scene"
    synth.generate(scene, n_frames=20, fps=10)
    case = load_case(scene, kind="synthetic")
    est = run_case(case, tmp_path / "work", do_mesh=False)
    sc = score_case(case, est)
    assert sc.n_solved >= 5
    # loose sanity: a working solve keeps scale within ~15 %
    if sc.scale_error is not None:
        assert sc.scale_error < 0.15
