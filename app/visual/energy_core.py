"""
Energy core element - the heart of the visualization.
"""
import math
import random


class EnergyCore:
    """Represents the central energy hub of the visualization."""

    def __init__(self):
        self.size = 20.0
        self.brightness = 0.5
        self.rotation = 0.0
        self.pulse = 0.0
        self.glow_radius = 50.0
        self.vortex_speed = 1.0
        self.particles_rotation = 0.0
        self.inner_rotation = 0.0
        self.outer_rotation = 0.0
        self.breath_phase = 0.0
        self.rms_env = 0.0
        self.bass_env = 0.0
        self.energy_env = 0.0
        self.beat_env = 0.0
        
        # Static offsets for variety
        self.segments_offset = [random.uniform(0, math.pi * 2) for _ in range(3)]

    def update(self, rms: float, bass: float, energy: float, beat_strength: float, dt: float):
        """Update core state with a crisp but restrained response."""
        sf = dt * 60.0

        def smooth(current: float, target: float, attack: float, release: float) -> float:
            rate = attack if target > current else release
            return current + (target - current) * min(rate * sf, 1.0)

        self.rms_env = smooth(self.rms_env, rms, 0.24, 0.08)
        self.bass_env = smooth(self.bass_env, bass, 0.22, 0.07)
        self.energy_env = smooth(self.energy_env, energy, 0.16, 0.05)
        self.beat_env = smooth(self.beat_env, beat_strength, 0.36, 0.09)

        self.rotation += (0.034 + self.rms_env * 0.09 + self.energy_env * 0.06) * sf
        self.breath_phase += (0.018 + self.energy_env * 0.022 + self.bass_env * 0.014) * sf
        breathing = math.sin(self.breath_phase) * (2.8 + self.energy_env * 2.2)
        beat_push = self.beat_env * (34.0 + self.bass_env * 18.0)

        target_size = 66.0 + self.rms_env * 118.0 + self.bass_env * 60.0 + beat_push + breathing
        if target_size > self.size:
            self.size += (target_size - self.size) * 0.16 * sf
        else:
            self.size += (target_size - self.size) * 0.07 * sf
             
        target_brightness = min(
            1.18,
            0.72 + self.energy_env * 0.22 + self.beat_env * 0.24 + self.rms_env * 0.10,
        )
        self.brightness += (target_brightness - self.brightness) * 0.14 * sf
        
        self.inner_rotation += (0.045 + self.bass_env * 0.10 + self.beat_env * 0.12) * sf
        self.outer_rotation -= (0.032 + self.energy_env * 0.07 + self.beat_env * 0.09) * sf
        
        breath_pulse = 0.5 + 0.5 * math.sin(self.breath_phase * 1.35)
        self.pulse = 0.06 + breath_pulse * 0.08 + self.beat_env * 0.18
        self.glow_radius = self.size * (0.90 + self.pulse * 0.14)

    def get_state(self) -> dict:
        """Return current state for rendering."""
        return {
            "size": max(self.size, 0.0),
            "brightness": max(0.0, min(self.brightness, 1.18)),
            "rotation": self.rotation,
            "inner_rotation": self.inner_rotation,
            "outer_rotation": self.outer_rotation,
            "glow_radius": max(self.glow_radius, 0.0),
            "pulse": max(0.0, min(self.pulse, 1.0)),
            "segments_offset": self.segments_offset
        }
