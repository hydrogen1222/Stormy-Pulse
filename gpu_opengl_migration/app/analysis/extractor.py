"""
Audio feature extractor - orchestrates multi-level feature extraction.
"""
import numpy as np
import librosa
import soundfile as sf
from pathlib import Path
from typing import Optional
import logging
import time
import hashlib

from .features import (
    FeatureCache, TrackAnalysisMetadata, FrameFeatureSequence, 
    EventFeatureSet, WindowFeatureSet, SectionFeatureSet, 
    SemanticControlSet, GlobalFeatureSet
)
from .spectrum import (
    compute_rms, compute_peak_energy, compute_spectral_centroid,
    compute_spectral_rolloff, compute_spectral_bandwidth, compute_spectral_flux,
    compute_zero_crossing_rate, compute_onset_strength, compute_band_energies_6,
    compute_spectral_flatness, compute_chroma, compute_spectral_contrast
)
from .beat import detect_beats, estimate_tempo, compute_beat_regularity
from .window import compute_window_features
from .section import extract_sections
from ..config.constants import SAMPLE_RATE, HOP_LENGTH, FFT_SIZE

logger = logging.getLogger(__name__)


class FeatureExtractor:
    """Extracts all 5 levels of audio features from a track."""

    def __init__(self):
        self.sr = SAMPLE_RATE
        self.hop_length = HOP_LENGTH
        self.n_fft = FFT_SIZE

    def extract(self, file_path: str, progress_callback=None) -> Optional[FeatureCache]:
        """
        Extract all features from an audio file.
        """
        try:
            logger.info(f"Starting Level 1-5 feature extraction for: {file_path}")
            start_time = time.time()

            # --- STAGE A: Preprocessing ---
            if progress_callback: progress_callback(0, 100, "Loading audio...")
            y, orig_sr = sf.read(file_path)
            
            if len(y.shape) > 1:
                y = np.mean(y, axis=1)

            if orig_sr != self.sr:
                if progress_callback: progress_callback(5, 100, "Resampling...")
                y = librosa.resample(y, orig_sr=orig_sr, target_sr=self.sr, res_type='soxr_hq')
                
            sr = self.sr
            duration = len(y) / sr

            # --- STAGE B: Component separation (Fast approximation) ---
            if progress_callback: progress_callback(10, 100, "Harmonic/Percussive separation...")
            # Use margin for faster but rougher separation
            y_harmonic, y_percussive = librosa.effects.hpss(y, margin=(1.0, 5.0))

            # --- STAGE C: Multi-representation ---
            if progress_callback: progress_callback(20, 100, "Computing spectrograms...")
            S = librosa.stft(y, n_fft=self.n_fft, hop_length=self.hop_length)
            S_mag = np.abs(S)
            S_power = S_mag**2

            S_perc = librosa.stft(y_percussive, n_fft=self.n_fft, hop_length=self.hop_length)
            S_perc_power = np.abs(S_perc)**2
            
            S_harm = librosa.stft(y_harmonic, n_fft=self.n_fft, hop_length=self.hop_length)
            S_harm_power = np.abs(S_harm)**2

            # --- LEVEL 1: Frame-level Features ---
            if progress_callback: progress_callback(30, 100, "Extracting frame features...")
            import concurrent.futures

            with concurrent.futures.ThreadPoolExecutor() as executor:
                f_rms = executor.submit(compute_rms, y, self.n_fft, self.hop_length)
                f_peak = executor.submit(compute_peak_energy, y, self.n_fft, self.hop_length)
                f_bands = executor.submit(compute_band_energies_6, S_power, self.n_fft, sr)
                f_centroid = executor.submit(compute_spectral_centroid, S_power, librosa.fft_frequencies(sr=sr, n_fft=self.n_fft))
                f_rolloff = executor.submit(compute_spectral_rolloff, S_power, librosa.fft_frequencies(sr=sr, n_fft=self.n_fft))
                f_bandwidth = executor.submit(compute_spectral_bandwidth, y, sr, self.hop_length)
                f_flatness = executor.submit(compute_spectral_flatness, y, self.hop_length)
                f_flux = executor.submit(compute_spectral_flux, S_mag)
                f_onset = executor.submit(compute_onset_strength, y_percussive, sr, self.hop_length) # Use percussive for cleaner onsets
                f_zcr = executor.submit(compute_zero_crossing_rate, y, self.n_fft, self.hop_length)
                f_harm_e = executor.submit(compute_rms, y_harmonic, self.n_fft, self.hop_length)
                f_perc_e = executor.submit(compute_rms, y_percussive, self.n_fft, self.hop_length)
                f_chroma = executor.submit(compute_chroma, y_harmonic, sr, self.hop_length)
                f_contrast = executor.submit(compute_spectral_contrast, S_mag, sr)

                rms = f_rms.result()
                peak = f_peak.result()
                bands = f_bands.result()
                centroid = f_centroid.result()
                rolloff = f_rolloff.result()
                bandwidth = f_bandwidth.result()
                flatness = f_flatness.result()
                flux = f_flux.result()
                onset_env = f_onset.result()
                zcr = f_zcr.result()
                harm_e = f_harm_e.result()
                perc_e = f_perc_e.result()
                chroma = f_chroma.result()
                contrast = f_contrast.result()

            n_frames = len(rms)
            times = librosa.frames_to_time(np.arange(n_frames), sr=sr, hop_length=self.hop_length)
            
            features_matrix = np.zeros((n_frames, FrameFeatureSequence.N_FEATURES))
            features_matrix[:, FrameFeatureSequence.F_RMS] = rms
            features_matrix[:, FrameFeatureSequence.F_PEAK] = peak
            features_matrix[:, FrameFeatureSequence.F_LOUDNESS] = np.clip(librosa.amplitude_to_db(rms, ref=np.max) / 80.0 + 1.0, 0, 1) # roughly 0-1
            features_matrix[:, FrameFeatureSequence.F_BAND_BASS] = bands["bass"]
            features_matrix[:, FrameFeatureSequence.F_BAND_LOW_MID] = bands["low_mid"]
            features_matrix[:, FrameFeatureSequence.F_BAND_MID] = bands["mid"]
            features_matrix[:, FrameFeatureSequence.F_BAND_HIGH_MID] = bands["high_mid"]
            features_matrix[:, FrameFeatureSequence.F_BAND_HIGH] = bands["high"]
            features_matrix[:, FrameFeatureSequence.F_BAND_PRESENCE] = bands["presence"]
            features_matrix[:, FrameFeatureSequence.F_CENTROID] = centroid
            features_matrix[:, FrameFeatureSequence.F_ROLLOFF] = rolloff
            features_matrix[:, FrameFeatureSequence.F_BANDWIDTH] = bandwidth
            features_matrix[:, FrameFeatureSequence.F_FLATNESS] = flatness
            features_matrix[:, FrameFeatureSequence.F_FLUX] = flux
            features_matrix[:, FrameFeatureSequence.F_ONSET_STR] = onset_env
            features_matrix[:, FrameFeatureSequence.F_ZCR] = zcr
            features_matrix[:, FrameFeatureSequence.F_HARMONIC_E] = harm_e
            features_matrix[:, FrameFeatureSequence.F_PERCUSSIVE_E] = perc_e
            
            # Fill Chroma (transpose to match frames)
            c_len = min(n_frames, chroma.shape[1])
            features_matrix[:c_len, FrameFeatureSequence.F_CHROMA_START:FrameFeatureSequence.F_CHROMA_START+12] = chroma[:, :c_len].T

            frame_seq = FrameFeatureSequence(
                times=times,
                frame_rate=sr / self.hop_length,
                features=features_matrix
            )

            # --- LEVEL 2: Event-level Features ---
            if progress_callback: progress_callback(55, 100, "Detecting events...")
            beat_times, beat_strengths = detect_beats(onset_env, sr, self.hop_length)
            
            # Simple onset event extraction (peaks of onset_env > threshold)
            onset_peaks = librosa.util.peak_pick(onset_env, pre_max=3, post_max=3, pre_avg=5, post_avg=5, delta=0.1, wait=1)
            onset_positions = onset_peaks * self.hop_length / sr
            onset_event_strengths = onset_env[onset_peaks]
            
            events = EventFeatureSet(
                beat_positions=beat_times,
                beat_strengths=beat_strengths,
                beat_confidence=1.0 if len(beat_times) > 10 else 0.2, # Rough proxy
                onset_positions=onset_positions,
                onset_strengths=onset_event_strengths
            )

            # --- LEVEL 3: Window-level Features ---
            if progress_callback: progress_callback(65, 100, "Computing window stats...")
            windows_dict = compute_window_features(
                frame_features=features_matrix,
                frame_rate=sr / self.hop_length,
                beat_positions=beat_times,
                onset_positions=onset_positions,
                duration=duration,
                F_RMS=FrameFeatureSequence.F_RMS,
                F_CENTROID=FrameFeatureSequence.F_CENTROID,
                F_FLUX=FrameFeatureSequence.F_FLUX
            )
            windows = WindowFeatureSet(
                times_1hz=windows_dict["times_1hz"],
                stats_2s=windows_dict["stats_2s"],
                stats_4s=windows_dict["stats_4s"],
                stats_8s=windows_dict["stats_8s"]
            )

            # --- LEVEL 4: Section-level Features ---
            if progress_callback: progress_callback(75, 100, "Analyzing song structure...")
            section_dict = extract_sections(y, sr, self.hop_length, duration)
            sections = SectionFeatureSet(
                boundaries=section_dict["boundaries"],
                labels=section_dict["labels"],
                novelty_curve=section_dict["novelty_curve"],
                climax_candidates=section_dict["climax_candidates"],
                repeated_section_candidates=section_dict["repeated_section_candidates"],
                section_energy_summary=section_dict["section_energy_summary"]
            )

            # --- LEVEL 5: Global-level & Semantics ---
            if progress_callback: progress_callback(85, 100, "Computing semantic global DNA...")
            tempo = estimate_tempo(beat_times)
            beat_regularity = compute_beat_regularity(beat_times)
            
            globals_set, semantics = self._compute_globals_and_semantics(
                y, features_matrix, tempo, beat_regularity, duration, contrast
            )


            # --- METADATA ---
            stat = Path(file_path).stat()
            hash_str = f"{file_path}_{stat.st_size}_{stat.st_mtime}"
            file_hash = hashlib.md5(hash_str.encode()).hexdigest()
            
            metadata = TrackAnalysisMetadata(
                file_path=file_path,
                file_hash=file_hash,
                cache_version="v4",
                duration=duration,
                sample_rate=sr,
                analysis_timestamp=time.time()
            )

            # Debug: 10s window BASS/RMS correlation
            try:
                frame_rate = sr / self.hop_length
                sample_frames = int(10 * frame_rate)
                if n_frames > sample_frames:
                    # Pick a 10s segment from the middle
                    start_idx = n_frames // 2
                    end_idx = start_idx + sample_frames
                    rms_seg = rms[start_idx:end_idx]
                    bass_seg = bands["bass"][start_idx:end_idx]
                    
                    rms_min, rms_max, rms_mean = np.min(rms_seg), np.max(rms_seg), np.mean(rms_seg)
                    bass_min, bass_max, bass_mean = np.min(bass_seg), np.max(bass_seg), np.mean(bass_seg)
                    correlation = np.corrcoef(rms_seg, bass_seg)[0, 1] if np.std(rms_seg) > 0 and np.std(bass_seg) > 0 else 0
                    
                    print(f"\n[Debug] 10s Segment Stats (Middle):")
                    print(f"  RMS : min={rms_min:.3f}, max={rms_max:.3f}, mean={rms_mean:.3f}")
                    print(f"  BASS: min={bass_min:.3f}, max={bass_max:.3f}, mean={bass_mean:.3f}")
                    print(f"  Correlation (RMS vs BASS): {correlation:.3f}")
                    if correlation > 0.8:
                        print("  Warning: BASS is highly correlated with RMS. They might look similar.")
                    else:
                        print("  Success: BASS is distinct from RMS.")
            except Exception as debug_e:
                print(f"Debug stats failed: {debug_e}")

            if progress_callback: progress_callback(100, 100, "Done!")

            logger.info(
                f"L5 Extraction Complete in {time.time() - start_time:.2f}s | "
                f"Dur: {duration:.1f}s, Beats: {len(beat_times)}, Tempo: {tempo:.1f} BPM"
            )

            return FeatureCache(
                metadata=metadata,
                frame_seq=frame_seq,
                events=events,
                windows=windows,
                sections=sections,
                semantics=semantics,
                globals_set=globals_set
            )

        except Exception as e:
            logger.error(f"Feature extraction failed: {e}", exc_info=True)
            return None

    def _compute_globals_and_semantics(
        self, y, fm, tempo, beat_regularity, duration, spectral_contrast_vec
    ):
        """Derive Level 5 variables using deterministic musical mapping."""
        # Unpack continuous features
        rms = fm[:, FrameFeatureSequence.F_RMS]
        bass = fm[:, FrameFeatureSequence.F_BAND_BASS]
        mid = fm[:, FrameFeatureSequence.F_BAND_MID]
        high = fm[:, FrameFeatureSequence.F_BAND_HIGH]
        centroid = fm[:, FrameFeatureSequence.F_CENTROID]
        flatness = fm[:, FrameFeatureSequence.F_FLATNESS]
        onset_env = fm[:, FrameFeatureSequence.F_ONSET_STR]
        harm_e = fm[:, FrameFeatureSequence.F_HARMONIC_E]
        perc_e = fm[:, FrameFeatureSequence.F_PERCUSSIVE_E]
        flux = fm[:, FrameFeatureSequence.F_FLUX]
        
        # Unpack Chroma (12 bins)
        chroma_data = fm[:, FrameFeatureSequence.F_CHROMA_START:FrameFeatureSequence.F_CHROMA_START+12]
        avg_chroma = np.mean(chroma_data, axis=0) # Shape: (12,)
        
        # Global Stats
        energy = np.clip(np.mean(rms) * 4, 0.1, 1.0)
        dynamic_range = np.std(rms / (np.max(rms) + 1e-8))
        avg_centroid = np.mean(centroid)
        avg_flatness = np.mean(flatness)
        chaos = np.clip(np.std(onset_env) * 4 + np.std(flux) * 2, 0.1, 1.0)
        global_contrast = np.mean(spectral_contrast_vec)
        
        # Spectral Balance
        b_mean = np.mean(bass)
        m_mean = np.mean(mid)
        h_mean = np.mean(high)
        tot = b_mean + m_mean + h_mean + 1e-8
        b_ratio, m_ratio, h_ratio = b_mean/tot, m_mean/tot, h_mean/tot

        # Semantics (Level 5a)
        impact = np.clip(np.mean(perc_e) / (np.mean(harm_e) + 1e-8), 0, 1)
        pressure = np.clip(energy * b_ratio * 3.0, 0, 1)
        sparkle = np.clip(h_ratio * 2.5 + avg_centroid, 0, 1)
        density = np.clip(1.0 - avg_flatness + energy, 0, 1)
        warmth = np.clip(1.0 - avg_centroid * 0.8 + b_ratio * 0.4, 0, 1)
        
        semantics = SemanticControlSet(
            impact=impact,
            pressure=pressure,
            sparkle=sparkle,
            density=density,
            tension=chaos * 0.6 + energy * 0.4,
            warmth=warmth,
            flow=beat_regularity * 0.7 + (1.0 - chaos) * 0.3,
            chaos=chaos,
            lift=np.clip(tempo / 180.0 * 0.5 + h_ratio * 0.5, 0, 1),
            climax_score=energy * 0.8 + density * 0.2
        )
        
        # --- DETERMINISTIC VISUAL MAPPING (The "Fingerprint" Logic) ---
        
        # 1. Hue from Chroma (Musical Key Mapping)
        # Find the strongest note and use it as a base.
        # We also look at the "Chroma Centroid" to distinguish between major/minor tonality feel.
        strongest_note_idx = np.argmax(avg_chroma)
        # Map 12 notes to 360 degrees: C=0, C#=30, D=60, ..., B=330
        hue_base = (strongest_note_idx * 30.0) % 360.0
        
        # Adjust hue based on secondary strongest note (Harmonic complexity)
        sorted_notes = np.argsort(avg_chroma)[::-1]
        secondary_note_idx = sorted_notes[1]
        interval = abs(secondary_note_idx - strongest_note_idx)
        if interval in [3, 4, 7]: # Minor third, Major third, Perfect fifth
             hue_base = (hue_base + 15) % 360 # Slight shift for harmonic richness
        
        # 2. Mood Prior
        if energy > 0.65 and global_contrast > 0.4:
            mood = "energetic"
        elif energy < 0.4 and avg_flatness < 0.1:
            mood = "chill"
        elif avg_centroid < 0.3:
            mood = "dark"
        else:
            mood = "bright"

        # 3. Structure Type from Spectral Balance & Chaos
        if b_ratio > 0.5:
            structure_type = "reactor" # Bass heavy needs a solid core
        elif h_ratio > 0.4:
            structure_type = "vortex"  # High end detail suits vortex
        elif chaos > 0.7:
            structure_type = "organic" # Unpredictable music suits organic
        else:
            structure_type = "pulse"   # Balanced/Electronic suits pulse
            
        # 4. Detail Style from Spectral Contrast (Richness)
        # High contrast means clear peaks/valleys -> spikes or arcs
        if global_contrast > 0.45:
            detail_style = "spikes" if h_ratio > 0.3 else "arcs"
        else:
            detail_style = "glow" if energy < 0.5 else "particles"

        # 5. Motion Prior from Rhythm Regularity
        if beat_regularity > 0.8:
            motion_性格 = "steady" if energy < 0.6 else "agile"
        elif beat_regularity < 0.3:
            motion_性格 = "staccato" # Glitchy/Complex rhythms
        else:
            motion_性格 = "fluid"    # Smooth but moving

        # 6. Palette Type from Dynamic Range & Chroma Spread
        chroma_spread = np.std(avg_chroma)
        if chroma_spread < 0.05: # Very chromatic/noisy
            palette_type = "triadic" 
        elif dynamic_range < 0.12:
            palette_type = "mono"    # Compressed audio feels monolithic
        else:
            palette_type = "analogous"

        globals_set = GlobalFeatureSet(
            tempo=tempo,
            tempo_stability=beat_regularity,
            beat_regularity=beat_regularity,
            dynamic_range=dynamic_range,
            energy=energy,
            brightness=avg_centroid,
            warmth=warmth,
            darkness=1.0 - avg_centroid,
            chaos=chaos,
            density=density,
            bass_ratio=b_ratio,
            mid_ratio=m_ratio,
            high_ratio=h_ratio,
            harmonicity_proxy=1.0 - avg_flatness,
            percussiveness_proxy=impact,
            
            chroma_vector=avg_chroma,
            spectral_contrast=global_contrast,
            
            palette_prior=palette_type,
            structure_prior=structure_type,
            motion_prior=motion_性格,
            
            # Compat
            theme_hue_base=hue_base,
            theme_saturation=0.4 + chaos * 0.5,
            theme_brightness=0.5 + energy * 0.4,
            particle_density=np.clip(chaos * 0.7 + energy * 0.3, 0.1, 1.0),
            ring_count=int(np.clip(3 + energy * 7, 3, 12)),
            line_thickness=np.clip(1.2 + global_contrast * 4, 1.0, 6.0),
            mood=mood,
            structure_type=structure_type,
            detail_style=detail_style,
            motion_性格=motion_性格,
            palette_type=palette_type
        )
        
        return globals_set, semantics
