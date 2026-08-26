"""
Scene manager - coordinates all visual elements.
"""
from typing import Optional, List
import math
import random
import numpy as np

from ..analysis.features import FeatureFrame, GlobalFeatureSet
from .themes import Theme, create_theme_from_features
from .effects import EffectState
from .particles import ParticleSystem
from .ring_layer import RingLayer
from .energy_core import EnergyCore
from .phase_engine import PhaseEngine
from .pes_field import PESField
from ..dynamics.field import AnalyticalPESField

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

        # V2 Dynamics Pipeline
        self.dynamics_bundle = None
        self.analytical_field = AnalyticalPESField()
        self.current_material_state = None
        self.current_context = None

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

    def set_dynamics_bundle(self, bundle):
        """Attach V2 DynamicsBundle."""
        self.dynamics_bundle = bundle
        self.analytical_field = AnalyticalPESField()

    def seek_to(self, time: float, width: float | None = None, height: float | None = None):
        """Seek scene to exact timestamp with non-recursive deterministic particle warmup."""
        target_time = max(0.0, float(time))
        w_w = width if width is not None else getattr(self, "viewport_width", 1280.0)
        w_h = height if height is not None else getattr(self, "viewport_height", 720.0)

        self.time = target_time
        self.effects = EffectState()
        self.particles.clear()
        self.last_onset_time = 0.0
        self.last_beat_time = 0.0
        self.ring_layer = RingLayer(ring_count=self.ring_layer.ring_count)
        self.energy_core = EnergyCore()

        if self.dynamics_bundle is not None:
            mat = self.dynamics_bundle.material_trajectory.get_state_at_time(target_time)
            ctx = self.dynamics_bundle.context_builder.at(target_time)
            self.current_material_state = mat
            self.current_context = ctx
            self.current_geometry_control = mat.geometry_control if mat is not None else None
            self.analytical_field.update(ctx, mat)

            # Non-recursive warmup short transient visual state over 2.0 seconds
            warmup_start = max(0.0, target_time - 2.0)
            if target_time > 0.0 and hasattr(self.dynamics_bundle.context_builder.cache, "get_frame_at_time"):
                cache = self.dynamics_bundle.context_builder.cache
                w_dt = 0.033
                w_times = np.arange(warmup_start, target_time, w_dt)

                # Set initial warmup time before simulation step
                self.time = warmup_start
                for wt in w_times:
                    frame = cache.get_frame_at_time(wt)
                    if frame is not None:
                        self._update_internal(frame, is_playing=True, width=w_w, height=w_h, dt=w_dt, detect_seek=False)

            # Re-confirm target state
            self.time = target_time
            self.current_material_state = mat
            self.current_context = ctx
            self.current_geometry_control = mat.geometry_control if mat is not None else None

    def load_track_features(self, global_features: GlobalFeatureSet):
        """Load global features and create theme."""
        self.global_features = global_features
        self.theme = create_theme_from_features(global_features)
        self.ring_layer.ring_count = self.theme.ring_count

    def update(self, frame: FeatureFrame, is_playing: bool, width: float, height: float, dt: float = 0.016):
        """Public update interface for scene rendering."""
        self._update_internal(frame, is_playing, width, height, dt, detect_seek=True)

    def _update_internal(
        self,
        frame: FeatureFrame,
        is_playing: bool,
        width: float,
        height: float,
        dt: float = 0.016,
        detect_seek: bool = True,
    ):
        """Internal scene update core with optional seek detection."""
        self.viewport_width = float(width)
        self.viewport_height = float(height)
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

        # Handle seeking backwards (disabled during warmup loops)
        if detect_seek and frame.time < self.time - 0.5:
            self.seek_to(frame.time, width=width, height=height)

        # Keep time perfectly synced to the audio feature frame time
        self.time = frame.time

        # Query V2 Dynamics Bundle if attached
        active_material = None
        active_pes = self.pes_field

        if self.dynamics_bundle is not None:
            ctx = self.dynamics_bundle.context_builder.at(self.time)
            mat = self.dynamics_bundle.material_trajectory.get_state_at_time(self.time)
            self.current_context = ctx
            self.current_material_state = mat
            self.analytical_field.update(ctx, mat)
            active_material = mat
            active_pes = self.analytical_field

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
        self.is_on_beat = beat > 0.6
        self.beat_strength = beat_strength

        beat_event_triggered = False
        onset_event_triggered = False

        if self.is_on_beat and not was_on_beat:
            beat_event_triggered = True
            self.last_beat_time = self.time
            self.effects.trigger_beat(max(0.7, self.beat_strength))

            burst_count = int(140 + self.beat_strength * 320)
            self.particles.emit_burst(
                center_x, center_y,
                min(burst_count, self.particles.max_particles - self.particles.get_count()),
                self.theme.hue_base if self.theme else 200,
                max(0.7, self.beat_strength),
                chaos,
                energy
            )
            self.ring_layer.trigger_beat_flash()

        if onset > 0.75 and (self.time - self.last_onset_time) > 0.1 and (self.time - self.last_beat_time) > 0.2:
            onset_event_triggered = True
            self.last_onset_time = self.time
            self.effects.trigger_transient(onset)

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

        # Background particles emission
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

        # Legacy fallback if no V2 dynamics bundle attached
        if self.dynamics_bundle is None:
            self.phase_state = self.phase_engine.update(
                rms=rms, bass=bass, mid=mid, high=high, onset_strength=onset,
                flatness=flatness, harmonic_e=getattr(frame, "harmonic_e", 0.5),
                percussive_e=getattr(frame, "percussive_e", 0.5), flux=getattr(frame, "flux", 0.0), dt=dt,
            )
            self.pes_field.update(
                chroma_vector=getattr(frame, "chroma_vector", None),
                energy=rms * 0.7 + bass * 0.3, flux=getattr(frame, "flux", 0.0),
            )

        # Update all visual elements with physical fields & active material
        base_radius = getattr(self.energy_core, "size", 200.0)
        self.particles.update(
            center_x, center_y, chaos, self.effects.beat_flash, energy, dt,
            pes_field=active_pes, base_radius=base_radius, material=active_material
        )

        self.current_geometry_control = active_material.geometry_control if active_material is not None else None

        ring_cnt = self.ring_layer.ring_count
        bands = [bass] * (ring_cnt // 3) + [mid] * (ring_cnt // 3) + [high] * (ring_cnt - 2 * (ring_cnt // 3))
        seed = self.dynamics_bundle.track_seed if self.dynamics_bundle is not None else 42
        self.ring_layer.update(
            bands, bass, mid, high, energy, chaos,
            self.effects.beat_flash, self.beat_strength, self.is_on_beat,
            tempo, dt, time=self.time, track_seed=seed, phase_state=self.phase_state,
            material=active_material, geometry=self.current_geometry_control
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
        self.dynamics_bundle = None
        self.analytical_field = AnalyticalPESField()
        self.current_material_state = None
        self.current_context = None
