"""Drishti3D evaluation harness.

Runs the *verified* reconstruction pipeline on real (or synthetic) datasets that
carry ground truth, then scores the result against that ground truth with honest,
convention-safe metrics:

  * trajectory ATE  -- estimated camera centres vs GT centres, after a Sim(3)
    alignment (the standard SLAM protocol; absorbs frame/scale gauge freedom);
  * scale error     -- how far the recovered metric scale is from 1.0;
  * cloud accuracy / completeness -- nearest-neighbour distances between the
    reconstructed point cloud and a GT cloud, both directions.

The harness never feeds ground-truth *poses* into the pipeline.  For datasets
without real GPS it synthesises drone-grade noisy GPS from the GT track, so the
pose/scale numbers reflect the same conditions a real single-pass drone flight
would impose -- which is exactly the accuracy claim Drishti3D has to defend.
"""

from .cases import EvalCase, load_case, detect_dataset  # noqa: F401
from .harness import run_case  # noqa: F401
from .metrics import score_case, CaseScore  # noqa: F401

__all__ = [
    "EvalCase", "load_case", "detect_dataset", "run_case",
    "score_case", "CaseScore",
]
