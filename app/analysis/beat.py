"""
Beat detection module.
"""
import numpy as np
from typing import Tuple


def detect_beats(
    onset_envelope: np.ndarray,
    sample_rate: int,
    hop_length: int,
    tempo_hint: float = None,
) -> Tuple[np.ndarray, np.ndarray]:
    from scipy.signal import find_peaks
    """
    Detect beat positions from onset strength envelope.

    Returns:
        beat_times: Array of beat times in seconds
        beat_strengths: Array of beat strengths (0-1)
    """
    # Normalize onset envelope
    onset_norm = onset_envelope.copy()
    if onset_norm.max() > 0:
        onset_norm = onset_norm / onset_norm.max()

    # Compute onset derivative for peak detection
    onset_diff = np.diff(onset_norm, prepend=0)
    onset_diff = np.maximum(onset_diff, 0)  # Only positive changes

    # Dynamic threshold based on mean and standard deviation
    threshold = np.mean(onset_norm) + 0.3 * np.std(onset_norm)
    threshold = max(threshold, 0.15)

    # Find peaks
    distance = int(sample_rate / hop_length * 0.3)  # Min 300ms between beats
    peaks, properties = find_peaks(
        onset_norm, distance=distance, height=threshold, prominence=0.1
    )

    if len(peaks) == 0:
        # Fallback: return evenly spaced beats at ~120 BPM
        duration = len(onset_envelope) * hop_length / sample_rate
        beat_times = np.arange(0.5, duration, 0.5)  # 120 BPM
        beat_strengths = np.ones(len(beat_times)) * 0.5
        return beat_times, beat_strengths

    # Convert peak indices to time
    beat_times = peaks * hop_length / sample_rate

    # Compute beat strengths
    beat_strengths = onset_norm[peaks]

    # Filter out beats that are too close together (within 200ms)
    if len(beat_times) > 1:
        min_interval = 0.2  # 200ms minimum
        filtered_times = [beat_times[0]]
        filtered_strengths = [beat_strengths[0]]
        for i in range(1, len(beat_times)):
            if beat_times[i] - filtered_times[-1] >= min_interval:
                filtered_times.append(beat_times[i])
                filtered_strengths.append(beat_strengths[i])
        beat_times = np.array(filtered_times)
        beat_strengths = np.array(filtered_strengths)

    return beat_times, beat_strengths


def estimate_tempo(beat_times: np.ndarray) -> float:
    """
    Estimate tempo (BPM) from beat times.

    Returns:
        tempo: Estimated BPM
    """
    if len(beat_times) < 2:
        return 120.0  # Default

    # Compute intervals between beats
    intervals = np.diff(beat_times)

    # Filter outliers (keep intervals within 300-30 BPM range)
    min_interval = 60.0 / 200  # 200 BPM max
    max_interval = 60.0 / 40  # 40 BPM min
    valid_intervals = intervals[(intervals >= min_interval) & (intervals <= max_interval)]

    if len(valid_intervals) == 0:
        return 120.0

    # Use median interval for robustness
    median_interval = np.median(valid_intervals)
    tempo = 60.0 / median_interval

    # Clamp to reasonable range
    return np.clip(tempo, 60.0, 180.0)


def compute_beat_regularity(beat_times: np.ndarray) -> float:
    """
    Compute how regular the beats are (0-1).

    Returns:
        regularity: 0 = very irregular, 1 = very regular
    """
    if len(beat_times) < 3:
        return 0.5

    intervals = np.diff(beat_times)

    # Coefficient of variation (CV) - lower is more regular
    mean_interval = np.mean(intervals)
    std_interval = np.std(intervals)

    if mean_interval == 0:
        return 0.5

    cv = std_interval / mean_interval

    # Convert CV to regularity score (0-1)
    # CV of 0 = perfect regularity = 1.0
    # CV of 1 = high irregularity = 0.0
    regularity = max(0.0, min(1.0, 1.0 - cv))

    return regularity
