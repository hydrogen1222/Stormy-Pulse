import pytest
import numpy as np
from app.analysis.beat import detect_beats, compute_beat_regularity
from app.analysis.features import FeatureFrame, GlobalFeatureSet
from app.dynamics.calibration import TrackCalibration
from app.visual.scene import Scene
from app.visual.phase_engine import PhaseEngine


def test_no_fake_120bpm_beats_on_flat_signal():
    """Verify that detect_beats returns empty arrays on flat signal (no fake 120 BPM beats)."""
    flat_onset = np.zeros(500, dtype=float)
    beats, strengths = detect_beats(flat_onset, sample_rate=44100, hop_length=512)
    assert len(beats) == 0
    assert len(strengths) == 0
    assert compute_beat_regularity(beats) == 0.0


def test_scene_reset_contract():
    """Verify Scene.reset clears PhaseEngine, PESField, and phase_state."""
    scene = Scene()
    frame = FeatureFrame(
        time=1.0, rms=0.5, bass=0.5, mid=0.5, high=0.5,
        onset_strength=0.5, spectral_centroid=0.5, spectral_rolloff=0.5,
        spectral_flatness=0.1, beat=1.0, beat_strength=0.8,
        chroma_vector=np.ones(12)/12.0, harmonic_e=0.6, percussive_e=0.4, flux=0.2
    )
    scene.update(frame, is_playing=True, width=1280, height=720, dt=0.016)
    assert scene.phase_state is not None

    scene.reset()
    assert scene.phase_state is None
    assert scene.phase_engine.temp_eff == 0.3


def test_silence_dormant_activity_gate():
    """Verify that silence leads to dormant phase state rather than forced fluid turbulence."""
    engine = PhaseEngine()
    # Feed silence / near-zero input for ~2 seconds
    for _ in range(120):
        state = engine.update(
            rms=0.0, bass=0.0, mid=0.0, high=0.0,
            onset_strength=0.0, flatness=0.0,
            harmonic_e=0.0, percussive_e=0.0, flux=0.0, dt=0.016
        )

    assert state.phase_name == "dormant"
    assert state.effective_temp < 0.05
    assert state.w_crystalline > state.w_hydrodynamic


def test_rms_calibration_reference_consistency():
    """Verify normalize_rms_db uses track max_rms reference consistently."""
    rms_arr = np.linspace(0.02, 0.20, 1000)
    flux_arr = np.ones(1000)
    onset_arr = np.ones(1000)
    calib = TrackCalibration.compute(rms_arr, flux_arr, onset_arr)

    norm_min = calib.normalize_rms_db(0.02)
    norm_mid = calib.normalize_rms_db(0.10)
    norm_max = calib.normalize_rms_db(0.20)

    assert norm_min < norm_mid < norm_max
    assert norm_max >= 0.95
