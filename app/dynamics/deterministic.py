"""
Stateless Deterministic Randomness & Hash Generator.
Provides stateless, reproducible pseudo-random numbers based on BLAKE2b hash.
Zero Python global RNG state dependency.
"""
from __future__ import annotations

import hashlib
import struct


def deterministic_hash_uint64(track_seed: int, stream_id: str, tick: int, event_idx: int = 0) -> int:
    """Hash tuple (track_seed, stream_id, tick, event_idx) into a uint64 integer."""
    msg = f"{track_seed}:{stream_id}:{tick}:{event_idx}".encode("utf-8")
    digest = hashlib.blake2b(msg, digest_size=8).digest()
    return struct.unpack("<Q", digest)[0]


def deterministic_float(track_seed: int, stream_id: str, tick: int, event_idx: int = 0) -> float:
    """Generate deterministic float in [0.0, 1.0) from stateless tuple key."""
    u = deterministic_hash_uint64(track_seed, stream_id, tick, event_idx)
    # Convert 64-bit int to [0, 1) float
    return (u & 0xFFFFFFFFFFFFF) / float(1 << 52)


def deterministic_uniform(
    track_seed: int, stream_id: str, tick: int, event_idx: int = 0, low: float = 0.0, high: float = 1.0
) -> float:
    """Generate deterministic float in [low, high)."""
    f = deterministic_float(track_seed, stream_id, tick, event_idx)
    return low + f * (high - low)
