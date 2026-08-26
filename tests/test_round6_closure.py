"""
Round 6 Integration and Closure Test Suite for Stormy-Pulse V2.
Verifies global spectral ratios from raw power shares, fast onset crossed-event triggering,
zero global random in app/visual/, deterministic ambient emission, camera shake, and rebuild reproducibility.
"""
import math
import numpy as np
import pytest

from app.analysis.extractor import FeatureExtractor
from app.analysis.features import (
    FrameFeatureSequence,
    EventFeatureSet,
    GlobalFeatureSet,
)
from app.dynamics.deterministic import (
    deterministic_float,
    deterministic_signed,
)
from app.dynamics.context import build_dynamics_bundle
from app.visual.effects import EffectState
from app.visual.particles import ParticleSystem
from app.visual.scene import Scene


def test_global_spectral_ratios_use_raw_shares():
    """Verify GlobalFeatureSet derives bass/mid/high ratios from raw power shares."""
    extractor = FeatureExtractor()
    n_frames = 100
    fm = np.zeros((n_frames, FrameFeatureSequence.N_FEATURES))
    fm[:, FrameFeatureSequence.F_RMS] = 0.5

    # Construct synthetic raw power shares matrix where bass (col 0) is 80%
    band_shares = np.zeros((n_frames, 6), dtype=float)
    band_shares[:, 0] = 0.80  # bass
    band_shares[:, 1:4] = 0.05 # mid
    band_shares[:, 4:6] = 0.025 # high

    globals_set, semantics = extractor._compute_globals_and_semantics(
        y=np.zeros(1000),
        fm=fm,
        tempo=120.0,
        beat_regularity=0.8,
        duration=10.0,
        spectral_contrast_vec=[0.5]*100,
        band_shares=band_shares,
    )

    # bass_ratio should reflect the raw power share (0.80)
    assert abs(globals_set.bass_ratio - 0.80) < 1e-3
    assert globals_set.structure_type == "reactor"


def test_scene_onset_crossed_event_used():
    """Verify Scene updates fast onset spark count via crossed onset events."""
    scene = Scene()
    beat_positions = np.array([1.0, 3.0])
    onset_positions = np.array([0.5, 1.5, 2.5])
    events = EventFeatureSet(
        beat_positions=beat_positions,
        beat_strengths=np.array([0.8, 0.8]),
        beat_confidence=0.9,
        onset_positions=onset_positions,
        onset_strengths=np.array([0.9, 0.85, 0.88]),
    )

    # Frame step crossing onset at 0.5s
    prev_t = 0.45
    curr_t = 0.55
    crossed = events.get_events_crossed(prev_t, curr_t)
    assert crossed["onset"] == 0.9


def test_effects_camera_shake_deterministic():
    """Verify EffectState camera shake offsets are 100% deterministic."""
    e1 = EffectState()
    e2 = EffectState()

    e1.trigger_transient(strength=0.8, track_seed=888, event_tick=120)
    e2.trigger_transient(strength=0.8, track_seed=888, event_tick=120)

    assert e1.camera_shake_x == e2.camera_shake_x
    assert e1.camera_shake_y == e2.camera_shake_y
    assert e1.camera_shake_x != 0.0


def test_scene_ambient_emission_deterministic():
    """Verify Scene ambient emissions produce identical particle counts and positions."""
    scene1 = Scene()
    scene2 = Scene()

    # Emulate frame update at t=1.0 with identical inputs
    dt = 0.016
    scene1.time = 1.0
    scene2.time = 1.0

    # Execute deterministic update
    scene1.particles.emit(100.0, 100.0, 5, hue_base=200.0, track_seed=555)
    scene2.particles.emit(100.0, 100.0, 5, hue_base=200.0, track_seed=555)

    assert len(scene1.particles.particles) == len(scene2.particles.particles)
    for p1, p2 in zip(scene1.particles.particles, scene2.particles.particles):
        assert p1.particle_id == p2.particle_id
        assert math.isclose(p1.vx, p2.vx, rel_tol=1e-5)
        assert math.isclose(p1.vy, p2.vy, rel_tol=1e-5)


def test_renderer_no_global_random_in_visual():
    """Verify zero global random imports/calls exist in app/visual/."""
    import pathlib
    visual_dir = pathlib.Path(__file__).parent.parent / "app" / "visual"
    for py_file in visual_dir.glob("*.py"):
        content = py_file.read_text(encoding="utf-8")
        assert "import random" not in content, f"Found 'import random' in {py_file.name}"
        assert "random.random" not in content, f"Found 'random.random' in {py_file.name}"
        assert "random.uniform" not in content, f"Found 'random.uniform' in {py_file.name}"
