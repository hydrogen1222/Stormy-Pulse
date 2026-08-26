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

        # Convert RMS to dB relative to max
        max_rms = max(eps, float(np.max(rms_arr))) if len(rms_arr) > 0 else 1.0
        rms_db = 20.0 * np.log10((rms_arr + eps) / (max_rms + eps))

        rms_p10 = float(np.percentile(rms_db, 10)) if len(rms_db) > 0 else -40.0
        rms_p95 = float(np.percentile(rms_db, 95)) if len(rms_db) > 0 else 0.0

        flx_p95 = max(eps, float(np.percentile(flux_arr, 95))) if len(flux_arr) > 0 else 1.0
        ons_p95 = max(eps, float(np.percentile(onset_arr, 95))) if len(onset_arr) > 0 else 1.0

        if contrast_arr is not None and len(contrast_arr) > 0:
            c_low = float(np.percentile(contrast_arr, 10))
            c_high = max(c_low + eps, float(np.percentile(contrast_arr, 95)))
        else:
            c_low, c_high = 10.0, 35.0

        return cls(
            rms_db_p10=rms_p10,
            rms_db_p95=rms_p95,
            flux_p95=flx_p95,
            onset_p95=ons_p95,
            contrast_low=c_low,
            contrast_high=c_high,
        )

    def normalize_rms_db(self, rms_val: float, max_rms: float = 1.0) -> float:
        """Map raw RMS to [0, 1] via dB space P10/P95 scaling."""
        eps = 1e-6
        rms_db = 20.0 * np.log10((max(0.0, rms_val) + eps) / (max(eps, max_rms) + eps))
        range_db = self.rms_db_p95 - self.rms_db_p10
        if range_db < 1e-3:
            return 0.5
        return float(np.clip((rms_db - self.rms_db_p10) / range_db, 0.0, 1.0))

    def normalize_flux(self, flux_val: float) -> float:
        """Map raw flux to [0, 1] via P95 percentile scaling."""
        return float(np.clip(flux_val / max(1e-6, self.flux_p95), 0.0, 1.0))

    def normalize_onset(self, onset_val: float) -> float:
        """Map raw onset to [0, 1] via P95 percentile scaling."""
        return float(np.clip(onset_val / max(1e-6, self.onset_p95), 0.0, 1.0))
