import pytest
import numpy as np
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
from app.dynamics.calibration import TrackCalibration
from app.dynamics.context import VisualContextBuilder, DynamicsBundle
from app.dynamics.trajectory import MaterialTrajectoryCompiler
from app.visual.scene import Scene


def create_dummy_feature_cache(duration: float = 60.0) -> FeatureCache:
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
        beat_positions=np.array([1.0, 2.0, 3.0]),
        beat_strengths=np.array([0.8, 0.8, 0.8]),
        beat_confidence=0.8,
        onset_positions=np.array([0.5, 1.5]),
        onset_strengths=np.array([0.5, 0.5]),
    )
    meta = TrackAnalysisMetadata("dummy.mp3", "hash123", "2.0", duration, 44100, 1.0)
    windows = WindowFeatureSet(np.arange(int(duration)), {}, {}, {})
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


def test_v2_runtime_pipeline_end_to_end():
    """Verify that Scene uses V2 DynamicsBundle, MaterialState, and AnalyticalPESField."""
    cache = create_dummy_feature_cache(duration=30.0)

    calib = TrackCalibration.compute(
        rms_arr=cache.frame_seq.features[:, cache.frame_seq.F_RMS],
        flux_arr=cache.frame_seq.features[:, cache.frame_seq.F_FLUX],
        onset_arr=cache.frame_seq.features[:, cache.frame_seq.F_ONSET_STR],
    )
    ctx_builder = VisualContextBuilder(cache, calib)
    mat_traj = MaterialTrajectoryCompiler.compile(ctx_builder, cache.duration, simulation_hz=60.0)
    bundle = DynamicsBundle(
        calibration=calib,
        context_builder=ctx_builder,
        material_trajectory=mat_traj,
        track_seed=42,
    )

    scene = Scene()
    scene.load_track_features(cache.globals)
    scene.set_dynamics_bundle(bundle)

    # Execute frame update at t = 5.0
    frame = cache.get_frame_at_time(5.0)
    scene.update(frame, is_playing=True, width=1920, height=1080, dt=0.016)

    assert scene.current_material_state is not None
    assert scene.current_context is not None
    assert scene.current_material_state.order > 0.0
    assert scene.analytical_field.potential_gain >= 0.0


def test_legacy_phase_engine_not_called_in_v2():
    """Verify that legacy PhaseEngine raises if called, but Scene update succeeds via V2."""
    cache = create_dummy_feature_cache(duration=30.0)
    calib = TrackCalibration.compute(
        rms_arr=cache.frame_seq.features[:, cache.frame_seq.F_RMS],
        flux_arr=cache.frame_seq.features[:, cache.frame_seq.F_FLUX],
        onset_arr=cache.frame_seq.features[:, cache.frame_seq.F_ONSET_STR],
    )
    ctx_builder = VisualContextBuilder(cache, calib)
    mat_traj = MaterialTrajectoryCompiler.compile(ctx_builder, cache.duration, simulation_hz=60.0)
    bundle = DynamicsBundle(
        calibration=calib,
        context_builder=ctx_builder,
        material_trajectory=mat_traj,
        track_seed=42,
    )

    scene = Scene()
    scene.load_track_features(cache.globals)
    scene.set_dynamics_bundle(bundle)

    # Monkeypatch legacy PhaseEngine to raise error
    def legacy_raise(*args, **kwargs):
        raise RuntimeError("Legacy PhaseEngine should not be called under V2!")

    scene.phase_engine.update = legacy_raise

    frame = cache.get_frame_at_time(10.0)
    # Must update cleanly without triggering legacy_raise
    scene.update(frame, is_playing=True, width=1920, height=1080, dt=0.016)
    assert scene.current_material_state is not None


def test_seek_equivalence():
    """Verify Scene.seek_to(t) fetches the exact precompiled MaterialState at timestamp t."""
    cache = create_dummy_feature_cache(duration=30.0)
    calib = TrackCalibration.compute(
        rms_arr=cache.frame_seq.features[:, cache.frame_seq.F_RMS],
        flux_arr=cache.frame_seq.features[:, cache.frame_seq.F_FLUX],
        onset_arr=cache.frame_seq.features[:, cache.frame_seq.F_ONSET_STR],
    )
    ctx_builder = VisualContextBuilder(cache, calib)
    mat_traj = MaterialTrajectoryCompiler.compile(ctx_builder, cache.duration, simulation_hz=60.0)
    bundle = DynamicsBundle(
        calibration=calib,
        context_builder=ctx_builder,
        material_trajectory=mat_traj,
        track_seed=42,
    )

    scene = Scene()
    scene.set_dynamics_bundle(bundle)

    seek_time = 15.0
    scene.seek_to(seek_time)

    expected_state = mat_traj.get_state_at_time(seek_time)
    assert scene.current_material_state == expected_state
