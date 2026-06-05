"""Analysis package - audio feature extraction and caching."""
from .features import (
    FeatureCache, TrackAnalysisMetadata, FrameFeatureSequence, 
    EventFeatureSet, WindowFeatureSet, SectionFeatureSet, 
    SemanticControlSet, GlobalFeatureSet, FeatureFrame
)
from .extractor import FeatureExtractor
from .cache import FeatureCacheManager
from .sync import VisualizationSync
from .beat import detect_beats, estimate_tempo, compute_beat_regularity
from .spectrum import (
    compute_rms,
    compute_spectral_centroid,
    compute_spectral_rolloff,
    compute_onset_strength,
    compute_band_energies_6,
    compute_spectral_flatness,
    get_frequency_array,
)
from .window import compute_window_features
from .section import extract_sections
