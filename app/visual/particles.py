"""
Particle system for visualization.
"""
import math
import random
from typing import List, Tuple
from dataclasses import dataclass


@dataclass
class Particle:
    """Represents a single particle."""

    x: float
    y: float
    vx: float
    vy: float
    size: float
    life: float
    max_life: float
    hue: float
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
    ):
        """Emit particles at a position."""
        count = int(max(1, count * 1.35))
        for _ in range(count):
            if len(self.particles) >= self.max_particles:
                break

            angle = random.random() * math.pi * 2
            
            if type == "spark":
                speed = 8 + energy * 12 + random.random() * 6
                size = 1.0 + random.random() * 1.8
                life = 25 + random.random() * 20
                hue = hue_base + random.uniform(-15, 15)
                vy_factor = 0.7
            elif type == "dust":
                speed = 0.28 + energy * 1.1 + random.random() * 0.45
                size = 0.55 + random.random() * 0.95
                life = 120 + random.random() * 80
                hue = hue_base + random.uniform(-30, 30)
                vy_factor = 0.3
            elif type == "star":
                speed = 0.2 + energy * 1.0 + random.random() * 0.5
                size = 1.0 + random.random() * 2.0
                life = 200 + random.random() * 100
                hue = hue_base + random.uniform(-60, 60)
                vy_factor = 0.5
            else: 
                speed = 2.8 + energy * 8 + random.random() * 4.2
                size = 1.4 + energy * 4.8 + random.random() * 2.8
                life = 100 + random.random() * 60
                hue = hue_base + random.uniform(-20, 20)
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
                is_spark=(type == "spark"),
                trail=[]
            )
            particle.trail.append((x, y))
            self.particles.append(particle)

    def emit_burst(
        self, x: float, y: float, count: int, hue_base: float, beat_strength: float, chaos: float = 0.3, energy: float = 0.5
    ):
        """Emit a refined radial burst of data-point particles."""
        count = int(max(1, count * 1.6))
        for i in range(count):
            angle = (i / count) * math.pi * 2
            angle += (random.random() - 0.5) * 0.2

            speed = 9 + beat_strength * 18 + energy * 7 + random.random() * 7
            speed *= (1 + chaos * 0.6)
            
            life = 15 + random.random() * 25
            
            hue = hue_base + random.uniform(-10, 30)
            size = 1.4 + beat_strength * 5 + random.random() * 2.2

            particle = Particle(
                x=x,
                y=y,
                vx=math.cos(angle) * speed,
                vy=math.sin(angle) * speed,
                size=size,
                life=life,
                max_life=life,
                hue=hue,
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

            p.vx *= (1.0 - (1.0 - drag) * sf)
            p.vy *= (1.0 - (1.0 - drag) * sf)

            p.x += p.vx * sf
            p.y += p.vy * sf

            p.life -= (1.2 if p.is_spark else 0.5) * sf

            if p.life <= 0:
                to_remove.append(i)

        for i in reversed(to_remove):
            self.particles.pop(i)

    def clear(self):
        """Clear all particles."""
        self.particles.clear()

    def get_particles(self) -> List[Particle]:
        """Get all particles."""
        return self.particles

    def get_count(self) -> int:
        """Get particle count."""
        return len(self.particles)
