import numpy as np
import pytest

from drishti_recon import trust


def synth_points(n=2000, seed=0):
    rng = np.random.default_rng(seed)
    obs = rng.integers(1, 9, n)
    tri = rng.uniform(0.2, 15, n)
    resid = rng.uniform(0.05, 2.5, n)
    net = rng.uniform(0.2, 1.0, n)
    # true error genuinely driven by the evidence, plus noise
    err = (2.0 / np.sqrt(obs)) * (1.0 + resid) * (3.0 / (1 + tri)) \
        * rng.lognormal(0, 0.25, n)
    return obs, net, resid, tri, err


class TestComponents:
    def test_ranges(self):
        obs, net, resid, tri, _ = synth_points()
        O, N, E, P = trust.components(obs_count=obs, net_conf=net,
                                      residual_px=resid, tri_angle_deg=tri)
        for t in (O, N, E, P):
            assert t.min() >= 0 and t.max() <= 1

    def test_missing_terms_are_dropped(self):
        O, N, E, P = trust.components(obs_count=[2, 4])
        s = trust.score(O, N, E, P)
        assert s.shape == (2,)
        assert np.all(s >= 0) and np.all(s <= 1)


class TestCalibration:
    def test_calibrated_score_ranks_error(self):
        obs, net, resid, tri, err = synth_points()
        norm = trust.fit_normalisation(obs_count=obs, residual_px=resid,
                                       tri_angle_deg=tri)
        O, N, E, P = trust.components(obs_count=obs, net_conf=net,
                                      residual_px=resid, tri_angle_deg=tri,
                                      norm=norm)
        w, sp = trust.calibrate_weights(O, N, E, P, err, grid=8)
        assert abs(w.sum() - 1.0) < 1e-9
        # high trust must mean low error, strongly
        assert sp > 0.6
        # and calibrated weights must beat a deliberately bad weighting
        from scipy.stats import spearmanr
        bad = trust.score(O, N, E, P, (0.0, 1.0, 0.0, 0.0))
        sp_bad = -spearmanr(bad, err).statistic
        assert sp > sp_bad


class TestNormalisationFitting:
    def test_fitted_constants_prevent_saturation(self):
        obs, net, resid, tri, _ = synth_points()
        norm = trust.fit_normalisation(obs_count=obs, residual_px=resid,
                                       tri_angle_deg=tri)
        O, _, E, P = trust.components(obs_count=obs, residual_px=resid,
                                      tri_angle_deg=tri, norm=norm)
        # ~5% reach the ceiling by construction; obs_count is integer-valued
        # so its quantile lands on a repeated value and a few percent more tie
        # at the top. The contrast that matters is against the saturated case
        # below, where the fraction is 100%.
        for t in (O, E, P):
            assert (t >= 0.999).mean() < 0.20
            assert t.std() > 0.15          # genuinely spread, not degenerate

    def test_guessed_constants_can_saturate(self):
        # the failure this fitting exists to prevent: constants chosen for a
        # different distribution collapse a term to a constant
        obs = np.full(500, 30.0)           # every point well past 6 views
        O, _, _, _ = trust.components(obs_count=obs,
                                      norm={"obs_saturation": 6.0})
        assert (O >= 0.999).all()
        assert O.std() == 0.0

    def test_all_weight_on_absent_term_raises(self):
        O, N, E, P = trust.components(obs_count=[2, 4, 8])
        with pytest.raises(ValueError, match="absent"):
            trust.score(O, N, E, P, (0.0, 1.0, 0.0, 0.0))

    def test_returned_weights_cover_only_present_terms(self):
        obs, net, resid, tri, err = synth_points()
        O, N, E, P = trust.components(obs_count=obs, residual_px=resid,
                                      tri_angle_deg=tri)      # N absent
        w, _ = trust.calibrate_weights(O, N, E, P, err, grid=6)
        assert w[1] == 0.0                  # no mass reported on absent N
        assert abs(w.sum() - 1.0) < 1e-9
