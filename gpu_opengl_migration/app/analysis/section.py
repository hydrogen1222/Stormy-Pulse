"""
Section-level feature analysis (macro structure).
"""
import numpy as np
from typing import Dict, List, Tuple, Any
import librosa


def extract_sections(
    y: np.ndarray, 
    sr: int, 
    hop_length: int, 
    duration: float
) -> Dict[str, Any]:
    """
    Extract song structure boundaries using a novelty curve.
    """
    # 1. Compute a novelty curve using librosa's rec_matrix and novelty
    # To keep it fast, we use a coarse mel spectrogram
    S = librosa.feature.melspectrogram(y=y, sr=sr, hop_length=hop_length, n_mels=64)
    S_log = librosa.power_to_db(S, ref=np.max)
    
    # Use MFCC for structure
    mfcc = librosa.feature.mfcc(S=S_log, n_mfcc=13)
    
    # Compute self-similarity matrix
    # Using a larger hop for the structure analysis to speed it up (e.g., ~1 second per frame)
    struct_hop = int(sr) 
    mfcc_coarse = librosa.feature.mfcc(y=y, sr=sr, hop_length=struct_hop, n_mfcc=13)
    
    # Compute cross-similarity
    R = librosa.segment.recurrence_matrix(mfcc_coarse, mode='affinity', metric='cosine', sym=True)
    
    # Compute novelty curve from recurrence matrix
    # A simple diagonal filter
    novelty = librosa.segment.recurrence_to_lag(R)
    novelty_curve = np.linalg.norm(np.diff(novelty, axis=1), axis=0)
    # Pad to match
    novelty_curve = np.pad(novelty_curve, (1, 0), mode='constant')
    if novelty_curve.max() > 0:
        novelty_curve = novelty_curve / novelty_curve.max()
        
    # Find peaks in novelty curve (boundaries)
    peaks = librosa.util.peak_pick(novelty_curve, pre_max=5, post_max=5, pre_avg=5, post_avg=5, delta=0.1, wait=10)
    
    # Convert peaks to time
    boundaries = peaks * (struct_hop / sr)
    # Ensure 0 and duration are boundaries
    boundaries = np.unique(np.concatenate(([0.0], boundaries, [duration])))
    
    # Generate labels
    labels = [f"Section {i}" for i in range(len(boundaries) - 1)]
    
    # Compute energy summary per section
    # We can use the RMS or directly S_log
    rms_coarse = librosa.feature.rms(y=y, hop_length=struct_hop)[0]
    
    section_energies = []
    for i in range(len(boundaries) - 1):
        start_idx = int(boundaries[i] * sr / struct_hop)
        end_idx = int(boundaries[i+1] * sr / struct_hop)
        
        if start_idx < end_idx and start_idx < len(rms_coarse):
            energy = np.mean(rms_coarse[start_idx:end_idx])
            section_energies.append(float(energy))
        else:
            section_energies.append(0.0)
            
    # Normalize section energies to find climax candidates
    if len(section_energies) > 0 and max(section_energies) > 0:
        norm_energies = np.array(section_energies) / max(section_energies)
        climax_candidates = [i for i, e in enumerate(norm_energies) if e > 0.85]
    else:
        climax_candidates = []
        
    return {
        "boundaries": boundaries,
        "labels": labels,
        "novelty_curve": novelty_curve,
        "climax_candidates": climax_candidates,
        "repeated_section_candidates": [], # Too complex to compute accurately right now without slow DTW
        "section_energy_summary": section_energies
    }
