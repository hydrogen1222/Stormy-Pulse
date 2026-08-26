"""
Particle system for visualization.
"""
import math
import random
from typing import List, Tuple
from dataclasses import dataclass
from ..dynamics.deterministic import (
    deterministic_float,
    deterministic_uniform,
    deterministic_signed,
)


@dataclass
class Particle:
    """Represents a single particle with stable ID."""

    x: float
    y: float
    vx: float
    vy: float
    size: float
    life: float
    max_life: float
    hue: float
    particle_id: int = 0
    is_spark: bool = False
    trail: List[Tuple[float, float]] = None

    def __post_init__(self):
        if self.trail is None:
            self.trail = []


class ParticleSystem:
    """Manages particles for visualization with Scientific Precision."""

    def __init__(self, max_particles: int = 3000): 
        self.max_particles = max_particles
        self.particles: List[Particle] = []
        self.next_particle_id = 0

    def clear(self):
        """Clear all active particles."""
        self.particles.clear()
        self.next_particle_id = 0

    def emit(
        self,
        x: float,
        y: float,
        count: int,
        hue_base: float,
        chaos: float = 0.3,
        energy: float = 0.5,
        is_spark: bool = False,
        type: str = "normal", 
        track_seed: int = 42,
    ):
        """Emit particles at a position with deterministic pseudo-random properties."""
        count = int(max(1, count * 1.35))
        for idx in range(count):
            if len(self.particles) >= self.max_particles:
                break

            pid = self.next_particle_id
            self.next_particle_id += 1

            r0 = deterministic_float(track_seed, f"p_angle_{type}", pid, idx)
            r1 = deterministic_float(track_seed, f"p_speed_{type}", pid, idx)
            r2 = deterministic_float(track_seed, f"p_size_{type}", pid, idx)
            r3 = deterministic_float(track_seed, f"p_life_{type}", pid, idx)
            r4 = deterministic_signed(track_seed, f"p_hue_{type}", pid, idx, scale=1.0)

            angle = r0 * math.pi * 2
            
            if type == "spark":
                speed = 8 + energy * 12 + r1 * 6
                size = 1.0 + r2 * 1.8
                life = 25 + r3 * 20
                hue = hue_base + r4 * 15
                vy_factor = 0.7
            elif type == "dust":
                speed = 0.28 + energy * 1.1 + r1 * 0.45
                size = 0.55 + r2 * 0.95
                life = 120 + r3 * 80
                hue = hue_base + r4 * 30
                vy_factor = 0.3
            elif type == "star":
                speed = 0.2 + energy * 1.0 + r1 * 0.5
                size = 1.0 + r2 * 2.0
                life = 200 + r3 * 100
                hue = hue_base + r4 * 60
                vy_factor = 0.5
            else: 
                speed = 2.8 + energy * 8 + r1 * 4.2
                size = 1.4 + energy * 4.8 + r2 * 2.8
                life = 100 + r3 * 60
                hue = hue_base + r4 * 20
                vy_factor = 0.6
            
            speed *= (1 + chaos * 0.6)
            size *= (1 + energy * 0.6)
            life *= (1 + chaos * 0.3)

            particle = Particle(
                x=x,
                y=y,
                vx=math.cos(angle) * speed,
                vy=math.sin(angle) * speed * vy_factor,
                size=size,
                life=life,
                max_life=life,
                hue=hue,
                particle_id=pid,
                is_spark=(type == "spark"),
                trail=[]
            )
            particle.trail.append((x, y))
            self.particles.append(particle)

    def emit_burst(
        self,
        x: float,
        y: float,
        count: int,
        hue_base: float,
        beat_strength: float,
        chaos: float = 0.3,
        energy: float = 0.5,
        track_seed: int = 42,
    ):
        """Emit a refined radial burst of data-point particles deterministically."""
        count = int(max(1, count * 1.6))
        for i in range(count):
            pid = self.next_particle_id
            self.next_particle_id += 1

            r_angle = deterministic_signed(track_seed, "burst_angle", pid, i, scale=0.1)
            r_speed = deterministic_float(track_seed, "burst_speed", pid, i)
            r_life = deterministic_float(track_seed, "burst_life", pid, i)
            r_hue = deterministic_signed(track_seed, "burst_hue", pid, i, scale=20.0)
            r_size = deterministic_float(track_seed, "burst_size", pid, i)

            angle = (i / count) * math.pi * 2 + r_angle
            speed = (9 + beat_strength * 18 + energy * 7 + r_speed * 7) * (1 + chaos * 0.6)
            life = 15 + r_life * 25
            hue = hue_base + r_hue
            size = 1.4 + beat_strength * 5 + r_size * 2.2

            particle = Particle(
                x=x,
                y=y,
                vx=math.cos(angle) * speed,
                vy=math.sin(angle) * speed,
                size=size,
                life=life,
                max_life=life,
                hue=hue,
                particle_id=pid,
                is_spark=True,
                trail=[]
            )
            self.particles.append(particle)

    def update(
        self,
        center_x: float,
        center_y: float,
        chaos: float = 0.3,
        beat_pulse: float = 0.0,
        energy: float = 0.5,
        dt: float = 0.016,
        pes_field=None,
        base_radius: float = 200.0,
        material=None,
    ):
        """Update particles with smooth drag physics and PES field forces."""
        to_remove = []
        sf = dt * 60.0

        for i, p in enumerate(self.particles):
            p.trail.append((p.x, p.y))
            max_trail = 5 if p.is_spark else 10
            if len(p.trail) > max_trail:
                p.trail.pop(0)

            # Apply PES Force Field if available
            if pes_field is not None:
                try:
                    fx, fy = pes_field.sample_force(p.x, p.y, center_x, center_y, base_radius, material=material)
                except TypeError:
                    fx, fy = pes_field.sample_force(p.x, p.y, center_x, center_y, base_radius)
                p.vx += fx * 0.08 * sf
                p.vy += fy * 0.08 * sf

            if material is not None:
                drag = material.w_crystalline * 0.88 + material.w_hydrodynamic * 0.94 + material.w_plasma * 0.97
            else:
                drag = 0.88 if p.is_spark else 0.94

            drag_factor = max(0.01, min(0.999, drag)) ** sf
            p.vx *= drag_factor
            p.vy *= drag_factor

            p.x += p.vx * sf
            p.y += p.vy * sf

            p.life -= (1.2 if p.is_spark else 0.5) * sf

            if p.life <= 0:
                to_remove.append(i)

        for i in reversed(to_remove):
            self.particles.pop(i)

    def get_particles(self) -> List[Particle]:
        """Get all particles."""
        return self.particles

    def get_count(self) -> int:
        """Get particle count."""
        return len(self.particles)
