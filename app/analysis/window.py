"""
Window-level feature analysis (rolling statistics).
Strictly causal trailing windows [t - window_sec, t] aligned to 1Hz timeline.
"""
from concurrent.futures import ThreadPoolExecutor
import os
from typing import Dict, Tuple
import numpy as np


def compute_rolling_stats_causal(
    feature: np.ndarray,
    frame_rate: float,
    times_1hz: np.ndarray,
    window_sec: float,
) -> Tuple[np.ndarray, np.ndarray]:
    """
    Compute causal trailing rolling mean and trend for a feature over times_1hz.
    Trailing window is [max(0, t - window_sec), t].
    Trend is calculated as (second_half_mean - first_half_mean).
    """
    n_times = len(times_1hz)
    n_frames = len(feature)

    means = np.zeros(n_times, dtype=float)
    trends = np.zeros(n_times, dtype=float)

    for i, t in enumerate(times_1hz):
        frame_end = min(n_frames, int(round(t * frame_rate)) + 1)
        frame_start = max(0, int(round((t - window_sec) * frame_rate)))

        if frame_end <= frame_start or frame_start >= n_frames:
            if frame_start < n_frames:
                means[i] = float(feature[frame_start])
            continue

        window_data = feature[frame_start:frame_end]
        if len(window_data) == 0:
            continue

        means[i] = float(np.mean(window_data))

        half = len(window_data) // 2
        if half > 0:
            first_half = float(np.mean(window_data[:half]))
            second_half = float(np.mean(window_data[half:]))
            trends[i] = second_half - first_half

    return means, trends


def compute_event_density_causal(
    events: np.ndarray,
    times_1hz: np.ndarray,
    window_sec: float,
) -> np.ndarray:
    """
    Compute causal event density (events/sec) over trailing window [max(0, t - window_sec), t].
    Uses searchsorted for O(log N) lookup.
    """
    n_times = len(times_1hz)
    density = np.zeros(n_times, dtype=float)

    if len(events) == 0:
        return density

    sorted_events = np.sort(events)

    for i, t in enumerate(times_1hz):
        start_time = max(0.0, float(t) - window_sec)
        end_time = float(t)
        effective_win = max(0.1, end_time - start_time) if t > 0 else max(0.1, window_sec)

        left = int(np.searchsorted(sorted_events, start_time, side="left"))
        right = int(np.searchsorted(sorted_events, end_time, side="right"))
        count = right - left
        density[i] = count / effective_win

    return density


def compute_window_features(
    frame_features: np.ndarray,
    frame_rate: float,
    beat_positions: np.ndarray,
    onset_positions: np.ndarray,
    duration: float,
    F_RMS: int,
    F_CENTROID: int,
    F_FLUX: int,
) -> Dict[str, Dict[str, np.ndarray]]:
    """
    Compute 2s, 4s, and 8s window features downsampled to 1Hz timeline [0, duration].
    All window dictionaries share identical array lengths corresponding to times_1hz.
    """
    duration = max(1.0, float(duration))
    times_1hz = np.arange(0.0, duration + 1e-5, 1.0)
    windows = {}

    rms = frame_features[:, F_RMS]
    centroid = frame_features[:, F_CENTROID]
    flux = frame_features[:, F_FLUX]

    def _compute_window(win_sec: int) -> Tuple[int, Dict[str, np.ndarray]]:
        energy_mean, energy_trend = compute_rolling_stats_causal(rms, frame_rate, times_1hz, float(win_sec))
        brightness_mean, brightness_trend = compute_rolling_stats_causal(centroid, frame_rate, times_1hz, float(win_sec))
        spectral_activity, _ = compute_rolling_stats_causal(flux, frame_rate, times_1hz, float(win_sec))

        beat_density = compute_event_density_causal(beat_positions, times_1hz, float(win_sec))
        onset_density = compute_event_density_causal(onset_positions, times_1hz, float(win_sec))

        # Normalize event densities (4 beats/sec = 240 BPM max, 10 onsets/sec max)
        norm_beat_density = np.clip(beat_density / 4.0, 0.0, 1.0)
        norm_onset_density = np.clip(onset_density / 10.0, 0.0, 1.0)

        chaos_proxy = np.clip(
            (spectral_activity + norm_onset_density + np.abs(energy_trend)) / 3.0,
            0.0,
            1.0,
        )

        return win_sec, {
            "energy_mean": energy_mean,
            "energy_trend": energy_trend,
            "brightness_mean": brightness_mean,
            "brightness_trend": brightness_trend,
            "spectral_activity": spectral_activity,
            "beat_density": norm_beat_density,
            "transient_density": norm_onset_density,
            "chaos_proxy": chaos_proxy,
        }

    # The three window sizes are independent; use all available cores (bounded
    # to the number of windows) so this stage does not run strictly serially.
    with ThreadPoolExecutor(max_workers=min(3, (os.cpu_count() or 1))) as executor:
        for win_sec, stats in executor.map(_compute_window, [2, 4, 8]):
            windows[f"stats_{win_sec}s"] = stats

    return {
        "times_1hz": times_1hz,
        **windows,
    }