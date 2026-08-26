import pytest
import numpy as np
from app.dynamics.context import VisualContext
from app.dynamics.material import MaterialStateEngine, MaterialState


def make_dummy_context(time: float, rms: float, onset: float, harm_ratio: float = 0.8) -> VisualContext:
    return VisualContext(
        time=time,
        activity=min(1.0, rms * 1.5),
        energy_fast=rms,
        energy_slow=rms * 0.8,
        energy_trend=0.0,
        bass_drive=rms, mid_drive=rms, high_drive=rms,
        spectral_brightness=0.5, spectral_noise=0.1, spectral_tilt=0.5,
        onset=onset, flux=onset * 0.8, beat_impulse=0.0, beat_confidence=0.8,
        transient_density=onset, beat_density=0.5,
        harmonic_ratio=harm_ratio, tonal_confidence=0.8,
        chroma=np.zeros(12),
        novelty=0.0, boundary_impulse=0.0, climax_prior=0.5, section_progress=0.5
    )


def test_true_hysteresis_path_dependence():
    """Verify Path B (after intense climax) retains higher defect_density than Path A (from quiet)."""
    # Path A: Quiet -> Medium
    engine_a = MaterialStateEngine()
    for t in range(50):
        ctx = make_dummy_context(t * 0.016, rms=0.2, onset=0.0)
        engine_a.update(ctx, dt=0.016)

    for t in range(50, 100):
        ctx = make_dummy_context(t * 0.016, rms=0.5, onset=0.2)
        state_a = engine_a.update(ctx, dt=0.016)

    # Path B: Heavy Climax -> Medium
    engine_b = MaterialStateEngine()
    for t in range(50):
        ctx = make_dummy_context(t * 0.016, rms=0.95, onset=0.95)
        engine_b.update(ctx, dt=0.016)

    for t in range(50, 100):
        ctx = make_dummy_context(t * 0.016, rms=0.5, onset=0.2)
        state_b = engine_b.update(ctx, dt=0.016)

    # Verify path dependence: state_b retains higher defect_density
    assert state_b.defect_density > state_a.defect_density
