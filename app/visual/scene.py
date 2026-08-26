"""
Scene manager - coordinates all visual elements.
"""
from typing import Optional, List
import math
import random

from ..analysis.features import FeatureFrame, GlobalFeatureSet
from .themes import Theme, create_theme_from_features
from .effects import EffectState
from .particles import ParticleSystem
from .ring_layer import RingLayer
from .energy_core import EnergyCore
from .phase_engine import PhaseEngine
from .pes_field import PESField

DEBUG_EVENT_SYNC = False


class Scene:
    """Manages the visual scene and its elements."""

    def __init__(self):
        # Visual DNA
        self.theme: Optional[Theme] = None
        self.global_features: Optional[GlobalFeatureSet] = None

        # Condensed Matter Physical Dynamics Engines
        self.phase_engine = PhaseEngine()
        self.pes_field = PESField()
        self.phase_state = None

        # Visual elements
        self.effects = EffectState()
        self.particles = ParticleSystem(max_particles=1600)
        self.ring_layer = RingLayer(ring_count=5)
        self.energy_core = EnergyCore()

        # Current frame data
        self.current_frame: Optional[FeatureFrame] = None
        self.is_on_beat = False
        self.beat_strength = 0.0

        # Time tracking
        self.time = 0.0
        self.vortex_angle = 0.0
        self.last_onset_time = 0.0
        self.last_beat_time = 0.0
        self.last_update_center = (0.0, 0.0)
        self.audio_drive = {
            "rms": 0.0,
            "bass": 0.0,
            "mid": 0.0,
            "high": 0.0,
            "onset": 0.0,
            "beat": 0.0,
            "centroid": 0.0,
            "rolloff": 0.0,
            "flatness": 0.0,
            "sparkle": 0.0,
            "pressure": 0.0,
            "density": 0.0,
            "tension": 0.0,
        }

    def _smooth_env(
        self,
        current: float,
        target: float,
        attack: float,
        release: float,
        dt: float,
    ) -> float:
        sf = dt * 60.0
        rate = attack if target > current else release
        return current + (target - current) * min(rate * sf, 1.0)

    def load_track_features(self, global_features: GlobalFeatureSet):
        """Load global features and create theme."""
        self.global_features = global_features
        self.theme = create_theme_from_features(global_features)
        self.ring_layer.ring_count = self.theme.ring_count

    def update(self, frame: FeatureFrame, is_playing: bool, width: float, height: float, dt: float = 0.016):
        """Update the scene based on current audio features."""
        center_x = width / 2
        center_y = height / 2
        self.last_update_center = (center_x, center_y)

        if not is_playing or not frame:
            # Idle animation
            self.time += dt
            self.current_frame = None
            self.vortex_angle += 1.5 * dt

            # Update layers with idle values
            ring_cnt = self.ring_layer.ring_count
            self.particles.update(center_x, center_y, 0.2, 0.0, 0.2, dt)
            self.ring_layer.update([0.1]*ring_cnt, 0.1, 0.1, 0.1, 0.2, 0.2, 0, 0, False, 120, dt)
            self.energy_core.update(0.05, 0.1, 0.2, 0.0, dt)
            self.effects.update(dt)
            for key in list(self.audio_drive.keys()):
                self.audio_drive[key] *= 0.92
            return

        self.current_frame = frame
        
        # Handle seeking backwards
        if frame.time < self.time:
            self.last_onset_time = 0.0
            
        # Keep time perfectly synced to the audio feature frame time
        self.time = frame.time

        # Extract features
        rms = frame.rms
        bass = frame.bass
        mid = frame.mid
        high = frame.high
        onset = frame.onset_strength
        centroid = frame.spectral_centroid
        rolloff = frame.spectral_rolloff
        flatness = frame.spectral_flatness
        beat = frame.beat
        beat_strength = frame.beat_strength

        # Get theme values
        chaos = self.global_features.chaos if self.global_features else 0.3
        energy = self.global_features.energy if self.global_features else 0.5
        density = self.global_features.density if self.global_features else 0.5
        brightness = self.global_features.brightness if self.global_features else 0.5
        tempo = self.global_features.tempo if self.global_features else 120.0

        centroid_norm = max(0.0, min(1.0, float(centroid)))
        rolloff_norm = max(0.0, min(1.0, float(rolloff)))
        flatness_norm = max(0.0, min(1.0, flatness))
        sparkle_target = max(0.0, min(1.0, brightness * 0.58 + high * 0.42))
        pressure_target = max(0.0, min(1.0, bass * 0.58 + rms * 0.24 + beat_strength * 0.30))
        density_target = max(0.0, min(1.0, density * 0.66 + rms * 0.20 + max(onset - 0.2, 0.0) * 0.20))
        tension_target = max(0.0, min(1.0, chaos * 0.54 + onset * 0.30 + beat_strength * 0.24))

        self.audio_drive["rms"] = self._smooth_env(self.audio_drive["rms"], rms, 0.22, 0.07, dt)
        self.audio_drive["bass"] = self._smooth_env(self.audio_drive["bass"], bass, 0.20, 0.07, dt)
        self.audio_drive["mid"] = self._smooth_env(self.audio_drive["mid"], mid, 0.18, 0.07, dt)
        self.audio_drive["high"] = self._smooth_env(self.audio_drive["high"], high, 0.22, 0.09, dt)
        self.audio_drive["onset"] = self._smooth_env(self.audio_drive["onset"], max(onset, beat_strength * 0.8), 0.34, 0.11, dt)
        self.audio_drive["beat"] = self._smooth_env(self.audio_drive["beat"], beat_strength, 0.36, 0.13, dt)
        self.audio_drive["centroid"] = self._smooth_env(self.audio_drive["centroid"], centroid_norm, 0.18, 0.08, dt)
        self.audio_drive["rolloff"] = self._smooth_env(self.audio_drive["rolloff"], rolloff_norm, 0.16, 0.07, dt)
        self.audio_drive["flatness"] = self._smooth_env(self.audio_drive["flatness"], flatness_norm, 0.12, 0.08, dt)
        self.audio_drive["sparkle"] = self._smooth_env(self.audio_drive["sparkle"], sparkle_target, 0.16, 0.07, dt)
        self.audio_drive["pressure"] = self._smooth_env(self.audio_drive["pressure"], pressure_target, 0.20, 0.09, dt)
        self.audio_drive["density"] = self._smooth_env(self.audio_drive["density"], density_target, 0.14, 0.06, dt)
        self.audio_drive["tension"] = self._smooth_env(self.audio_drive["tension"], tension_target, 0.18, 0.08, dt)

        # Update vortex speed based on energy
        vortex_speed = (2.0 + bass * 6.0 + self.effects.beat_flash * 10.0) * dt
        self.vortex_angle += vortex_speed * (1 + chaos)

        # --- EVENT DRIVEN RESPONSE ---
        was_on_beat = self.is_on_beat
        # Use a strict threshold to avoid sticky beat states causing missed triggers
        self.is_on_beat = beat > 0.6
        self.beat_strength = beat_strength

        beat_event_triggered = False
        onset_event_triggered = False

        if self.is_on_beat and not was_on_beat:
            beat_event_triggered = True
            self.last_beat_time = self.time
            # Beat just triggered: massive response
            self.effects.trigger_beat(max(0.7, self.beat_strength))

            # Massive burst on beat
            burst_count = int(140 + self.beat_strength * 320)
            self.particles.emit_burst(
                center_x, center_y,
                min(burst_count, self.particles.max_particles - self.particles.get_count()),
                self.theme.hue_base if self.theme else 200,
                max(0.7, self.beat_strength),
                chaos,
                energy
            )

            # Optional: activate random ring segment or flash
            self.ring_layer.trigger_beat_flash()

        # Refractory period for onset to prevent storm (100ms)
        # Also prevent onset triggering if a beat happened recently (200ms)
        if onset > 0.75 and (self.time - self.last_onset_time) > 0.1 and (self.time - self.last_beat_time) > 0.2:
            onset_event_triggered = True
            self.last_onset_time = self.time
            # Transient / Onset event (distinct from beat)
            self.effects.trigger_transient(onset)

            # Short, fast sparks (distinct from beat burst)
            spark_count = int(30 + onset * 70)
            for _ in range(spark_count):
                angle = random.random() * math.pi * 2
                radius = self.energy_core.size * 0.9
                self.particles.emit(
                    center_x + math.cos(angle) * radius,
                    center_y + math.sin(angle) * radius,
                    1, self.theme.hue_base if self.theme else 200,
                    chaos, energy * 2.0, type="spark"
                )

        hf_trigger = max(high - 0.52, 0.0) * 1.15 + max(centroid_norm - 0.42, 0.0) * 0.8
        if onset_event_triggered:
            hf_trigger = max(hf_trigger, onset * 0.85)
        if hf_trigger > 0.16:
            self.effects.trigger_high_frequency(min(1.0, hf_trigger))

        # --- LOGGING VISUAL EVENTS (As requested for debugging) ---
        if DEBUG_EVENT_SYNC and (beat_event_triggered or onset_event_triggered):
            event_type = "BEAT_HIT" if beat_event_triggered else "ONSET_HIT"
            # We don't print every frame to avoid spam, only on distinct events
            print(f"[EventSync] Time: {self.time:.2f}s | {event_type} | rms: {rms:.2f} bass: {bass:.2f} | "
                  f"beat_str: {beat_strength:.2f} onset: {onset:.2f}")
        # --- CONTINUOUS DRIVEN RESPONSE ---
        # Emit occasional background particles
        if self.particles.get_count() < self.particles.max_particles:
            emit_chance = rms * 0.46 + high * 0.38 + self.effects.beat_flash * 0.15
            if random.random() < emit_chance:
                angle = random.random() * math.pi * 2
                radius = self.energy_core.size * 0.6
                self.particles.emit(
                    center_x + math.cos(angle) * radius,
                    center_y + math.sin(angle) * radius,
                    int(2 + emit_chance * 10), self.theme.hue_base if self.theme else 200,
                    chaos, energy, type="normal"
                )
            if random.random() < chaos * 0.34 + high * 0.12:
                # Ambient dust
                self.particles.emit(
                    center_x + (random.random() - 0.5) * 600,
                    center_y + (random.random() - 0.5) * 600,
                    int(2 + chaos * 8 + high * 4),
                    self.theme.hue_base if self.theme else 200,
                    chaos, energy, type="dust"
                )

        # Update Condensed Matter Phase Engine & PES Field
        self.phase_state = self.phase_engine.update(
            rms=rms,
            bass=bass,
            mid=mid,
            high=high,
            onset_strength=onset,
            flatness=flatness,
            harmonic_e=getattr(frame, "harmonic_e", 0.5),
            percussive_e=getattr(frame, "percussive_e", 0.5),
            flux=getattr(frame, "flux", 0.0),
            dt=dt,
        )
        local_energy = rms * 0.7 + bass * 0.3
        self.pes_field.update(
            chroma_vector=getattr(frame, "chroma_vector", None),
            energy=local_energy,
            flux=getattr(frame, "flux", 0.0),
        )

        # Update all visual elements with physical fields
        base_radius = getattr(self.energy_core, "size", 200.0)
        self.particles.update(
            center_x, center_y, chaos, self.effects.beat_flash, energy, dt,
            pes_field=self.pes_field, base_radius=base_radius
        )
        
        # Intelligent band distribution & Phase State passing
        ring_cnt = self.ring_layer.ring_count
        bands = [bass] * (ring_cnt // 3) + [mid] * (ring_cnt // 3) + [high] * (ring_cnt - 2 * (ring_cnt // 3))
        self.ring_layer.update(
            bands, bass, mid, high, energy, chaos,
            self.effects.beat_flash, self.beat_strength, self.is_on_beat,
            tempo, dt, phase_state=self.phase_state
        )

        self.energy_core.update(rms, bass, energy, self.beat_strength, dt)
        self.effects.update(dt)

    def get_camera_offset(self) -> tuple:
        """Get camera shake offset."""
        return (self.effects.camera_shake_x, self.effects.camera_shake_y)

    def get_audio_drive(self) -> dict:
        """Get smoothed audio-reactive controls for rendering."""
        return self.audio_drive

    def get_center(self, width: float, height: float) -> tuple:
        """Get center with camera offset."""
        cx = width / 2 + self.effects.camera_shake_x
        cy = height / 2 + self.effects.camera_shake_y
        return (cx, cy)

    def reset(self):
        """Reset the scene."""
        self.theme = None
        self.global_features = None
        self.current_frame = None
        self.is_on_beat = False
        self.beat_strength = 0.0
        self.time = 0.0
        self.vortex_angle = 0.0
        self.last_onset_time = 0.0
        self.last_beat_time = 0.0
        self.last_update_center = (0.0, 0.0)
        for key in list(self.audio_drive.keys()):
            self.audio_drive[key] = 0.0
        self.particles.clear()
        self.effects = EffectState()
        self.ring_layer = RingLayer(ring_count=5)
        self.energy_core = EnergyCore()
        self.phase_engine = PhaseEngine()
        self.pes_field = PESField()
        self.phase_state = None
