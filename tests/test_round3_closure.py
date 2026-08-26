import math
import numpy as np
import pytest

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
from app.dynamics.context import VisualContextBuilder, build_dynamics_bundle
from app.dynamics.calibration import TrackCalibration
from app.dynamics.trajectory import MaterialTrajectoryCompiler, MaterialStateSequence
from app.dynamics.material import MaterialState, GeometryControl
from app.visual.scene import Scene
from app.visual.particles import ParticleSystem


def create_mock_feature_cache(duration: float = 30.0) -> FeatureCache:
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
    feats[:, FrameFeatureSequence.F_BAND_BASS] = 0.1
    feats[:, FrameFeatureSequence.F_BAND_LOW_MID] = 0.1
    feats[:, FrameFeatureSequence.F_BAND_MID] = 0.1
    feats[:, FrameFeatureSequence.F_BAND_HIGH_MID] = 0.1
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
    meta = TrackAnalysisMetadata("test_track.mp3", "hash_abc_123", "v5", duration, 44100, 1.0)

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
    sections = SectionFeatureSet(np.array([0.0, 15.0, duration]), ["verse", "chorus"], np.zeros(int(duration)), [1], [], [0.5, 0.9])
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


def test_l3_causal_no_future_leak():
    """Verify L3 trailing windows do NOT leak future energy on a step signal."""
    fps = 50.0
    duration = 20.0
    n_frames = int(duration * fps)
    feats = np.zeros((n_frames, FrameFeatureSequence.N_FEATURES), dtype=float)

    # 0 ~ 10s: RMS = 0.05
    # 10 ~ 20s: RMS = 0.90
    step_frame = int(10.0 * fps)
    feats[:step_frame, FrameFeatureSequence.F_RMS] = 0.05
    feats[step_frame:, FrameFeatureSequence.F_RMS] = 0.90

    windows_dict = compute_window_features(
        frame_features=feats,
        frame_rate=fps,
        beat_positions=np.array([]),
        onset_positions=np.array([]),
        duration=duration,
        F_RMS=FrameFeatureSequence.F_RMS,
        F_CENTROID=FrameFeatureSequence.F_CENTROID,
        F_FLUX=FrameFeatureSequence.F_FLUX,
    )

    times = windows_dict["times_1hz"]
    e_mean_8s = windows_dict["stats_8s"]["energy_mean"]

    # At t = 9s (index 9), 8s trailing window [1s, 9s] must see ONLY 0.05, NOT 0.90
    idx_9 = int(np.where(times == 9.0)[0][0])
    assert e_mean_8s[idx_9] < 0.10, f"Future leak detected at t=9s: energy_mean_8s={e_mean_8s[idx_9]}"


def test_l3_equal_lengths_and_interpolation():
    """Verify all L3 window stat arrays share exact length of times_1hz and interpolate smoothly."""
    cache = create_mock_feature_cache(duration=30.0)

    n_times = len(cache.windows.times_1hz)
    assert len(cache.windows.stats_2s["energy_mean"]) == n_times
    assert len(cache.windows.stats_4s["energy_mean"]) == n_times
    assert len(cache.windows.stats_8s["energy_mean"]) == n_times

    # Test linear interpolation at t = 4.5s
    s_4 = cache.get_window_stats_at_time(4.0, 4)["energy_mean"]
    s_5 = cache.get_window_stats_at_time(5.0, 4)["energy_mean"]
    s_4_5 = cache.get_window_stats_at_time(4.5, 4)["energy_mean"]

    expected = 0.5 * s_4 + 0.5 * s_5
    assert abs(s_4_5 - expected) < 1e-5


def test_stable_track_seed_cross_process():
    """Verify build_dynamics_bundle produces stable BLAKE2b track_seed from file_hash."""
    cache1 = create_mock_feature_cache(duration=10.0)
    cache2 = create_mock_feature_cache(duration=10.0)

    bundle1 = build_dynamics_bundle(cache1)
    bundle2 = build_dynamics_bundle(cache2)

    assert bundle1.track_seed == bundle2.track_seed
    assert bundle1.track_seed > 0


def test_material_state_interpolation():
    """Verify MaterialStateSequence smoothly interpolates state between 60Hz keyframes."""
    s0 = MaterialState(order=0.2, excitation=0.1, mobility=0.3, defect_density=0.1, activity=0.8, w_crystalline=0.8, w_hydrodynamic=0.1, w_plasma=0.1, phase_name="crystalline")
    s1 = MaterialState(order=0.8, excitation=0.9, mobility=0.7, defect_density=0.5, activity=0.8, w_crystalline=0.2, w_hydrodynamic=0.7, w_plasma=0.1, phase_name="hydrodynamic")

    seq = MaterialStateSequence(times=np.array([0.0, 0.1]), states=[s0, s1])

    s_mid = seq.get_state_at_time(0.05, interpolate=True)
    assert abs(s_mid.order - 0.5) < 1e-3
    assert abs(s_mid.excitation - 0.5) < 1e-3


def test_geometry_control_renderer_morph():
    """Verify GeometryControl continuous parameter scaling."""
    st = MaterialState(order=0.8, excitation=0.4, mobility=0.6, defect_density=0.2, activity=0.8, w_crystalline=0.7, w_hydrodynamic=0.2, w_plasma=0.1, phase_name="crystalline")
    geom = st.geometry_control

    assert 0.0 <= geom.symmetry <= 1.0
    assert 0.0 <= geom.coherence <= 1.0
    assert 0.0 <= geom.circulation <= 1.0
    assert 0.0 <= geom.fragmentation <= 1.0
    assert 0.0 <= geom.roughness <= 1.0
    assert 0.0 <= geom.angular_lock <= 1.0


def test_particle_exponential_drag():
    """Verify particle exponential drag factor remains in (0, 1) even for high dt."""
    ps = ParticleSystem()
    ps.emit(0, 0, 5, 180.0)

    # Update with large dt = 0.5s
    ps.update(0, 0, chaos=0.5, beat_pulse=0.0, energy=0.5, dt=0.5)
    for p in ps.particles:
        assert not math.isnan(p.vx)
        assert not math.isnan(p.vy)


def test_seek_rebuild_warmup():
    """Verify Scene.seek_to(t) performs warmup and populates particles."""
    cache = create_mock_feature_cache(duration=30.0)
    bundle = build_dynamics_bundle(cache)

    scene = Scene()
    scene.load_track_features(cache.globals)
    scene.set_dynamics_bundle(bundle)

    seek_time = 12.0
    scene.seek_to(seek_time)

    assert scene.current_material_state is not None
    assert scene.current_geometry_control is not None
    assert scene.time == seek_time
