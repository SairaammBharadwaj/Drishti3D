"""AI reconstruction adapter interface + honest stubs.

Learned models (MASt3R-SLAM, VGGT) are OPTIONAL.  The default pipeline runs
fully without them.  An adapter must never report that a model ran when it did
not; ``is_available()`` reflects real installation.  AI output starts as
``AI_ASSISTED`` provenance and may only be promoted after geometric
verification against the classical reconstruction.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
import importlib.util
import numpy as np


@dataclass
class AIResult:
    points: np.ndarray                 # (N,3)
    colors: np.ndarray | None = None
    uncertainty: np.ndarray | None = None
    camera_poses: list = field(default_factory=list)
    provenance: str = "AI_ASSISTED"


class AIReconstructor(ABC):
    name = "abstract"
    setup_instructions = ""

    @abstractmethod
    def is_available(self) -> bool: ...

    @abstractmethod
    def prepare_inputs(self, frames): ...

    @abstractmethod
    def reconstruct(self, prepared): ...

    def get_camera_poses(self, result: AIResult):
        return result.camera_poses

    def get_depth_maps(self, result: AIResult):
        return None

    def get_point_cloud(self, result: AIResult):
        return result.points

    def get_uncertainty(self, result: AIResult):
        return result.uncertainty


def _installed(module: str) -> bool:
    try:
        return importlib.util.find_spec(module) is not None
    except (ImportError, ValueError):
        return False


class MASt3RSLAMAdapter(AIReconstructor):
    name = "mast3r_slam"
    setup_instructions = (
        "Install MASt3R-SLAM from https://github.com/rmurai0610/MASt3R-SLAM "
        "and its checkpoints. Note CC BY-NC-SA licensing. Set "
        "DRISHTI_MAST3R_PATH to the repo. Requires an NVIDIA GPU for usable speed."
    )

    def is_available(self) -> bool:
        import os
        return _installed("mast3r_slam") or bool(os.environ.get("DRISHTI_MAST3R_PATH"))

    def prepare_inputs(self, frames):
        return frames

    def reconstruct(self, prepared):
        if not self.is_available():
            raise RuntimeError("MASt3R-SLAM not installed. " + self.setup_instructions)
        raise NotImplementedError(
            "MASt3R-SLAM integration is stubbed. Provide the repo and enable it "
            "explicitly; the classical path is used by default.")


class VGGTAdapter(AIReconstructor):
    name = "vggt"
    setup_instructions = (
        "Install VGGT from https://github.com/facebookresearch/vggt and its "
        "weights. Set DRISHTI_VGGT_PATH. A GPU is strongly recommended."
    )

    def is_available(self) -> bool:
        import os
        return _installed("vggt") or bool(os.environ.get("DRISHTI_VGGT_PATH"))

    def prepare_inputs(self, frames):
        return frames

    def reconstruct(self, prepared):
        if not self.is_available():
            raise RuntimeError("VGGT not installed. " + self.setup_instructions)
        raise NotImplementedError(
            "VGGT integration is stubbed. Provide the repo and enable it "
            "explicitly; the classical path is used by default.")


ADAPTERS = {"mast3r_slam": MASt3RSLAMAdapter, "vggt": VGGTAdapter}


def status() -> list[dict]:
    """Report availability of each optional AI backend (no fabrication)."""
    out = []
    for key, cls in ADAPTERS.items():
        a = cls()
        out.append({"name": key, "available": a.is_available(),
                    "setup": a.setup_instructions})
    return out
