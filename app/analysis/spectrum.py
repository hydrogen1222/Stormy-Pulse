"""
Spectrum analysis module using librosa.
"""
import numpy as np
import librosa
from typing import Tuple, Dict


def compute_rms(y: np.ndarray, frame_length: int = 2048, hop_length: int = 512) -> np.ndarray:
    """Compute RMS energy."""
    return librosa.feature.rms(y=y, frame_length=frame_length, hop_length=hop_length)[0]


def compute_peak_energy(y: np.ndarray, frame_length: int = 2048, hop_length: int = 512) -> np.ndarray:
    """Compute peak amplitude per frame."""
    # librosa.util.frame doesn't pad by default, so we pad like librosa.stft/rms does with center=True
    y_padded = np.pad(y, (frame_length // 2, frame_length // 2), mode='reflect')
    frames = librosa.util.frame(y_padded, frame_length=frame_length, hop_length=hop_length)
    return np.max(np.abs(frames), axis=0)


def compute_spectral_centroid(
    S: np.ndarray, frequencies: np.ndarray
) -> np.ndarray:
    """Compute spectral centroid for each frame."""
    centroid = librosa.feature.spectral_centroid(S=S, freq=frequencies)[0]
    return np.clip(centroid / 8000.0, 0, 1)


def compute_spectral_rolloff(
    S: np.ndarray, frequencies: np.ndarray
) -> np.ndarray:
    """Compute spectral rolloff for each frame."""
    rolloff = librosa.feature.spectral_rolloff(S=S, freq=frequencies)[0]
    return np.clip(rolloff / 8000.0, 0, 1)


def compute_spectral_bandwidth(y: np.ndarray, sr: int, hop_length: int = 512) -> np.ndarray:
    """Compute spectral bandwidth."""
    bw = librosa.feature.spectral_bandwidth(y=y, sr=sr, hop_length=hop_length)[0]
    return np.clip(bw / (sr / 2), 0, 1)


def compute_spectral_flux(S_mag: np.ndarray) -> np.ndarray:
    """Compute spectral flux (positive differences in magnitude spectrum)."""
    flux = np.diff(S_mag, axis=1)
    flux = np.maximum(flux, 0)
    flux = np.sum(flux, axis=0)
    # Pad to match original length
    flux = np.pad(flux, (1, 0), mode='constant')
    if flux.max() > 0:
        flux = flux / flux.max()
    return flux


def compute_zero_crossing_rate(y: np.ndarray, frame_length: int = 2048, hop_length: int = 512) -> np.ndarray:
    """Compute zero crossing rate."""
    return librosa.feature.zero_crossing_rate(y=y, frame_length=frame_length, hop_length=hop_length)[0]


def compute_onset_strength(
    y: np.ndarray, sr: int, hop_length: int = 512
) -> np.ndarray:
    """Compute onset strength envelope."""
    onset_env = librosa.onset.onset_strength(
        y=y, sr=sr, hop_length=hop_length, n_fft=2048
    )
    if onset_env.max() > 0:
        onset_env = onset_env / onset_env.max()
    return onset_env


def compute_band_energies_6(
    S_power: np.ndarray, n_fft: int, sr: int
) -> Dict[str, np.ndarray]:
    """
    Compute energy in 6 different frequency bands.
    """
    freqs = librosa.fft_frequencies(n_fft=n_fft, sr=sr)
    valid = freqs > 0
    
    bands = {
        "bass": (0, 250),
        "low_mid": (250, 500),
        "mid": (500, 2000),
        "high_mid": (2000, 4000),
        "high": (4000, 8000),
        "presence": (8000, sr // 2)
    }
    
    energies = {}
    
    for name, (f_min, f_max) in bands.items():
        bins = (freqs >= f_min) & (freqs < f_max) & valid
        if bins.sum() > 0:
            energy = np.sum(S_power[bins], axis=0)
            energies[name] = energy
        else:
            energies[name] = np.zeros(S_power.shape[1])
            
    def normalize_with_dynamics(x, punch_factor=1.0, sub_moving_min=False):
        if x.max() == 0:
            return x
            
        x_norm = x.copy()
        
        # Remove slow moving background energy (e.g. 2 seconds = approx 80 frames at 43Hz)
        if sub_moving_min and len(x) > 80:
            import scipy.ndimage
            # Fast moving minimum
            mov_min = scipy.ndimage.minimum_filter1d(x_norm, size=80)
            x_norm = x_norm - mov_min
            x_norm = np.maximum(x_norm, 0)
            
        if x_norm.max() > 0:
            x_norm = x_norm / x_norm.max()
            
        return x_norm ** punch_factor
        
    energies["bass"] = normalize_with_dynamics(energies["bass"], 1.5, sub_moving_min=True)
    energies["low_mid"] = normalize_with_dynamics(energies["low_mid"], 1.3, sub_moving_min=True)
    energies["mid"] = normalize_with_dynamics(energies["mid"], 1.1)
    energies["high_mid"] = normalize_with_dynamics(energies["high_mid"], 1.0)
    energies["high"] = normalize_with_dynamics(energies["high"], 1.0)
    energies["presence"] = normalize_with_dynamics(energies["presence"], 1.0)
    
    return energies


def get_frequency_array(n_fft: int, sr: int) -> np.ndarray:
    """Get frequency array for FFT bins."""
    return librosa.fft_frequencies(n_fft=n_fft, sr=sr)


def compute_spectral_flatness(y: np.ndarray, hop_length: int = 512) -> np.ndarray:
    """Compute spectral flatness for each frame."""
    return librosa.feature.spectral_flatness(y=y, hop_length=hop_length)[0]


def compute_chroma(y: np.ndarray, sr: int, hop_length: int = 512) -> np.ndarray:
    """Compute chroma feature (12 bins representing notes)."""
    chroma = librosa.feature.chroma_cqt(y=y, sr=sr, hop_length=hop_length)
    return chroma


def compute_spectral_contrast(S_mag: np.ndarray, sr: int) -> np.ndarray:
    """Compute spectral contrast 1D series over time (averaged across frequency bands)."""
    contrast = librosa.feature.spectral_contrast(S=S_mag, sr=sr)
    return np.mean(contrast, axis=0)
