"""
Track Calibration & Percentile Normalization.
Provides robust P10/P95 percentile normalization and dB-scale RMS conversion.
"""
from __future__ import annotations

from dataclasses import dataclass
import numpy as np


@dataclass(frozen=True)
class TrackCalibration:
    """Robust scaling percentile limits computed across a full track."""

    rms_reference: float
    rms_db_p10: float
    rms_db_p95: float
    flux_p95: float
    onset_p95: float
    contrast_low: float
    contrast_high: float

    @classmethod
    def compute(
        cls,
        rms_arr: np.ndarray,
        flux_arr: np.ndarray,
        onset_arr: np.ndarray,
        contrast_arr: np.ndarray | None = None,
    ) -> TrackCalibration:
        """Compute robust track calibration percentiles."""
        eps = 1e-6

        # Convert RMS to dB relative to track max reference
        valid_rms = np.maximum(0.0, rms_arr[~np.isnan(rms_arr)]) if len(rms_arr) > 0 else np.array([1.0])
        max_rms = max(eps, float(np.max(valid_rms))) if len(valid_rms) > 0 else 1.0
        rms_db = 20.0 * np.log10((valid_rms + eps) / (max_rms + eps))

        rms_p10 = float(np.percentile(rms_db, 10)) if len(rms_db) > 0 else -40.0
        rms_p95 = float(np.percentile(rms_db, 95)) if len(rms_db) > 0 else 0.0

        flx_p95 = max(eps, float(np.percentile(flux_arr[~np.isnan(flux_arr)], 95))) if len(flux_arr) > 0 else 1.0
        ons_p95 = max(eps, float(np.percentile(onset_arr[~np.isnan(onset_arr)], 95))) if len(onset_arr) > 0 else 1.0

        if contrast_arr is not None and len(contrast_arr) > 0:
            c_valid = contrast_arr[~np.isnan(contrast_arr)]
            c_low = float(np.percentile(c_valid, 10)) if len(c_valid) > 0 else 10.0
            c_high = max(c_low + eps, float(np.percentile(c_valid, 95))) if len(c_valid) > 0 else 35.0
        else:
            c_low, c_high = 10.0, 35.0

        return cls(
            rms_reference=max_rms,
            rms_db_p10=rms_p10,
            rms_db_p95=rms_p95,
            flux_p95=flx_p95,
            onset_p95=ons_p95,
            contrast_low=c_low,
            contrast_high=c_high,
        )

    def normalize_rms_db(self, rms_val: float, max_rms: float | None = None) -> float:
        """Map raw RMS to [0, 1] via dB space P10/P95 scaling relative to rms_reference."""
        eps = 1e-6
        if np.isnan(rms_val):
            return 0.0
        ref_rms = max_rms if max_rms is not None else self.rms_reference
        rms_db = 20.0 * np.log10((max(0.0, float(rms_val)) + eps) / (max(eps, float(ref_rms)) + eps))
        range_db = self.rms_db_p95 - self.rms_db_p10
        if range_db < 1e-3 or np.isnan(rms_db):
            return 0.5
        return float(np.clip((rms_db - self.rms_db_p10) / range_db, 0.0, 1.0))

    def normalize_flux(self, flux_val: float) -> float:
        """Map raw flux to [0, 1] via P95 percentile scaling."""
        return float(np.clip(flux_val / max(1e-6, self.flux_p95), 0.0, 1.0))

    def normalize_onset(self, onset_val: float) -> float:
        """Map raw onset to [0, 1] via P95 percentile scaling."""
        return float(np.clip(onset_val / max(1e-6, self.onset_p95), 0.0, 1.0))

    def normalize_contrast(self, contrast_val: float) -> float:
        """Map raw spectral contrast dB to [0, 1] via P10/P95 percentile scaling."""
        denom = max(1e-3, self.contrast_high - self.contrast_low)
        return float(np.clip((contrast_val - self.contrast_low) / denom, 0.0, 1.0))
