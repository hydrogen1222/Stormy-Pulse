"""
Visual Context Engine.
Translates multi-level audio features into clean, normalized, semantic VisualContext signals.
"""
from __future__ import annotations

from dataclasses import dataclass
import numpy as np
from typing import Optional, Dict

from .calibration import TrackCalibration


def _clamp(v: float, low: float = 0.0, high: float = 1.0) -> float:
    return max(low, min(high, float(v)))


@dataclass(frozen=True)
class VisualContext:
    """Normalized, semantic visual input snapshot at time t."""

    time: float

    # Activity & Energy
    activity: float
    energy_fast: float
    energy_slow: float
    energy_trend: float

    # Spectral Balance
    bass_drive: float
    mid_drive: float
    high_drive: float
    spectral_brightness: float
    spectral_noise: float
    spectral_tilt: float

    # Rhythm & Transients
    onset: float
    flux: float
    beat_impulse: float
    beat_confidence: float
    transient_density: float
    beat_density: float

    # Tonal & Harmonic Structure
    harmonic_ratio: float
    tonal_confidence: float
    chroma: np.ndarray

    # Structural Macro Context
    novelty: float
    boundary_impulse: float
    climax_prior: float
    section_progress: float


class VisualContextBuilder:
    """Builds linearly interpolated VisualContext for any given time t."""

    def __init__(self, feature_cache, calibration: Optional[TrackCalibration] = None):
        self.cache = feature_cache
        self.frame_seq = feature_cache.frame_seq
        self.events = feature_cache.events
        self.globals = feature_cache.globals

        if calibration is not None:
            self.calibration = calibration
        else:
            rms_arr = self.frame_seq.features[:, self.frame_seq.F_RMS]
            flx_arr = self.frame_seq.features[:, self.frame_seq.F_FLUX]
            ons_arr = self.frame_seq.features[:, self.frame_seq.F_ONSET_STR]
            self.calibration = TrackCalibration.compute(rms_arr, flx_arr, ons_arr)

    def at(self, time: float) -> VisualContext:
        """Sample or interpolate VisualContext snapshot at exact timestamp."""
        time = max(0.0, float(time))
        frame_dict = self.frame_seq.get_frame_dict_at_time(time)

        if frame_dict is None:
            # Fallback for silent out-of-bounds
            return VisualContext(
                time=time,
                activity=0.0, energy_fast=0.0, energy_slow=0.0, energy_trend=0.0,
                bass_drive=0.0, mid_drive=0.0, high_drive=0.0,
                spectral_brightness=0.0, spectral_noise=0.0, spectral_tilt=0.5,
                onset=0.0, flux=0.0, beat_impulse=0.0, beat_confidence=0.0,
                transient_density=0.0, beat_density=0.0,
                harmonic_ratio=0.5, tonal_confidence=0.0,
                chroma=np.zeros(12),
                novelty=0.0, boundary_impulse=0.0, climax_prior=0.0, section_progress=0.0,
            )

        raw_rms = frame_dict["rms"]
        energy_fast = self.calibration.normalize_rms_db(raw_rms)
        raw_flux = frame_dict["flux"]
        flux_norm = self.calibration.normalize_flux(raw_flux)
        raw_onset = frame_dict["onset_strength"]
        onset_norm = self.calibration.normalize_onset(raw_onset)

        # Activity Gate
        activity = _clamp(energy_fast * 1.6 + onset_norm * 0.4, 0.0, 1.0)

        # Spectrum
        bass_d = frame_dict["bass"]
        mid_d = (frame_dict["low_mid"] + frame_dict["mid"] + frame_dict["high_mid"]) / 3.0
        high_d = (frame_dict["high"] + frame_dict["presence"]) / 2.0

        brightness = _clamp(frame_dict["centroid"], 0.0, 1.0)
        noise = _clamp(frame_dict["flatness"], 0.0, 1.0)
        tilt = _clamp(high_d / (bass_d + high_d + 1e-5), 0.0, 1.0)

        # Rhythm Events
        ev = self.events.get_events_near(time, window=0.08)
        beat_impulse = ev["beat"]
        beat_conf = getattr(self.events, "beat_confidence", 0.5) if len(self.events.beat_positions) >= 3 else 0.0

        # Tonal Structure
        harm_e = frame_dict["harmonic_e"]
        perc_e = frame_dict["percussive_e"]
        tot_e = max(1e-5, harm_e + perc_e)
        harm_ratio = _clamp(harm_e / tot_e, 0.0, 1.0)

        chroma = frame_dict.get("chroma", np.zeros(12))
        chroma_sum = float(np.sum(chroma))
        if chroma_sum > 1e-5:
            p_chroma = chroma / chroma_sum
            entropy = -float(np.sum(p_chroma * np.log(p_chroma + 1e-12)))
            tonal_conf = _clamp((1.0 - (entropy / np.log(12.0))) * harm_ratio * activity, 0.0, 1.0)
        else:
            tonal_conf = 0.0

        # Macro section progress
        duration = self.cache.duration if hasattr(self.cache, "duration") else 100.0
        sec_progress = _clamp(time / max(1.0, duration), 0.0, 1.0)

        return VisualContext(
            time=time,
            activity=activity,
            energy_fast=energy_fast,
            energy_slow=energy_fast * 0.8,
            energy_trend=0.0,
            bass_drive=bass_d,
            mid_drive=mid_d,
            high_drive=high_d,
            spectral_brightness=brightness,
            spectral_noise=noise,
            spectral_tilt=tilt,
            onset=onset_norm,
            flux=flux_norm,
            beat_impulse=beat_impulse,
            beat_confidence=beat_conf,
            transient_density=onset_norm * 0.8,
            beat_density=beat_impulse * beat_conf,
            harmonic_ratio=harm_ratio,
            tonal_confidence=tonal_conf,
            chroma=chroma,
            novelty=0.0,
            boundary_impulse=0.0,
            climax_prior=self.globals.energy if self.globals else 0.5,
            section_progress=sec_progress,
        )
