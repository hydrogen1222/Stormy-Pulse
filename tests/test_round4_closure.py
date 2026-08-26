import math
import numpy as np
import pytest

from app.config.constants import CACHE_VERSION
from app.analysis.features import (
    TrackAnalysisMetadata,
    FrameFeatureSequence,
    EventFeatureSet,
    WindowFeatureSet,
    SectionFeatureSet,
    SemanticControlSet,
    GlobalFeatureSet,
    FeatureCache,
)
from app.analysis.window import compute_window_features
from app.dynamics.calibration import TrackCalibration
from app.dynamics.context import build_dynamics_bundle, VisualContextBuilder
from app.dynamics.material import MaterialState, GeometryControl
from app.visual.scene import Scene
from app.visual.particles import ParticleSystem


def create_mock_v5_cache(duration: float = 20.0) -> FeatureCache:
    fps = 50.0
    n_frames = int(duration * fps)
    times = np.linspace(0, duration, n_frames)

    feats = np.zeros((n_frames, FrameFeatureSequence.N_FEATURES), dtype=float)
    feats[:, FrameFeatureSequence.F_RMS] = np.sin(times * 0.5) * 0.15 + 0.10
    feats[:, FrameFeatureSequence.F_CENTROID] = 0.5
    feats[:, FrameFeatureSequence.F_ROLLOFF] = 0.6
    feats[:, FrameFeatureSequence.F_FLATNESS] = 0.1
    feats[:, FrameFeatureSequence.F_FLUX] = 0.05
    feats[:, FrameFeatureSequence.F_ONSET_STR] = 0.1
    feats[:, FrameFeatureSequence.F_BAND_BASS] = 0.2
    feats[:, FrameFeatureSequence.F_BAND_LOW_MID] = 0.2
    feats[:, FrameFeatureSequence.F_BAND_MID] = 0.2
    feats[:, FrameFeatureSequence.F_BAND_HIGH_MID] = 0.2
    feats[:, FrameFeatureSequence.F_BAND_HIGH] = 0.1
    feats[:, FrameFeatureSequence.F_BAND_PRESENCE] = 0.1

    seq = FrameFeatureSequence(times=times, frame_rate=fps, features=feats)
    events = EventFeatureSet(
        beat_positions=np.array([1.0, 2.0, 3.0, 4.0, 5.0]),
        beat_strengths=np.array([0.8, 0.8, 0.8, 0.8, 0.8]),
        beat_confidence=0.8,
        onset_positions=np.array([0.5, 1.5, 2.5, 3.5]),
        onset_strengths=np.array([0.5, 0.5, 0.5, 0.5]),
    )
    meta = TrackAnalysisMetadata("test.mp3", "test_hash_r4", CACHE_VERSION, duration, 44100, 1.0)

    windows_dict = compute_window_features(
        frame_features=feats,
        frame_rate=fps,
        beat_positions=events.beat_positions,
        onset_positions=events.onset_positions,
        duration=duration,
        F_RMS=FrameFeatureSequence.F_RMS,
        F_CENTROID=FrameFeatureSequence.F_CENTROID,
        F_FLUX=FrameFeatureSequence.F_FLUX,
    )
    windows = WindowFeatureSet(
        times_1hz=windows_dict["times_1hz"],
        stats_2s=windows_dict["stats_2s"],
        stats_4s=windows_dict["stats_4s"],
        stats_8s=windows_dict["stats_8s"],
    )
    sections = SectionFeatureSet(np.array([0.0, duration]), ["verse"], np.zeros(int(duration)), [], [], [0.5])
    semantics = SemanticControlSet(0.5, 0.5, 0.5, 0.5, 0.5, 0.5, 0.5, 0.3, 0.5, 0.5)
    globals_feat = GlobalFeatureSet.compute_defaults()

    return FeatureCache(
        metadata=meta,
        frame_seq=seq,
        events=events,
        windows=windows,
        sections=sections,
        semantics=semantics,
        globals_set=globals_feat,
    )


def test_l3_window_query_interpolation_at_fractional_time():
    """Verify FeatureCache.get_window_stats_at_time interpolates fractional timestamps smoothly."""
    cache = create_mock_v5_cache(duration=20.0)

    s4 = cache.get_window_stats_at_time(4.0, window_size=4)["energy_mean"]
    s5 = cache.get_window_stats_at_time(5.0, window_size=4)["energy_mean"]
    s4_5 = cache.get_window_stats_at_time(4.5, window_size=4)["energy_mean"]

    expected = 0.5 * s4 + 0.5 * s5
    assert abs(s4_5 - expected) < 1e-5


def test_v4_cache_version_rejection():
    """Verify v4 metadata version is distinct from current CACHE_VERSION (v5)."""
    assert CACHE_VERSION == "v5"
    meta_v4 = TrackAnalysisMetadata("old.mp3", "old_hash", "v4", 10.0, 44100, 1.0)
    assert meta_v4.cache_version != CACHE_VERSION


def test_silence_track_calibration():
    """Verify silent track returns 0.0 for normalized RMS and low excitation."""
    rms_arr = np.zeros(100, dtype=float)
    flux_arr = np.zeros(100, dtype=float)
    onset_arr = np.zeros(100, dtype=float)

    calib = TrackCalibration.compute(rms_arr, flux_arr, onset_arr)

    norm_rms = calib.normalize_rms_db(0.0)
    assert norm_rms == 0.0


def test_all_nan_flux_onset_defensiveness():
    """Verify TrackCalibration cleanly handles all-NaN flux and onset arrays without crashing."""
    rms_arr = np.ones(50, dtype=float) * 0.1
    flux_arr = np.full(50, np.nan)
    onset_arr = np.full(50, np.nan)

    calib = TrackCalibration.compute(rms_arr, flux_arr, onset_arr)
    assert calib.flux_p95 >= 1e-6
    assert calib.onset_p95 >= 1e-6


def test_non_recursive_seek_rebuild():
    """Verify Scene.seek_to does not cause recursive seek calls or stack overflow."""
    cache = create_mock_v5_cache(duration=30.0)
    bundle = build_dynamics_bundle(cache)

    scene = Scene()
    scene.load_track_features(cache.globals)
    scene.set_dynamics_bundle(bundle)

    # Seek to t = 15.0s
    scene.seek_to(15.0, width=1280, height=720)

    assert scene.time == 15.0
    assert scene.current_material_state is not None
    assert scene.current_geometry_control is not None


def test_stable_particle_ids():
    """Verify ParticleSystem assigns incrementing particle_id and resets cleanly on clear()."""
    ps = ParticleSystem()
    ps.emit(100, 100, 3, hue_base=180.0)

    assert len(ps.particles) >= 3
    assert ps.particles[0].particle_id == 0
    assert ps.particles[1].particle_id == 1
    assert ps.particles[2].particle_id == 2

    ps.clear()
    assert len(ps.particles) == 0
    assert ps.next_particle_id == 0
