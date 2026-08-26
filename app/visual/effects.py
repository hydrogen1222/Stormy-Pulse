"""
Visual effects for the renderer.
"""
from ..dynamics.deterministic import deterministic_signed


class EffectState:
    """Manages effect states and transitions."""

    def __init__(self):
        self.beat_flash = 0.0
        self.beat_kick = 0.0
        self.shockwave_radius = 0.0
        self.shockwave_active = False
        self.shockwave_strength = 0.0
        self.camera_shake_x = 0.0
        self.camera_shake_y = 0.0
        self.global_pulse = 0.0
        self.high_energy_flash = 0.0 # New for high frequency spikes

    def trigger_beat(self, strength: float):
        """Trigger a beat effect."""
        self.beat_flash = min(1.0, self.beat_flash + strength * 0.8)
        self.beat_kick = strength
        self.shockwave_active = True
        self.shockwave_radius = 0.0
        self.shockwave_strength = strength
        self.global_pulse = min(1.0, self.global_pulse + strength * 0.5)

    def trigger_high_frequency(self, strength: float):
        """Trigger feedback for high frequency spikes."""
        self.high_energy_flash = max(self.high_energy_flash, strength)

    def update(self, dt: float = 0.016):
        """Update effect states with frame-rate-independent decay."""
        sf = dt * 60.0

        self.beat_flash *= 0.90 ** sf
        if self.beat_flash < 0.01:
            self.beat_flash = 0.0

        self.high_energy_flash *= 0.86 ** sf
        if self.high_energy_flash < 0.01:
            self.high_energy_flash = 0.0

        self.beat_kick *= 0.92 ** sf
        if self.beat_kick < 0.01:
            self.beat_kick = 0.0

        if self.shockwave_active:
            self.shockwave_radius += (14.0 + self.shockwave_strength * 12.0) * sf
            self.shockwave_strength *= 0.95 ** sf
            if self.shockwave_strength < 0.02 or self.shockwave_radius > 1500:
                self.shockwave_active = False

        self.camera_shake_x *= 0.74 ** sf
        self.camera_shake_y *= 0.74 ** sf

        self.global_pulse *= 0.94 ** sf

    def trigger_transient(self, strength: float, track_seed: int = 42, event_tick: int = 0):
        """Trigger a transient effect (camera shake) deterministically."""
        sx = deterministic_signed(track_seed, "shake_x", event_tick, 0, scale=0.5)
        sy = deterministic_signed(track_seed, "shake_y", event_tick, 0, scale=0.5)
        self.camera_shake_x = sx * strength * 4.0
        self.camera_shake_y = sy * strength * 3.0

    def add_pulse(self, strength: float):
        """Add to global pulse."""
        self.global_pulse = min(1.0, self.global_pulse + strength)


class TrailEffect:
    """Simple trail effect for particles."""

    def __init__(self, max_length: int = 20):
        self.max_length = max_length
        self.points = []

    def add_point(self, x: float, y: float):
        """Add a point to the trail."""
        self.points.append((x, y))
        if len(self.points) > self.max_length:
            self.points.pop(0)

    def clear(self):
        """Clear the trail."""
        self.points.clear()

    def get_points(self):
        """Get trail points."""
        return self.points
