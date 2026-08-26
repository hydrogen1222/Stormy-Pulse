import pytest
import numpy as np
from app.visual.phase_engine import PhaseEngine, PhaseState


def test_phase_engine_initialization():
    engine = PhaseEngine()
    assert engine.order_param == 0.5
    assert engine.temp_eff == 0.3


def test_phase_engine_transitions():
    engine = PhaseEngine()

    # 1. Classical / Harmonic input -> Crystalline Phase
    for _ in range(30):
        state = engine.update(
            rms=0.15,
            bass=0.1,
            mid=0.3,
            high=0.2,
            onset_strength=0.1,
            flatness=0.05,
            harmonic_e=0.9,
            percussive_e=0.1,
            flux=0.02,
            dt=0.016,
        )

    assert state.w_crystalline > state.w_plasma
    assert state.order_parameter > 0.5

    # 2. High Energy Percussive / Noise input -> Plasma Phase
    for _ in range(60):
        state = engine.update(
            rms=0.9,
            bass=0.95,
            mid=0.7,
            high=0.8,
            onset_strength=0.9,
            flatness=0.85,
            harmonic_e=0.1,
            percussive_e=0.9,
            flux=0.85,
            dt=0.016,
        )

    assert state.w_plasma > state.w_crystalline
    assert state.effective_temp > 0.7
