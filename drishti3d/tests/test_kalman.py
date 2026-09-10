"""Kalman/RTS telemetry smoother tests.

The bias limitation is documented in D-031: a smoother removes white jitter
only. These tests pin down the white-noise win and the honest behaviour of the
posterior sigma in that regime; they deliberately do NOT claim bias removal.
"""
import numpy as np

from drishti_recon.telemetry import kalman_smooth


def make_track(n=240, dt=0.5, speed=(3.0, 0.5, 0.1), accel=0.3, seed=0):
    rng = np.random.default_rng(seed)
    t = np.arange(n) * dt
    v = np.array(speed) + np.cumsum(rng.normal(0, accel * dt, (n, 3)), 0)
    p = np.cumsum(v * dt, 0)
    return t, p


class TestWhiteNoise:
    def test_error_reduced_substantially(self):
        t, p = make_track()
        rng = np.random.default_rng(1)
        z = p + rng.normal(0, 4.0, p.shape)
        sm, sig = kalman_smooth(t, z, sigma_m=4.0, accel_m_s2=0.5)
        e_raw = np.linalg.norm(z - p, axis=1)
        e_sm = np.linalg.norm(sm - p, axis=1)
        assert np.median(e_sm) < 0.55 * np.median(e_raw)

    def test_posterior_sigma_honest_for_white_noise(self):
        t, p = make_track(seed=2)
        rng = np.random.default_rng(3)
        z = p + rng.normal(0, 4.0, p.shape)
        sm, sig = kalman_smooth(t, z, sigma_m=4.0, accel_m_s2=0.5)
        err = np.linalg.norm(sm - p, axis=1) / np.sqrt(3)   # per-axis scale
        # calibrated within a factor of ~1.8 in the regime it is valid for
        ratio = np.median(err) / np.median(sig)
        assert 0.4 < ratio < 1.8

    def test_short_input_passthrough(self):
        t = np.array([0.0, 1.0])
        z = np.array([[0.0, 0, 0], [1.0, 0, 0]])
        sm, sig = kalman_smooth(t, z, sigma_m=2.0)
        assert np.allclose(sm, z)


class TestBiasRegime:
    def test_bias_passes_through_and_is_not_hidden(self):
        # constant 5 m bias: smoother must not pretend to remove it
        t, p = make_track(seed=4)
        z = p + np.array([5.0, 0, 0])
        sm, sig = kalman_smooth(t, z, sigma_m=4.0, accel_m_s2=0.5)
        residual_bias = np.median(np.linalg.norm(sm - p, axis=1))
        assert residual_bias > 4.0          # still ~5 m off — documented limit
