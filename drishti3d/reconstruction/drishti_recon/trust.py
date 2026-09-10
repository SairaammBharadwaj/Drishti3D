"""Intelligence trust score (doc §20).

    C = w1*O + w2*N + w3*(1 - E) + w4*P,   sum(w) = 1

O  multi-view observation support
N  network (model) confidence, when a learned backbone supplied one
E  normalised geometric residual
P  parallax quality

Two things make this score honest rather than decorative, and both were
established by measurement rather than assumption:

**The normalisations are fitted, not guessed.** The saturation constants decide
whether a term discriminates at all. The first version of this module used
plausible-sounding constants -- 6 views, 2 px, 10 degrees -- against a pipeline
whose actual distribution is 11 views median, 0.09 px median, 17 deg median.
O and P sat pinned at 1.0 for over half the points and contributed nothing.
:func:`fit_normalisation` derives the constants from the data's own quantiles.

**The terms are correlated, and the weights are not importances.** Measured on
the synthetic oblique_pass scene: obs_count and triangulation angle correlate
at rho = 0.88, and obs_count's partial correlation with error, controlling for
parallax, is +0.04 -- it carries almost no independent information. Reprojection
residual is confounded the other way: marginally it appears to have the WRONG
sign (rho = -0.08 against error) purely because points with many views
accumulate more residual while being more accurate; controlled for track length
it is correctly positive (+0.13 to +0.23), and positive inside every track-length
band. So a fitted weight vector ranks well but must not be read as "this term
matters this much".
"""
from __future__ import annotations

import numpy as np

#: Saturation constants measured on the synthetic oblique_pass scene. Treat as
#: a starting point; call :func:`fit_normalisation` on your own distribution.
DEFAULT_NORM = {"obs_saturation": 24.0,
                "resid_saturation_px": 0.45,
                "parallax_saturation_deg": 35.0}


def _unit(x, lo, hi):
    x = np.asarray(x, float)
    return np.clip((x - lo) / max(hi - lo, 1e-12), 0.0, 1.0)


def fit_normalisation(*, obs_count=None, residual_px=None, tri_angle_deg=None,
                      quantile: float = 0.95):
    """Derive saturation constants from the data's own distribution.

    Each term saturates at the given quantile of its evidence, so roughly the
    top 5 % of points reach 1.0 and the rest spread across the range. Fixing
    the constants by intuition instead measured out at zero discriminative
    power for two of the three terms.
    """
    out = dict(DEFAULT_NORM)
    if obs_count is not None:
        out["obs_saturation"] = float(max(
            np.quantile(np.asarray(obs_count, float), quantile), 2.0))
    if residual_px is not None:
        out["resid_saturation_px"] = float(max(
            np.quantile(np.asarray(residual_px, float), quantile), 1e-3))
    if tri_angle_deg is not None:
        out["parallax_saturation_deg"] = float(max(
            np.quantile(np.asarray(tri_angle_deg, float), quantile), 1.0))
    return out


def components(*, obs_count, net_conf=None, residual_px=None,
               tri_angle_deg=None, norm=None):
    """Map raw per-point evidence onto the four [0,1] terms.

    ``obs_count`` enters through a square root: measured median error by track
    length runs 0.063, 0.034, 0.023, 0.016, 0.009 m across bands centred near
    2.5, 5, 9.5, 19 and 60 views -- close to the 1/sqrt(n) that independent
    observations predict, and badly modelled by a linear ramp.

    Terms whose evidence is absent come back as ``None`` and their weight is
    redistributed at score time.
    """
    n = dict(DEFAULT_NORM)
    if norm:
        n.update(norm)
    obs = np.asarray(obs_count, float)
    O = _unit(np.sqrt(np.maximum(obs, 1.0)), 1.0,
              np.sqrt(max(n["obs_saturation"], 1.0 + 1e-9)))
    N = None if net_conf is None else np.clip(np.asarray(net_conf, float), 0, 1)
    E = None if residual_px is None else _unit(residual_px, 0.0,
                                               n["resid_saturation_px"])
    P = None if tri_angle_deg is None else _unit(tri_angle_deg, 0.0,
                                                 n["parallax_saturation_deg"])
    return O, N, E, P


def score(O, N, E, P, weights=(0.25, 0.15, 0.25, 0.35)):
    """Combine components; absent terms redistribute their weight.

    Raises if the supplied weights put *all* their mass on absent terms --
    silently returning zeros there would look like a confident "untrusted"
    verdict on every point.
    """
    terms = [O, N, None if E is None else 1.0 - np.asarray(E, float), P]
    w = np.asarray(weights, float)
    present = [i for i, t in enumerate(terms) if t is not None]
    if not present:
        raise ValueError("no trust components supplied")
    mass = w[present].sum()
    if mass <= 1e-12:
        raise ValueError(
            "all weight lies on components that are absent; "
            f"present={present}, weights={weights}")
    w_use = w[present] / mass
    out = np.zeros(np.shape(terms[present[0]]), float)
    for wi, i in zip(w_use, present):
        out = out + wi * np.asarray(terms[i], float)
    return out


def calibrate_weights(O, N, E, P, true_error, *, grid: int = 10):
    """Sweep the weight simplex; keep the weights that best rank points by
    true error (Spearman, negated -- high trust must mean low error).

    Returns ``(weights, spearman)``. A coarse exhaustive sweep is deliberate:
    four weights on a simplex is a 3-D search of a few hundred candidates,
    reproducible and free of local minima, and the objective is flat near its
    optimum anyway. Candidates whose mass lies entirely on absent components
    are skipped rather than producing a silent NaN.

    The returned weights are renormalised over the components that were
    actually present, so they are the weights the score really applies. The
    raw sweep can place mass on an absent term -- harmless, since
    :func:`score` redistributes it, but reporting it would suggest a term
    contributed when it was never supplied.
    """
    from scipy.stats import spearmanr
    true_error = np.asarray(true_error, float)
    terms = [O, N, E, P]
    present = np.array([t is not None for t in terms])
    best_w, best_val = None, -np.inf
    g = grid
    for a in range(g + 1):
        for b in range(g + 1 - a):
            for c in range(g + 1 - a - b):
                d = g - a - b - c
                w = np.array([a, b, c, d], float) / g
                if w[present].sum() <= 1e-12:
                    continue
                r = spearmanr(score(O, N, E, P, w), true_error).statistic
                if np.isnan(r):
                    continue
                if -r > best_val:
                    best_w, best_val = w, -r
    if best_w is None:
        raise RuntimeError("calibration found no usable weight vector")
    eff = np.zeros(4)
    eff[present] = best_w[present] / best_w[present].sum()
    return eff, float(best_val)
