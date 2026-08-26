"""
Ring layer for circular visualization.
"""
import math
import random
from typing import List


class RingLayer:
    """Manages concentric rings for visualization."""

    def __init__(self, ring_count: int = 5):
        self.ring_count = ring_count
        self.ring_radii = [0.0] * ring_count
        self.ring_phases = [0.0] * ring_count
        self.ring_thickness = [3.0] * ring_count
        self.rotation_angle = 0.0
        self.bass_pulse = 0.0
        self.overall_pulse = 0.0
        self.broken_segments: List[int] = [0] * ring_count
        self.phase_state = None

    def update(
        self,
        bands: list,
        bass: float,
        mid: float,
        high: float,
        energy: float,
        chaos: float,
        beat_pulse: float,
        beat_strength: float,
        is_on_beat: bool,
        bpm: float,
        dt: float = 0.016,
        phase_state = None,
    ):
        """Update ring parameters with phase state tracking."""
        sf = dt * 60.0
        self.phase_state = phase_state

        self.bass_pulse += (bass * 5.8 - self.bass_pulse) * (0.30 if bass * 5.8 > self.bass_pulse else 0.11) * sf
        self.overall_pulse += (energy * 3.8 - self.overall_pulse) * (0.24 if energy * 3.8 > self.overall_pulse else 0.10) * sf

        self.rotation_angle += (0.012 + bass * 0.06 + beat_strength * 0.09) * sf

        # Update each ring
        for ring in range(self.ring_count):
            while ring >= len(self.ring_radii):
                self.ring_radii.append(0.0)
                self.ring_phases.append(0.0)
                self.ring_thickness.append(1.5)
                self.broken_segments.append(0)

            band_idx = min(ring * len(bands) // self.ring_count, len(bands) - 1)
            band_val = bands[band_idx] if bands else 0.0

            base_radius = 0.21 + (ring * 0.078)
             
            pulse = self.bass_pulse if ring < 2 else self.overall_pulse * 0.45
            target_radius = base_radius + band_val * 0.27 + pulse * 0.17 + beat_strength * 0.10
             
            if target_radius > self.ring_radii[ring]:
                self.ring_radii[ring] += (target_radius - self.ring_radii[ring]) * 0.17 * sf
            else:
                self.ring_radii[ring] += (target_radius - self.ring_radii[ring]) * 0.06 * sf
             
            self.ring_phases[ring] += (0.03 + band_val * 0.11 + energy * 0.02) * sf
             
            target_thickness = 1.1 + band_val * 7.2 + beat_strength * 10.0 + energy * 2.0
            self.ring_thickness[ring] += (target_thickness - self.ring_thickness[ring]) * 0.15 * sf

    def get_ring_data(self, index: int) -> dict:
        if 0 <= index < len(self.ring_radii):
            return {
                "radius": self.ring_radii[index],
                "phase": self.ring_phases[index],
                "thickness": self.ring_thickness[index],
                "broken": self.broken_segments[index] > 0,
                "rotation": self.rotation_angle,
                "phase_state": self.phase_state,
            }
        return {
            "radius": 0,
            "phase": 0,
            "thickness": 1.5,
            "broken": False,
            "rotation": 0,
            "phase_state": None,
        }

    def trigger_beat_flash(self):
        """Pulse response."""
        for i in range(len(self.ring_radii)):
            self.ring_radii[i] += 0.035
            self.ring_thickness[i] += 3.4
        self.bass_pulse = 0.62
