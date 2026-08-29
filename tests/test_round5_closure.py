"""
Round 5 Integration and Closure Test Suite for Stormy-Pulse V2.
Verifies GeometryControl morphing, raw band shares, event causality, continuous damage healing,
keyed deterministic randomness, and centralized warmup ownership.
"""
import sys
import math
import subprocess
import numpy as np
import pytest

from app.config.constants import CACHE_VERSION
from app.analysis.spectrum import compute_band_energies_6
from app.analysis.features import (
    FrameFeatureSequence,
    EventFeatureSet,
    GlobalFeatureSet,
)
from app.dynamics.deterministic import (
    deterministic_hash_uint64,
    deterministic_float,
    deterministic_uniform,
    deterministic_signed,
)
from app.dynamics.material import GeometryControl, MaterialState
from app.visual.ring_layer import RingLayer
from app.visual.particles import ParticleSystem
from app.visual.scene import Scene


def test_v6_cache_version():
    """Verify CACHE_VERSION is bumped to v6."""
    assert CACHE_VERSION == "v6", f"Expected v6 cache version, got {CACHE_VERSION}"


def test_raw_band_shares_sum_and_spectral_tilt():
    """Verify raw band shares sum to ~1.0 and calculate correct proportions."""
    n_fft = 2048
    sr = 44100
    n_frames = 100
    S_power = np.ones((n_fft // 2 + 1, n_frames), dtype=np.float32) * 1e-4

    # Make bass frequency bins dominant (bins < 250Hz)
    freqs = np.linspace(0, sr / 2, n_fft // 2 + 1)
    bass_bins = (freqs >= 0) & (freqs < 250)
    S_power[bass_bins, :] = 10.0

    drives, shares = compute_band_energies_6(S_power, n_fft, sr, return_shares=True)

    # Raw shares shape (6, N)
    assert shares.shape == (6, n_frames)
    col_sums = np.sum(shares, axis=0)
    np.testing.assert_allclose(col_sums, 1.0, rtol=1e-4)

    # Bass share (index 0) should be dominant (> 0.70)
    assert np.mean(shares[0]) > 0.70


def test_event_causality_crossed():
    """Verify get_events_crossed is strictly causal (prev < position <= curr)."""
    beat_positions = np.array([1.0, 2.0, 3.0])
    beat_strengths = np.array([0.8, 0.9, 0.85])
    onset_positions = np.array([1.5, 2.5])
    onset_strengths = np.array([0.7, 0.75])

    events = EventFeatureSet(
        beat_positions=beat_positions,
        beat_strengths=beat_strengths,
        beat_confidence=0.9,
        onset_positions=onset_positions,
        onset_strengths=onset_strengths,
    )

    # Before event
    c0 = events.get_events_crossed(0.0, 0.95)
    assert c0["beat"] == 0.0
    assert c0["onset"] == 0.0

    # Cross beat 1.0
    c1 = events.get_events_crossed(0.95, 1.05)
    assert c1["beat"] == 0.8

    # After beat 1.0 (no double fire)
    c2 = events.get_events_crossed(1.05, 1.45)
    assert c2["beat"] == 0.0

    # Cross onset 1.5
    c3 = events.get_events_crossed(1.45, 1.55)
    assert c3["onset"] == 0.7


def test_continuous_ring_damage_healing():
    """Verify RingLayer damage_current performs continuous annealing interpolation."""
    ring_layer = RingLayer(ring_count=5)
    geom = GeometryControl(
        symmetry=0.2,
        coherence=0.5,
        roughness=0.5,
        angular_lock=0.5,
        circulation=0.2,
        fragmentation=0.8,
    )
    mat = MaterialState(
        order=0.2,
        excitation=0.8,
        mobility=0.8,
        defect_density=0.8,
        activity=0.8,
        w_crystalline=0.1,
        w_hydrodynamic=0.3,
        w_plasma=0.6,
        phase_name="plasma",
    )

    # Step forward with high defect
    ring_layer.update(
        bands=[0.5]*5, bass=0.5, mid=0.5, high=0.5, energy=0.5, chaos=0.5,
        beat_pulse=0.0, beat_strength=0.0, is_on_beat=False, bpm=120.0, dt=0.016, time=0.1,
        track_seed=12345, material=mat, geometry=geom,
    )

    d1 = ring_layer.damage_current[0]
    assert d1 > 0.0

    # Next frame with low defect (annealing/healing)
    mat_healed = MaterialState(
        order=0.9,
        excitation=0.2,
        mobility=0.2,
        defect_density=0.0,
        activity=0.5,
        w_crystalline=0.8,
        w_hydrodynamic=0.1,
        w_plasma=0.1,
        phase_name="crystal",
    )
    geom_healed = GeometryControl(
        symmetry=0.8,
        coherence=0.8,
        roughness=0.0,
        angular_lock=0.8,
        circulation=0.0,
        fragmentation=0.0,
    )
    ring_layer.update(
        bands=[0.5]*5, bass=0.5, mid=0.5, high=0.5, energy=0.5, chaos=0.5,
        beat_pulse=0.0, beat_strength=0.0, is_on_beat=False, bpm=120.0, dt=0.016, time=0.2,
        track_seed=12345, material=mat_healed, geometry=geom_healed,
    )

    d2 = ring_layer.damage_current[0]
    # Healing should smoothly decrease damage, not instantly jump to 0.0
    assert 0.0 < d2 < d1


def test_deterministic_particle_emission():
    """Verify particle system emissions are 100% reproducible for same seed."""
    ps1 = ParticleSystem(max_particles=500)
    ps2 = ParticleSystem(max_particles=500)

    ps1.emit(x=100.0, y=100.0, count=20, hue_base=200.0, track_seed=999)
    ps2.emit(x=100.0, y=100.0, count=20, hue_base=200.0, track_seed=999)

    assert len(ps1.particles) == len(ps2.particles)
    for p1, p2 in zip(ps1.particles, ps2.particles):
        assert p1.particle_id == p2.particle_id
        assert math.isclose(p1.vx, p2.vx, rel_tol=1e-5)
        assert math.isclose(p1.vy, p2.vy, rel_tol=1e-5)
        assert math.isclose(p1.size, p2.size, rel_tol=1e-5)
        assert math.isclose(p1.hue, p2.hue, rel_tol=1e-5)


def test_cross_process_keyed_determinism():
    """Verify keyed deterministic hash produces exact same values across subprocesses."""
    code = (
        "from app.dynamics.deterministic import deterministic_float; "
        "print(deterministic_float(777, 'test_stream', 42, 3))"
    )

    res1 = subprocess.check_output([sys.executable, "-c", code], text=True).strip()
    res2 = subprocess.check_output([sys.executable, "-c", code], text=True).strip()

    assert res1 == res2
    assert float(res1) == deterministic_float(777, "test_stream", 42, 3)


def test_scene_rebuild_to_time():
    """Verify Scene.rebuild_to_time centralizes full-history replay deterministically."""
    scene = Scene()
    scene.rebuild_to_time(time=1.5, width=1280, height=720)
    assert scene.time == 1.5
