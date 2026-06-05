"""
Window-level feature analysis (rolling statistics).
"""
import numpy as np
from typing import Dict, Tuple

def compute_rolling_stats(
    feature: np.ndarray, 
    window_frames: int, 
    hop_frames: int
) -> Tuple[np.ndarray, np.ndarray]:
    """
    Compute rolling mean and trend for a feature.
    Trend is approximated by the difference between the second half and first half of the window.
    """
    n_frames = len(feature)
    out_length = max(1, (n_frames - window_frames) // hop_frames + 1)
    
    means = np.zeros(out_length)
    trends = np.zeros(out_length)
    
    for i in range(out_length):
        start = i * hop_frames
        end = start + window_frames
        if end > n_frames:
            end = n_frames
            
        window_data = feature[start:end]
        if len(window_data) == 0:
            continue
            
        means[i] = np.mean(window_data)
        
        # Compute trend (linear regression slope could be better, but diff of halves is faster)
        half = len(window_data) // 2
        if half > 0:
            first_half = np.mean(window_data[:half])
            second_half = np.mean(window_data[half:])
            trends[i] = second_half - first_half
            
    return means, trends


def compute_event_density(
    events: np.ndarray, 
    total_duration: float, 
    window_sec: float, 
    hop_sec: float
) -> np.ndarray:
    """
    Compute density of events (e.g., beats or onsets) per window.
    """
    out_length = max(1, int((total_duration - window_sec) / hop_sec) + 1)
    density = np.zeros(out_length)
    
    for i in range(out_length):
        start_time = i * hop_sec
        end_time = start_time + window_sec
        
        # Count events in this window
        count = np.sum((events >= start_time) & (events < end_time))
        density[i] = count / window_sec  # events per second
        
    return density


def compute_window_features(
    frame_features: np.ndarray, 
    frame_rate: float, 
    beat_positions: np.ndarray, 
    onset_positions: np.ndarray,
    duration: float,
    F_RMS: int,
    F_CENTROID: int,
    F_FLUX: int
) -> Dict[str, Dict[str, np.ndarray]]:
    """
    Compute 2s, 4s, and 8s window features downsampled to 1Hz.
    """
    windows = {}
    hop_sec = 1.0  # 1 Hz output rate
    hop_frames = int(frame_rate * hop_sec)
    
    rms = frame_features[:, F_RMS]
    centroid = frame_features[:, F_CENTROID]
    flux = frame_features[:, F_FLUX]
    
    for win_sec in [2, 4, 8]:
        win_frames = int(frame_rate * win_sec)
        
        energy_mean, energy_trend = compute_rolling_stats(rms, win_frames, hop_frames)
        brightness_mean, brightness_trend = compute_rolling_stats(centroid, win_frames, hop_frames)
        spectral_activity, _ = compute_rolling_stats(flux, win_frames, hop_frames)
        
        beat_density = compute_event_density(beat_positions, duration, win_sec, hop_sec)
        onset_density = compute_event_density(onset_positions, duration, win_sec, hop_sec)
        
        # Normalize event densities (rough max heuristic: 4 beats/sec = 240 BPM, 10 onsets/sec)
        beat_density = np.clip(beat_density / 4.0, 0, 1)
        onset_density = np.clip(onset_density / 10.0, 0, 1)
        
        # Ensure all arrays have the same length (dictated by the hop_sec)
        min_len = min(len(energy_mean), len(beat_density))
        
        windows[f"stats_{win_sec}s"] = {
            "energy_mean": energy_mean[:min_len],
            "energy_trend": energy_trend[:min_len],
            "brightness_mean": brightness_mean[:min_len],
            "brightness_trend": brightness_trend[:min_len],
            "spectral_activity": spectral_activity[:min_len],
            "beat_density": beat_density[:min_len],
            "transient_density": onset_density[:min_len],
            # Chaos proxy: high spectral flux + high transient density + unstable energy
            "chaos_proxy": np.clip((spectral_activity[:min_len] + onset_density[:min_len] + np.abs(energy_trend[:min_len])) / 3.0, 0, 1)
        }
        
    # Generate times array for 1Hz
    min_len = len(windows["stats_2s"]["energy_mean"])
    times_1hz = np.arange(min_len) * hop_sec
    
    return {
        "times_1hz": times_1hz,
        **windows
    }