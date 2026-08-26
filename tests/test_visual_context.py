import pytest
import numpy as np
from app.analysis.features import FeatureFrame, GlobalFeatureSet, FrameFeatureSequence, EventFeatureSet, FeatureCache, TrackAnalysisMetadata
from app.dynamics.context import VisualContextBuilder, VisualContext


def test_visual_context_sampling():
    times = np.linspace(0.0, 10.0, 100)
    features = np.zeros((100, FrameFeatureSequence.N_FEATURES))
    features[:, FrameFeatureSequence.F_RMS] = 0.5
    features[:, FrameFeatureSequence.F_BAND_BASS] = 0.6
    features[:, FrameFeatureSequence.F_HARMONIC_E] = 0.8
    features[:, FrameFeatureSequence.F_PERCUSSIVE_E] = 0.2
    features[:, FrameFeatureSequence.F_CHROMA_START] = 1.0  # C pitch class

    frame_seq = FrameFeatureSequence(times=times, frame_rate=10.0, features=features)
    events = EventFeatureSet(
        beat_positions=np.array([1.0, 2.0, 3.0, 4.0]),
        beat_strengths=np.array([0.8, 0.8, 0.8, 0.8]),
        beat_confidence=0.8,
        onset_positions=np.array([0.5, 1.5]),
        onset_strengths=np.array([0.5, 0.5])
    )
    metadata = TrackAnalysisMetadata(file_path="dummy.wav", file_hash="hash", duration=10.0, sample_rate=44100, cache_version="v4", analysis_timestamp=1000.0)
    cache = FeatureCache(
        metadata=metadata,
        frame_seq=frame_seq,
        events=events,
        windows=None,
        sections=None,
        semantics=None,
        globals_set=GlobalFeatureSet.compute_defaults()
    )

    builder = VisualContextBuilder(cache)
    ctx = builder.at(2.0)

    assert isinstance(ctx, VisualContext)
    assert ctx.time == 2.0
    assert 0.0 <= ctx.activity <= 1.0
    assert 0.0 <= ctx.energy_fast <= 1.0
    assert ctx.harmonic_ratio > 0.5
    assert ctx.tonal_confidence > 0.0
