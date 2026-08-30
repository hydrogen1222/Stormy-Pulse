"""
Spectrum analysis module using librosa.
"""
from concurrent.futures import ThreadPoolExecutor
import numpy as np
import librosa
from scipy.ndimage import uniform_filter1d
from typing import Optional, Tuple, Dict


def fast_hpss(
    y: np.ndarray,
    n_fft: int = 2048,
    hop_length: int = 512,
    kernel_size=31,
    power: float = 2.0,
    margin=(1.0, 5.0),
):
    """Fast harmonic/percussive separation using mean filters instead of median filters.

    The original librosa HPSS median filter is the single largest cost in feature
    extraction (tens of seconds on a 5-minute track).  Replacing the median with
    a uniform (mean) filter preserves the harmonic component very closely and is
    dramatically faster.  This also returns the already-computed STFTs so callers
    do not need to re-run STFT on the separated waveforms.
    """
    if isinstance(kernel_size, (tuple, list)):
        win_harm = int(kernel_size[0])
        win_perc = int(kernel_size[1])
    else:
        win_harm = int(kernel_size)
        win_perc = int(kernel_size)

    if isinstance(margin, (tuple, list)):
        margin_harm = float(margin[0])
        margin_perc = float(margin[1])
    else:
        margin_harm = float(margin)
        margin_perc = float(margin)

    S = librosa.stft(y, n_fft=n_fft, hop_length=hop_length)
    mag = np.abs(S)

    # The two median/mean filter passes are independent; run them in parallel
    # so multi-core machines use more than one core for the dominant HPSS cost.
    with ThreadPoolExecutor(max_workers=2) as executor:
        f_harm = executor.submit(
            uniform_filter1d, mag, size=win_harm, axis=1, mode="reflect"
        )
        f_perc = executor.submit(
            uniform_filter1d, mag, size=win_perc, axis=0, mode="reflect"
        )
        harm = f_harm.result()
        perc = f_perc.result()

    mask_harm = (harm ** power) / (
        harm ** power + (perc * margin_harm) ** power + 1e-10
    )
    mask_perc = (perc ** power) / (
        perc ** power + (harm * margin_perc) ** power + 1e-10
    )

    S_harm = S * mask_harm
    S_perc = S * mask_perc

    # Both ISTFTs are independent too; parallelize them as well.
    with ThreadPoolExecutor(max_workers=2) as executor:
        f_yh = executor.submit(librosa.istft, S_harm, hop_length=hop_length, length=len(y))
        f_yp = executor.submit(librosa.istft, S_perc, hop_length=hop_length, length=len(y))
        y_harm = f_yh.result()
        y_perc = f_yp.result()
    return S, S_harm, S_perc, y_harm, y_perc


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


def compute_spectral_bandwidth(S_mag: np.ndarray, sr: int, n_fft: int = 2048) -> np.ndarray:
    """Compute spectral bandwidth from an existing magnitude spectrogram.

    Avoids a second internal STFT compared to ``librosa.feature.spectral_bandwidth(y=...)``.
    """
    freqs = librosa.fft_frequencies(sr=sr, n_fft=n_fft)
    total = S_mag.sum(axis=0, keepdims=True)
    norm = S_mag / np.maximum(total, 1e-10)
    centroid = (norm * freqs[:, None]).sum(axis=0)
    bandwidth = np.sqrt((norm * (freqs[:, None] - centroid[None, :]) ** 2).sum(axis=0))
    return np.clip(bandwidth / (sr / 2), 0, 1)


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
    S_power: np.ndarray, n_fft: int, sr: int, return_shares: bool = False
) -> Dict[str, np.ndarray] | Tuple[Dict[str, np.ndarray], np.ndarray]:
    """
    Compute energy in 6 different frequency bands.
    Returns band drives, and optionally (band_drives, raw_shares_matrix).
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
    
    raw_energies = {}
    
    for name, (f_min, f_max) in bands.items():
        bins = (freqs >= f_min) & (freqs < f_max) & valid
        if bins.sum() > 0:
            energy = np.sum(S_power[bins], axis=0)
            raw_energies[name] = energy
        else:
            raw_energies[name] = np.zeros(S_power.shape[1])

    # Compute raw cross-band power shares sum == 1.0
    band_names = ["bass", "low_mid", "mid", "high_mid", "high", "presence"]
    raw_stack = np.array([raw_energies[name] for name in band_names])
    tot_power = np.sum(raw_stack, axis=0, keepdims=True)
    raw_shares = raw_stack / np.maximum(1e-8, tot_power)
            
    def normalize_with_dynamics(x, punch_factor=1.0, sub_moving_min=False):
        if x.max() == 0:
            return x
            
        x_norm = x.copy()
        
        # Remove slow moving background energy
        if sub_moving_min and len(x) > 80:
            import scipy.ndimage
            mov_min = scipy.ndimage.minimum_filter1d(x_norm, size=80)
            x_norm = x_norm - mov_min
            x_norm = np.maximum(x_norm, 0)
            
        if x_norm.max() > 0:
            x_norm = x_norm / x_norm.max()
            
        return x_norm ** punch_factor
        
    energies = {}
    energies["bass"] = normalize_with_dynamics(raw_energies["bass"], 1.5, sub_moving_min=True)
    energies["low_mid"] = normalize_with_dynamics(raw_energies["low_mid"], 1.3, sub_moving_min=True)
    energies["mid"] = normalize_with_dynamics(raw_energies["mid"], 1.1)
    energies["high_mid"] = normalize_with_dynamics(raw_energies["high_mid"], 1.0)
    energies["high"] = normalize_with_dynamics(raw_energies["high"], 1.0)
    energies["presence"] = normalize_with_dynamics(raw_energies["presence"], 1.0)

    if return_shares:
        return energies, raw_shares
    return energies


def get_frequency_array(n_fft: int, sr: int) -> np.ndarray:
    """Get frequency array for FFT bins."""
    return librosa.fft_frequencies(n_fft=n_fft, sr=sr)


def compute_spectral_flatness(S_power: np.ndarray, hop_length: int = 512) -> np.ndarray:
    """Compute spectral flatness from an existing power spectrogram.

    Avoids a second internal STFT compared to ``librosa.feature.spectral_flatness(y=...)``.
    """
    return librosa.feature.spectral_flatness(S=S_power, hop_length=hop_length)[0]


def compute_chroma(
    y: Optional[np.ndarray] = None,
    sr: int = 22050,
    hop_length: int = 512,
    S: Optional[np.ndarray] = None,
    n_fft: int = 2048,
) -> np.ndarray:
    """Compute chroma feature (12 bins representing notes).

    Uses STFT-based chroma by default, which is much faster than CQT chroma while
    remaining musically useful for this visualizer.  Pass ``S`` to reuse an
    already-computed magnitude spectrogram and skip another STFT.
    """
    # tuning=0.0 skips librosa's automatic tuning estimation, which is very
    # expensive and not needed for visualizer-grade chroma features.
    if S is not None:
        return librosa.feature.chroma_stft(S=S, sr=sr, hop_length=hop_length, n_fft=n_fft, tuning=0.0)
    return librosa.feature.chroma_stft(y=y, sr=sr, hop_length=hop_length, n_fft=n_fft, tuning=0.0)


def compute_spectral_contrast(S_mag: np.ndarray, sr: int) -> np.ndarray:
    """Compute spectral contrast 1D series over time (averaged across frequency bands)."""
    contrast = librosa.feature.spectral_contrast(S=S_mag, sr=sr)
    return np.mean(contrast, axis=0)
