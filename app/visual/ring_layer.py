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
        self.damage_current: List[float] = [0.0] * ring_count
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
        time: float = 0.0,
        track_seed: int = 42,
        phase_state = None,
        material = None,
        geometry = None,
    ):
        """Update ring parameters with MaterialState and GeometryControl tracking."""
        sf = dt * 60.0
        self.phase_state = phase_state
        self.material = material
        self.geometry = geometry

        self.bass_pulse += (bass * 5.8 - self.bass_pulse) * (0.30 if bass * 5.8 > self.bass_pulse else 0.11) * sf
        self.overall_pulse += (energy * 3.8 - self.overall_pulse) * (0.24 if energy * 3.8 > self.overall_pulse else 0.10) * sf

        rot_speed = 0.012 + bass * 0.06 + beat_strength * 0.09
        if geometry is not None:
            rot_speed *= (1.0 + 1.5 * geometry.circulation)
        self.rotation_angle += rot_speed * sf

        fragmentation = geometry.fragmentation if geometry is not None else 0.0
        defect_density = material.defect_density if material is not None else 0.0
        coherence = geometry.coherence if geometry is not None else 0.5
        symmetry = geometry.symmetry if geometry is not None else 0.5
        roughness = geometry.roughness if geometry is not None else 0.0

        # Deterministic damage epoch (updated every 0.25s)
        damage_epoch = int(max(0.0, time) / 0.25)

        # Update each ring
        for ring in range(self.ring_count):
            while ring >= len(self.ring_radii):
                self.ring_radii.append(0.0)
                self.ring_phases.append(0.0)
                self.ring_thickness.append(1.5)
                self.broken_segments.append(0)
                self.damage_current.append(0.0)

            band_idx = min(ring * len(bands) // self.ring_count, len(bands) - 1)
            band_val = bands[band_idx] if bands else 0.0

            base_radius = 0.21 + (ring * 0.078)
            pulse = self.bass_pulse if ring < 2 else self.overall_pulse * 0.45
            target_radius = base_radius + band_val * 0.27 + pulse * 0.17 + beat_strength * 0.10

            # Apply roughness distortion
            if roughness > 0.05:
                target_radius += math.sin(time * 8.0 + ring * 1.5) * 0.015 * roughness

            # Smooth radial interpolation with coherence coupling
            adapt_speed = 0.17 * (0.5 + 0.5 * coherence)
            if target_radius > self.ring_radii[ring]:
                self.ring_radii[ring] += (target_radius - self.ring_radii[ring]) * adapt_speed * sf
            else:
                self.ring_radii[ring] += (target_radius - self.ring_radii[ring]) * 0.06 * sf

            # Phase progression modulated by symmetry
            phase_step = (0.03 + band_val * 0.11 + energy * 0.02) * (0.7 + 0.6 * symmetry)
            self.ring_phases[ring] += phase_step * sf

            target_thickness = 1.1 + band_val * 7.2 + beat_strength * 10.0 + energy * 2.0
            self.ring_thickness[ring] += (target_thickness - self.ring_thickness[ring]) * 0.15 * sf

            # Deterministic damage target & continuous annealing healing
            if fragmentation > 0.10 or defect_density > 0.15:
                h_val = ((track_seed ^ (ring * 10007) ^ (damage_epoch * 31337)) & 0xFFFFFFFF) / 4294967295.0
                damage_target = max(0.0, min(1.0, (h_val * 0.5 + 0.5 * fragmentation + 0.5 * defect_density - 0.3)))
            else:
                damage_target = 0.0

            # Smooth annealing interpolation (healing is slower than damage creation)
            rate = 0.20 if damage_target > self.damage_current[ring] else 0.06
            self.damage_current[ring] += (damage_target - self.damage_current[ring]) * rate * sf
            self.broken_segments[ring] = 1 if self.damage_current[ring] > 0.45 else 0

    def get_ring_data(self, index: int) -> dict:
        if 0 <= index < len(self.ring_radii):
            return {
                "radius": self.ring_radii[index],
                "phase": self.ring_phases[index],
                "thickness": self.ring_thickness[index],
                "broken": self.broken_segments[index] > 0,
                "damage": self.damage_current[index],
                "rotation": self.rotation_angle,
                "phase_state": self.phase_state,
                "material": self.material,
                "geometry": self.geometry,
            }
        return {
            "radius": 0,
            "phase": 0,
            "thickness": 1.5,
            "broken": False,
            "rotation": 0,
            "phase_state": None,
            "material": None,
            "geometry": None,
        }

    def trigger_beat_flash(self):
        """Pulse response."""
        for i in range(len(self.ring_radii)):
            self.ring_radii[i] += 0.035
            self.ring_thickness[i] += 3.4
        self.bass_pulse = 0.62
