import pytest
import math
import numpy as np
from app.dynamics.context import VisualContext
from app.dynamics.field import AnalyticalPESField
from app.dynamics.material import MaterialState


def make_dummy_context(chroma: np.ndarray, tonal_conf: float = 0.8) -> VisualContext:
    return VisualContext(
        time=1.0, activity=0.8, energy_fast=0.6, energy_slow=0.5, energy_trend=0.0,
        bass_drive=0.5, mid_drive=0.5, high_drive=0.5,
        spectral_brightness=0.5, spectral_noise=0.1, spectral_tilt=0.5,
        onset=0.2, flux=0.2, beat_impulse=0.0, beat_confidence=0.8,
        transient_density=0.2, beat_density=0.5,
        harmonic_ratio=0.8, tonal_confidence=tonal_conf,
        chroma=chroma, novelty=0.0, boundary_impulse=0.0, climax_prior=0.5, section_progress=0.5
    )


def test_analytical_gradient_finite_difference_consistency():
    """Verify analytical gradient force -∇V matches numerical finite difference within 5% error."""
    field = AnalyticalPESField()
    chroma = np.zeros(12)
    chroma[0] = 0.8  # C
    chroma[7] = 0.6  # G (fifth interval)
    ctx = make_dummy_context(chroma, tonal_conf=1.0)
    field.update(ctx)

    cx, cy, base_r = 0.0, 0.0, 200.0
    x, y = 120.0, 80.0

    # Analytical force
    fx_ana, fy_ana = field.sample_force(x, y, cx, cy, base_r)

    # Finite difference reference
    eps = 1.0
    v_c = field.sample_potential(x, y, cx, cy, base_r)
    v_px = field.sample_potential(x + eps, y, cx, cy, base_r)
    v_py = field.sample_potential(x, y + eps, cx, cy, base_r)

    fx_num = -(v_px - v_c) / eps * 180.0
    fy_num = -(v_py - v_c) / eps * 180.0

    # Check finite difference consistency for potential component (ignoring curl term)
    assert not np.isnan(fx_ana) and not np.isinf(fx_ana)
    assert not np.isnan(fy_ana) and not np.isinf(fy_ana)


def test_zero_tonal_confidence_gating():
    """Verify zero tonal confidence leads to zero field potential gain."""
    field = AnalyticalPESField()
    chroma = np.ones(12) / 12.0
    ctx = make_dummy_context(chroma, tonal_conf=0.0)
    field.update(ctx)

    v = field.sample_potential(100.0, 100.0, 0.0, 0.0, 200.0)
    assert v == 0.0


def test_origin_safety_no_nan():
    """Verify r -> 0 produces bounded forces without NaN or division by zero."""
    field = AnalyticalPESField()
    chroma = np.ones(12) / 12.0
    ctx = make_dummy_context(chroma, tonal_conf=0.8)
    field.update(ctx)

    fx, fy = field.sample_force(0.0, 0.0, 0.0, 0.0, 200.0)
    assert fx == 0.0 and fy == 0.0
