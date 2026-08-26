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
from app.analysis.window import compute_window_features
from app.dynamics.context import build_dynamics_bundle
from app.visual.scene import Scene


def create_smoke_feature_cache(duration: float = 10.0) -> FeatureCache:
    fps = 50.0
    n_frames = int(duration * fps)
    times = np.linspace(0, duration, n_frames)

    feats = np.zeros((n_frames, FrameFeatureSequence.N_FEATURES), dtype=float)
    feats[:, FrameFeatureSequence.F_RMS] = 0.3
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
        beat_positions=np.array([1.0, 2.0, 3.0]),
        beat_strengths=np.array([0.8, 0.8, 0.8]),
        beat_confidence=0.8,
        onset_positions=np.array([0.5, 1.5]),
        onset_strengths=np.array([0.5, 0.5]),
    )
    meta = TrackAnalysisMetadata("smoke.mp3", "smoke_hash_123", "v5", duration, 44100, 1.0)
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


def test_v2_scene_one_frame_smoke():
    """Verify Scene updates clean without exception when given a V2 DynamicsBundle."""
    cache = create_smoke_feature_cache()
    bundle = build_dynamics_bundle(cache)

    scene = Scene()
    scene.load_track_features(cache.globals)
    scene.set_dynamics_bundle(bundle)

    frame = cache.get_frame_at_time(2.0)
    scene.update(frame, is_playing=True, width=1920, height=1080, dt=0.016)

    assert scene.current_material_state is not None
    assert scene.current_geometry_control is not None
    assert scene.current_context is not None
