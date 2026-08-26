"""
Visual Context Engine.
Translates multi-level audio features into clean, normalized, semantic VisualContext signals.
"""
from __future__ import annotations

import math
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


@dataclass
class DynamicsBundle:
    """Unified container for full-track dynamics components."""

    calibration: TrackCalibration
    context_builder: VisualContextBuilder
    material_trajectory: "MaterialStateSequence"
    track_seed: int


class VisualContextBuilder:
    """Builds linearly interpolated VisualContext for any given time t."""

    def __init__(self, feature_cache, calibration: Optional[TrackCalibration] = None):
        self.cache = feature_cache
        self.frame_seq = feature_cache.frame_seq
        self.events = feature_cache.events
        self.globals = feature_cache.globals
        self.windows = getattr(feature_cache, "windows", None)
        self.sections = getattr(feature_cache, "sections", None)

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
        duration = self.cache.duration if hasattr(self.cache, "duration") and self.cache.duration > 0 else 100.0
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

        # L3 Window Stats (Causal Trailing Windows via Interpolation)
        stats4 = self.cache.get_window_stats_at_time(time, 4) if hasattr(self.cache, "get_window_stats_at_time") else {}
        stats2 = self.cache.get_window_stats_at_time(time, 2) if hasattr(self.cache, "get_window_stats_at_time") else {}

        if "energy_mean" in stats4:
            energy_slow = self.calibration.normalize_rms_db(stats4["energy_mean"])
        else:
            energy_slow = energy_fast * 0.8

        if "energy_trend" in stats4:
            energy_trend = _clamp(stats4["energy_trend"] * 2.0, -1.0, 1.0)
        else:
            energy_trend = 0.0

        if "transient_density" in stats4:
            t_d2 = stats2.get("transient_density", stats4["transient_density"])
            t_d4 = stats4["transient_density"]
            transient_density = _clamp(0.6 * t_d2 + 0.4 * t_d4, 0.0, 1.0)
        else:
            transient_density = _clamp(onset_norm * 0.8, 0.0, 1.0)

        # Rhythm Events (Strictly Causal - Most recent past beat decay)
        beat_impulse = 0.0
        if len(self.events.beat_positions) > 0:
            past_indices = np.where(self.events.beat_positions <= time)[0]
            if len(past_indices) > 0:
                last_idx = past_indices[-1]
                t_b = float(self.events.beat_positions[last_idx])
                b_str = float(self.events.beat_strengths[last_idx]) if len(self.events.beat_strengths) > last_idx else 0.8
                elapsed = time - t_b
                if elapsed <= 0.35:
                    beat_impulse = _clamp(b_str * math.exp(-elapsed / 0.15), 0.0, 1.0)

        beat_conf = getattr(self.events, "beat_confidence", 0.5) if len(self.events.beat_positions) >= 3 else 0.0

        if "beat_density" in stats4:
            b_d4 = stats4["beat_density"]
            beat_density = _clamp(b_d4 * (0.5 + 0.5 * beat_conf), 0.0, 1.0)
        else:
            beat_density = _clamp(beat_impulse * beat_conf, 0.0, 1.0)

        # Spectrum
        bass_d = frame_dict["bass"]
        mid_d = (frame_dict["low_mid"] + frame_dict["mid"] + frame_dict["high_mid"]) / 3.0
        high_d = (frame_dict["high"] + frame_dict["presence"]) / 2.0

        brightness = _clamp(frame_dict["centroid"], 0.0, 1.0)
        noise = _clamp(frame_dict["flatness"], 0.0, 1.0)

        if "band_shares" in frame_dict and frame_dict["band_shares"] is not None and len(frame_dict["band_shares"]) == 6:
            b_shares = frame_dict["band_shares"]
            weights = np.array([0.0, 1.0, 2.0, 3.0, 4.0, 5.0])
            tilt = _clamp(float(np.sum(weights * b_shares)) / 5.0, 0.0, 1.0)
        else:
            tilt = _clamp(high_d / (bass_d + high_d + 1e-5), 0.0, 1.0)

        # Tonal Structure
        harm_e = frame_dict["harmonic_e"]
        perc_e = frame_dict["percussive_e"]
        tot_e = max(1e-5, harm_e + perc_e)
        harm_ratio = _clamp(harm_e / tot_e, 0.0, 1.0)

        chroma = frame_dict.get("chroma", np.zeros(12))
        chroma_sum = float(np.sum(chroma))
        if chroma_sum > 1e-5 and not math.isnan(chroma_sum):
            p_chroma = chroma / chroma_sum
            entropy = -float(np.sum(p_chroma * np.log(p_chroma + 1e-12)))
            if math.isnan(entropy):
                tonal_conf = 0.0
            else:
                tonal_conf = _clamp((1.0 - (entropy / math.log(12.0))) * harm_ratio * activity, 0.0, 1.0)
        else:
            tonal_conf = 0.0

        # L4 Section Boundaries & Real Causal Section Progress
        sec_progress = _clamp(time / max(1.0, duration), 0.0, 1.0)
        novelty_val = 0.0
        boundary_impulse = 0.0
        climax_prior = self.globals.energy if self.globals else 0.5

        if self.sections is not None and hasattr(self.sections, "boundaries") and len(self.sections.boundaries) > 0:
            bounds = self.sections.boundaries
            sec_idx = int(np.searchsorted(bounds, time, side="right")) - 1
            sec_start = float(bounds[sec_idx]) if sec_idx >= 0 else 0.0
            sec_end = float(bounds[sec_idx + 1]) if sec_idx + 1 < len(bounds) else duration
            sec_progress = _clamp((time - sec_start) / max(0.1, sec_end - sec_start), 0.0, 1.0)

            # Strictly causal boundary impulse (decays after boundary start)
            elapsed = max(0.0, time - sec_start)
            boundary_impulse = float(math.exp(-elapsed / 0.45))

            if hasattr(self.sections, "novelty_curve") and len(self.sections.novelty_curve) > 0:
                n_idx = int(np.clip(time * (len(self.sections.novelty_curve) / duration), 0, len(self.sections.novelty_curve) - 1))
                novelty_val = float(self.sections.novelty_curve[n_idx])

            if hasattr(self.sections, "climax_candidates") and sec_idx in self.sections.climax_candidates:
                climax_prior = min(1.0, climax_prior + 0.3)

        return VisualContext(
            time=time,
            activity=activity,
            energy_fast=energy_fast,
            energy_slow=energy_slow,
            energy_trend=energy_trend,
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
            transient_density=transient_density,
            beat_density=beat_density,
            harmonic_ratio=harm_ratio,
            tonal_confidence=tonal_conf,
            chroma=chroma,
            novelty=novelty_val,
            boundary_impulse=boundary_impulse,
            climax_prior=climax_prior,
            section_progress=sec_progress,
        )


def build_dynamics_bundle(
    feature_cache,
    simulation_hz: float = 60.0,
) -> DynamicsBundle:
    """
    Centralized factory for creating full-track DynamicsBundle.
    Generates stable cross-process track_seed using BLAKE2b digest on metadata.file_hash.
    """
    import hashlib
    from .trajectory import MaterialTrajectoryCompiler

    file_hash = getattr(feature_cache.metadata, "file_hash", "default_hash")
    digest = hashlib.blake2b(file_hash.encode("utf-8"), digest_size=8).digest()
    track_seed = int.from_bytes(digest, "little")

    rms_arr = feature_cache.frame_seq.features[:, feature_cache.frame_seq.F_RMS]
    flx_arr = feature_cache.frame_seq.features[:, feature_cache.frame_seq.F_FLUX]
    ons_arr = feature_cache.frame_seq.features[:, feature_cache.frame_seq.F_ONSET_STR]

    calibration = TrackCalibration.compute(rms_arr, flx_arr, ons_arr)
    ctx_builder = VisualContextBuilder(feature_cache, calibration)
    mat_traj = MaterialTrajectoryCompiler.compile(
        ctx_builder,
        feature_cache.duration,
        simulation_hz=simulation_hz,
    )

    return DynamicsBundle(
        calibration=calibration,
        context_builder=ctx_builder,
        material_trajectory=mat_traj,
        track_seed=track_seed,
    )
