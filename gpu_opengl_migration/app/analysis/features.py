"""
Audio feature data structures for multi-level analysis.
"""
import numpy as np
from dataclasses import dataclass, field
from typing import Optional, List, Dict, Any


@dataclass
class TrackAnalysisMetadata:
    """Level 0: Metadata about the analysis itself."""
    file_path: str
    file_hash: str
    cache_version: str
    duration: float
    sample_rate: int
    analysis_timestamp: float


@dataclass
class FeatureFrame:
    """Legacy/Compat frame representation."""
    time: float
    rms: float
    bass: float
    mid: float
    high: float
    onset_strength: float
    spectral_centroid: float
    spectral_rolloff: float
    spectral_flatness: float
    beat: float
    beat_strength: float


@dataclass
class FrameFeatureSequence:
    """Level 1: Frame-level features (continuous timeseries)."""
    times: np.ndarray
    frame_rate: float
    features: np.ndarray  # Shape: (n_frames, N_FEATURES)

    # Feature indices
    F_RMS = 0
    F_PEAK = 1
    F_LOUDNESS = 2
    F_BAND_BASS = 3       # 0-250 Hz
    F_BAND_LOW_MID = 4    # 250-500 Hz
    F_BAND_MID = 5        # 500-2000 Hz
    F_BAND_HIGH_MID = 6   # 2000-4000 Hz
    F_BAND_HIGH = 7       # 4000-8000 Hz
    F_BAND_PRESENCE = 8   # 8000+ Hz
    F_CENTROID = 9
    F_ROLLOFF = 10
    F_BANDWIDTH = 11
    F_FLATNESS = 12
    F_FLUX = 13
    F_ONSET_STR = 14
    F_ZCR = 15
    F_HARMONIC_E = 16
    F_PERCUSSIVE_E = 17
    F_CHROMA_START = 18    # 18-29: 12 Chroma bins
    N_FEATURES = 30

    def get_frame_dict_at_time(self, time: float) -> Optional[Dict[str, float]]:
        if time < 0 or len(self.times) == 0 or time > self.times[-1]:
            return None

        # Nearest neighbor or linear interpolation
        frame_idx = time * self.frame_rate
        idx0 = int(frame_idx)
        idx1 = min(idx0 + 1, len(self.features) - 1)
        t = frame_idx - idx0
        
        if idx0 >= len(self.features):
            idx0 = len(self.features) - 1
            idx1 = idx0
            
        data = self.features[idx0] * (1 - t) + self.features[idx1] * t
        # Max for transient
        data[self.F_ONSET_STR] = max(self.features[idx0, self.F_ONSET_STR], self.features[idx1, self.F_ONSET_STR])
        
        return {
            "rms": data[self.F_RMS],
            "peak": data[self.F_PEAK],
            "loudness": data[self.F_LOUDNESS],
            "bass": data[self.F_BAND_BASS],
            "low_mid": data[self.F_BAND_LOW_MID],
            "mid": data[self.F_BAND_MID],
            "high_mid": data[self.F_BAND_HIGH_MID],
            "high": data[self.F_BAND_HIGH],
            "presence": data[self.F_BAND_PRESENCE],
            "centroid": data[self.F_CENTROID],
            "rolloff": data[self.F_ROLLOFF],
            "bandwidth": data[self.F_BANDWIDTH],
            "flatness": data[self.F_FLATNESS],
            "flux": data[self.F_FLUX],
            "onset_strength": data[self.F_ONSET_STR],
            "zcr": data[self.F_ZCR],
            "harmonic_e": data[self.F_HARMONIC_E],
            "percussive_e": data[self.F_PERCUSSIVE_E]
        }


@dataclass
class EventFeatureSet:
    """Level 2: Event-level features (discrete points)."""
    beat_positions: np.ndarray
    beat_strengths: np.ndarray
    beat_confidence: float
    onset_positions: np.ndarray
    onset_strengths: np.ndarray
    downbeat_positions: np.ndarray = field(default_factory=lambda: np.array([])) # Placeholder
    
    def get_events_near(self, time: float, window: float = 0.05) -> Dict[str, float]:
        """Get events close to a specific time, returning their strengths."""
        beat_str = 0.0
        onset_str = 0.0
        
        # Binary search could be faster, but array is small enough
        beat_idx = np.where(np.abs(self.beat_positions - time) <= window)[0]
        if len(beat_idx) > 0:
            beat_str = np.max(self.beat_strengths[beat_idx])
            
        onset_idx = np.where(np.abs(self.onset_positions - time) <= window)[0]
        if len(onset_idx) > 0:
            onset_str = np.max(self.onset_strengths[onset_idx])
            
        return {"beat": beat_str, "onset": onset_str}


@dataclass
class WindowFeatureSet:
    """Level 3: Window-level features (rolling stats)."""
    times_1hz: np.ndarray  # 1 sample per second
    
    # We store them as dicts mapped from window sizes
    # e.g., stats_2s["energy_mean"]
    stats_2s: Dict[str, np.ndarray]
    stats_4s: Dict[str, np.ndarray]
    stats_8s: Dict[str, np.ndarray]


@dataclass
class SectionFeatureSet:
    """Level 4: Section-level features (song structure)."""
    boundaries: np.ndarray
    labels: List[str]
    novelty_curve: np.ndarray
    climax_candidates: List[int]
    repeated_section_candidates: List[tuple]
    section_energy_summary: List[float]


@dataclass
class SemanticControlSet:
    """Level 5a: High-level semantic abstractions."""
    impact: float
    pressure: float
    sparkle: float
    density: float
    tension: float
    warmth: float
    flow: float
    chaos: float
    lift: float
    climax_score: float


@dataclass
class GlobalFeatureSet:
    """Level 5b: Global attributes (song identity)."""
    tempo: float
    tempo_stability: float
    beat_regularity: float
    dynamic_range: float
    energy: float
    brightness: float
    warmth: float
    darkness: float
    chaos: float
    density: float
    bass_ratio: float
    mid_ratio: float
    high_ratio: float
    harmonicity_proxy: float
    percussiveness_proxy: float
    
    palette_prior: str
    structure_prior: str
    motion_prior: str
    
    # Compat properties for theme generation
    theme_hue_base: float
    theme_saturation: float
    theme_brightness: float
    particle_density: float
    ring_count: int
    line_thickness: float
    mood: str
    structure_type: str
    detail_style: str
    motion_性格: str
    palette_type: str
    
    chroma_vector: np.ndarray = field(default_factory=lambda: np.zeros(12))
    spectral_contrast: float = 0.5

    @classmethod
    def compute_defaults(cls) -> "GlobalFeatureSet":
        """Return default global features for compat."""
        return cls(
            tempo=120.0, tempo_stability=0.5, beat_regularity=0.5,
            dynamic_range=0.5, energy=0.5, brightness=0.5, warmth=0.5, darkness=0.5,
            chaos=0.3, density=0.5, bass_ratio=0.33, mid_ratio=0.34, high_ratio=0.33,
            harmonicity_proxy=0.5, percussiveness_proxy=0.5,
            palette_prior="analogous", structure_prior="reactor", motion_prior="steady",
            theme_hue_base=200.0, theme_saturation=0.6, theme_brightness=0.7,
            particle_density=0.5, ring_count=5, line_thickness=2.0,
            mood="chill", structure_type="reactor", detail_style="glow", motion_性格="steady", palette_type="triadic",
            chroma_vector=np.zeros(12), spectral_contrast=0.5
        )


class FeatureCache:
    """The unified container for all 5 levels of features."""

    def __init__(
        self,
        metadata: TrackAnalysisMetadata,
        frame_seq: FrameFeatureSequence,
        events: EventFeatureSet,
        windows: WindowFeatureSet,
        sections: SectionFeatureSet,
        semantics: SemanticControlSet,
        globals_set: GlobalFeatureSet
    ):
        self.metadata = metadata
        self.frame_seq = frame_seq
        self.events = events
        self.windows = windows
        self.sections = sections
        self.semantics = semantics
        self.globals = globals_set

    # ---------------------------------------------------------
    # Backward compatibility properties & methods for Scene/UI
    # ---------------------------------------------------------
    @property
    def duration(self): return self.metadata.duration
    
    @property
    def frame_rate(self): return self.frame_seq.frame_rate
    
    @property
    def global_features(self): return self.globals
    
    @property
    def beat_positions(self): return self.events.beat_positions

    def get_frame_at_time(self, time: float) -> Optional[FeatureFrame]:
        """Provides the backward-compatible FeatureFrame."""
        frame_dict = self.frame_seq.get_frame_dict_at_time(time)
        if not frame_dict: return None
        
        # Get events
        ev = self.events.get_events_near(time, window=0.08) # 80ms window for visual hit
        
        # Combine the 6 bands into the compat 3 bands
        compat_bass = frame_dict["bass"]
        compat_mid = (frame_dict["low_mid"] + frame_dict["mid"] + frame_dict["high_mid"]) / 3.0
        compat_high = (frame_dict["high"] + frame_dict["presence"]) / 2.0
        
        return FeatureFrame(
            time=time,
            rms=frame_dict["rms"],
            bass=compat_bass,
            mid=compat_mid,
            high=compat_high,
            onset_strength=max(frame_dict["onset_strength"], ev["onset"]),
            spectral_centroid=frame_dict["centroid"],
            spectral_rolloff=frame_dict["rolloff"],
            spectral_flatness=frame_dict["flatness"],
            beat=1.0 if ev["beat"] > 0 else 0.0,
            beat_strength=ev["beat"]
        )

    def get_window_stats_at_time(self, time: float, window_size: int = 4) -> Dict[str, float]:
        """Returns the rolling stats for the given time."""
        idx = int(np.clip(time, 0, len(self.windows.times_1hz) - 1))
        
        stats_dict = {}
        if window_size == 2: source = self.windows.stats_2s
        elif window_size == 8: source = self.windows.stats_8s
        else: source = self.windows.stats_4s
            
        for k, v in source.items():
            if idx < len(v):
                stats_dict[k] = float(v[idx])
            else:
                stats_dict[k] = 0.0
                
        return stats_dict
