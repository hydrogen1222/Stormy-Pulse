"""Tests for the faster feature-extraction helpers."""
import numpy as np
import librosa

from app.analysis.spectrum import (
    fast_hpss,
    compute_spectral_bandwidth,
    compute_chroma,
    compute_spectral_flatness,
)


def _sine_wave(duration=2.0, sr=22050, freq=440.0):
    t = np.linspace(0, duration, int(sr * duration), endpoint=False)
    return 0.5 * np.sin(2 * np.pi * freq * t)


def test_fast_hpss_returns_stft_and_waveforms():
    y = _sine_wave()
    S, S_harm, S_perc, y_harm, y_perc = fast_hpss(
        y, n_fft=2048, hop_length=512, kernel_size=(31, 31), margin=(1.0, 5.0)
    )
    assert S.shape == S_harm.shape == S_perc.shape
    assert y_harm.shape == y_perc.shape == y.shape
    assert np.all(np.isfinite(y_harm))
    assert np.all(np.isfinite(y_perc))


def test_fast_hpss_harmonic_correlates_with_librosa():
    y = _sine_wave(duration=1.0)
    _, _, _, y_harm_fast, _ = fast_hpss(
        y, n_fft=2048, hop_length=512, kernel_size=(15, 15), margin=(1.0, 5.0)
    )
    y_harm_lib, _ = librosa.effects.hpss(
        y, kernel_size=(15, 15), margin=(1.0, 5.0)
    )
    # The mean-filter approximation should preserve the dominant harmonic
    # component closely (not bit-exact, but highly correlated).
    corr = np.corrcoef(y_harm_fast, y_harm_lib)[0, 1]
    assert corr > 0.95


def test_compute_spectral_bandwidth_matches_librosa():
    y = _sine_wave()
    S = librosa.stft(y, n_fft=2048, hop_length=512)
    S_mag = np.abs(S)
    fast = compute_spectral_bandwidth(S_mag, sr=22050, n_fft=2048)
    ref = librosa.feature.spectral_bandwidth(y=y, sr=22050, hop_length=512)[0]
    ref = np.clip(ref / (22050 / 2), 0, 1)
    assert fast.shape == ref.shape
    assert np.max(np.abs(fast - ref)) < 1e-6


def test_compute_chroma_stft_is_fast_shape():
    y = _sine_wave()
    S = librosa.stft(y, n_fft=2048, hop_length=512)
    chroma = compute_chroma(S=np.abs(S), sr=22050, hop_length=512, n_fft=2048)
    assert chroma.shape[0] == 12
    assert chroma.shape[1] == S.shape[1]


def test_compute_spectral_flatness_from_power():
    y = _sine_wave()
    S = librosa.stft(y, n_fft=2048, hop_length=512)
    flat = compute_spectral_flatness(np.abs(S) ** 2, hop_length=512)
    assert flat.shape[0] == S.shape[1]
    assert np.all(np.isfinite(flat))
