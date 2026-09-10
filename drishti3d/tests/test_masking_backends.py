"""Dynamic-object masking backends.

Two defects motivated these tests, both of which corrupt reconstruction
silently because masking runs BEFORE matching:

1. ``TorchvisionSemanticMask`` reported itself available whenever torch
   imported, while building its network with ``weights=None`` -- randomly
   initialised. It returned an argmax over random logits.
2. ``MaskRCNNDynamicMask`` on nadir aerial imagery produces confident false
   positives on large static structures: a school roof detected as "train" at
   score 0.74, masking 48.7 % of the frame.
"""
import numpy as np
import pytest

from drishti_recon import masking
from drishti_recon.masking import MaskRCNNDynamicMask


class _FakeTensor:
    def __init__(self, a): self._a = np.asarray(a)
    def cpu(self): return self
    def numpy(self): return self._a


class _StubModel:
    """Stands in for Mask R-CNN so mask() logic is testable without weights."""
    def __init__(self, instances):   # [(label, score, HxW float mask)]
        self.instances = instances
    def __call__(self, xs):
        labs = np.array([i[0] for i in self.instances], np.int64)
        scs = np.array([i[1] for i in self.instances], np.float32)
        mks = np.array([i[2] for i in self.instances], np.float32)[:, None]
        return [{"labels": _FakeTensor(labs), "scores": _FakeTensor(scs),
                 "masks": _FakeTensor(mks)}]


def _stub_backend(instances, shape=(120, 160), **kw):
    b = MaskRCNNDynamicMask(dilate=0, max_side=10_000, **kw)
    b._model = _StubModel(instances)
    b._device = "cpu"

    class _T:
        @staticmethod
        def from_numpy(a):
            class W:
                def __init__(s, a): s.a = a
                def permute(s, *o): return W(np.transpose(s.a, o))
                def to(s, d): return s
            return W(a)
        @staticmethod
        def no_grad():
            import contextlib
            return contextlib.nullcontext()
    b._torch = _T
    b._load = lambda: None
    return b


def _blob(shape, frac):
    """A mask covering exactly ``frac`` of the frame."""
    h, w = shape
    m = np.zeros((h, w), np.float32)
    n = int(round(frac * h * w))
    m.flat[:n] = 1.0
    return m


class TestUntrainedSemanticRefused:
    def test_unavailable_without_weights(self, monkeypatch):
        monkeypatch.delenv("DRISHTI_SEG_WEIGHTS", raising=False)
        assert masking.TorchvisionSemanticMask().is_available() is False

    def test_unavailable_when_path_missing(self, monkeypatch):
        monkeypatch.setenv("DRISHTI_SEG_WEIGHTS", "/nonexistent/x.pth")
        assert masking.TorchvisionSemanticMask().is_available() is False

    def test_loading_untrained_raises_rather_than_masking_randomly(self, monkeypatch):
        monkeypatch.delenv("DRISHTI_SEG_WEIGHTS", raising=False)
        b = masking.TorchvisionSemanticMask()
        with pytest.raises(RuntimeError, match="no weights"):
            b._load()

    def test_get_backend_falls_back_with_a_warning(self, monkeypatch):
        monkeypatch.delenv("DRISHTI_SEG_WEIGHTS", raising=False)
        b, warn = masking.get_backend("semantic")
        assert b.name != "torchvision_semantic"
        assert warn and "weights" in warn.lower()


class TestAGPLAlias:
    @pytest.mark.parametrize("alias", ["yolo", "fastsam"])
    def test_agpl_names_are_served_by_the_bsd_backend_with_notice(self, alias):
        b, warn = masking.get_backend(alias)
        assert warn and "AGPL" in warn
        assert b.name in ("maskrcnn", "optical_flow_residual")


class TestAreaCap:
    def test_oversized_instance_rejected(self):
        shape = (120, 160)
        # label 7 == train, the class that hallucinated on a roof
        b = _stub_backend([(7, 0.74, _blob(shape, 0.47))], shape)
        keep = b.mask(None, np.zeros((*shape, 3), np.uint8))
        assert (keep == 0).mean() == 0.0        # nothing masked
        assert b.rejected_large == 1

    def test_genuine_small_object_still_masked(self):
        shape = (120, 160)
        b = _stub_backend([(3, 0.9, _blob(shape, 0.005))], shape)   # car
        keep = b.mask(None, np.zeros((*shape, 3), np.uint8))
        assert 0.0 < (keep == 0).mean() <= 0.01
        assert b.rejected_large == 0

    def test_cap_is_per_instance_not_cumulative(self):
        # many small objects may legitimately sum past the cap
        shape = (120, 160)
        inst = [(3, 0.9, _blob(shape, 0.005))] * 8      # 4% total, 0.5% each
        b = _stub_backend(inst, shape)
        keep = b.mask(None, np.zeros((*shape, 3), np.uint8))
        assert b.rejected_large == 0
        assert (keep == 0).mean() > 0.0

    def test_static_classes_never_masked(self):
        shape = (120, 160)
        b = _stub_backend([(85, 0.99, _blob(shape, 0.004))], shape)   # clock
        keep = b.mask(None, np.zeros((*shape, 3), np.uint8))
        assert (keep == 0).mean() == 0.0

    def test_low_score_ignored(self):
        shape = (120, 160)
        b = _stub_backend([(3, 0.2, _blob(shape, 0.004))], shape)
        keep = b.mask(None, np.zeros((*shape, 3), np.uint8))
        assert (keep == 0).mean() == 0.0


class TestMaskSemantics:
    def test_keep_is_255_and_dynamic_is_0(self):
        shape = (120, 160)
        b = _stub_backend([(1, 0.9, _blob(shape, 0.01))], shape)     # person
        keep = b.mask(None, np.zeros((*shape, 3), np.uint8))
        assert set(np.unique(keep)).issubset({0, 255})
        assert (keep == 255).any() and (keep == 0).any()

    def test_null_backend_keeps_everything(self):
        b, _ = masking.get_backend("none")
        keep = b.mask(None, np.zeros((40, 50, 3), np.uint8))
        assert (keep == 255).all()
