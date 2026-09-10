"""Feature backends: the adapter must be real, and the SIFT path must not move.

Two things matter here beyond "it runs":

* The default SIFT path has to be **byte-identical** to the original inline
  implementation, or every archived benchmark silently stops being comparable.
* The abstraction has to actually hold for a backend that is not SIFT-shaped —
  different descriptor type, different distance metric — otherwise it will only
  break when the learned matcher is plugged in.
"""
from __future__ import annotations

import numpy as np
import pytest

cv2 = pytest.importorskip("cv2")

from drishti_recon import features, sfm            # noqa: E402


def _textured(seed=0, size=320):
    """A high-frequency image with plenty of corners to detect."""
    rng = np.random.default_rng(seed)
    small = rng.integers(0, 255, (size // 8, size // 8), dtype=np.uint8)
    img = cv2.resize(small, (size, size), interpolation=cv2.INTER_NEAREST)
    img[::40, :] = 20
    img[:, ::40] = 20
    return img


def _shifted(img, dx=7, dy=4):
    M = np.float32([[1, 0, dx], [0, 1, dy]])
    return cv2.warpAffine(img, M, (img.shape[1], img.shape[0]))


# --------------------------------------------------------------------------- #
# the default path must not change
# --------------------------------------------------------------------------- #
def test_sift_backend_matches_the_original_inline_implementation():
    """Regression guard for every archived benchmark."""
    img = _textured()
    # original inline behaviour
    sift = cv2.SIFT_create(nfeatures=4000, contrastThreshold=0.02)
    kp_ref, desc_ref = sift.detectAndCompute(img, None)

    be = features.SiftBackend(nfeatures=4000, contrast_threshold=0.02)
    pts, desc = be.detect(img, None)

    assert len(pts) == len(kp_ref)
    assert np.allclose(pts, np.array([k.pt for k in kp_ref], np.float32))
    assert np.allclose(desc, desc_ref)


def test_sfm_detect_default_is_unchanged_by_the_adapter():
    """`backend=None` must take the untouched original code path."""
    img = _textured(1)
    kp, desc = sfm._detect(img, None, 4000)          # default path
    sift = cv2.SIFT_create(nfeatures=4000, contrastThreshold=0.02)
    kp_ref, desc_ref = sift.detectAndCompute(img, None)
    assert len(kp) == len(kp_ref)
    assert np.allclose(desc, desc_ref)


def test_sfm_match_default_is_unchanged_by_the_adapter():
    a, b = _textured(2), _shifted(_textured(2))
    sift = cv2.SIFT_create(nfeatures=4000, contrastThreshold=0.02)
    _, d1 = sift.detectAndCompute(a, None)
    _, d2 = sift.detectAndCompute(b, None)
    got = sfm._match(d1, d2, 0.75)

    bf = cv2.BFMatcher(cv2.NORM_L2)
    ref = []
    for m_n in bf.knnMatch(d1, d2, k=2):
        if len(m_n) == 2 and m_n[0].distance < 0.75 * m_n[1].distance:
            ref.append((m_n[0].queryIdx, m_n[0].trainIdx))
    assert got == ref


# --------------------------------------------------------------------------- #
# the abstraction must hold for a non-SIFT backend
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("name", ["sift", "orb"])
def test_backend_detects_and_matches_a_shifted_image(name):
    be = features.create(name)
    a = _textured(3)
    b = _shifted(a, dx=6, dy=3)
    p1, d1 = be.detect(a, None)
    p2, d2 = be.detect(b, None)
    assert len(p1) > 20 and len(p2) > 20
    assert p1.shape[1] == 2 and p1.dtype == np.float32

    pairs = be.match(d1, d2, kp1=p1, kp2=p2, shape=a.shape)
    assert len(pairs) > 10, f"{name} found only {len(pairs)} matches"

    # The recovered shift should be about right for most matches -- this checks
    # the indices actually correspond, not merely that pairs were produced.
    d = np.array([p2[j] - p1[i] for i, j in pairs])
    med = np.median(d, axis=0)
    assert abs(med[0] - 6) < 2.5 and abs(med[1] - 3) < 2.5, med


@pytest.mark.parametrize("name", ["sift", "orb"])
def test_backend_respects_a_mask(name):
    """A masked (dynamic) region must not contribute keypoints."""
    be = features.create(name)
    img = _textured(4)
    mask = np.zeros_like(img)
    mask[:, : img.shape[1] // 2] = 255          # keep only the left half
    pts, _ = be.detect(img, mask)
    assert len(pts) > 0
    assert (pts[:, 0] <= img.shape[1] // 2 + 2).all(), "keypoint outside the mask"


def test_backends_are_usable_through_sfm_helpers():
    """The sfm-side wrappers must accept a backend and return .pt keypoints."""
    be = features.create("orb")
    img = _textured(5)
    kp, desc = sfm._detect(img, None, 4000, backend=be)
    assert len(kp) > 10
    assert isinstance(kp[0].pt, tuple) and len(kp[0].pt) == 2
    kp2, desc2 = sfm._detect(_shifted(img), None, 4000, backend=be)
    pairs = sfm._match(desc, desc2, backend=be, kp1=kp, kp2=kp2, shape=img.shape)
    assert len(pairs) > 5


# --------------------------------------------------------------------------- #
# registry, licensing and failure behaviour
# --------------------------------------------------------------------------- #
def test_unknown_backend_fails_loudly():
    """Silently defaulting to SIFT would mislabel a whole benchmark run."""
    with pytest.raises(ValueError, match="unknown feature backend"):
        features.create("does-not-exist")


def test_superpoint_is_refused_by_default_on_licence_grounds():
    """The weights, not the code, are non-commercial — refuse unless told."""
    with pytest.raises((ValueError, ImportError)) as exc:
        features.create("superpoint")
    msg = str(exc.value).lower()
    # Either the licence refusal, or torch/kornia genuinely missing.
    assert "non-commercial" in msg or "refusing" in msg or "kornia" in msg


def test_backend_reports_its_licence_and_kind():
    for name in ("sift", "orb"):
        info = features.create(name).info()
        assert info.kind == "classical"
        assert info.licence and info.licence != "unknown"
        assert "name" in info.to_dict()


def test_available_reports_what_can_run():
    av = features.available()
    assert av["sift"] is True and av["orb"] is True
    assert "lightglue" in av        # True, or a string explaining why not


def test_empty_descriptors_match_to_nothing():
    for name in ("sift", "orb"):
        be = features.create(name)
        assert be.match(None, None) == []
        assert be.match(np.zeros((0, 128), np.float32),
                        np.zeros((0, 128), np.float32)) == []
