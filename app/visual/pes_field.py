"""
Potential Energy Surface (PES) & Force Field Engine.
Evaluates continuous potential energy fields V(r, θ, t) and analytical gradient forces -∇V.
"""
from __future__ import annotations

import math
import numpy as np
from typing import Tuple


class PESField:
    """Calculates potential energy surfaces V(r, θ) and gradient force vectors -∇V."""

    def __init__(self):
        self.chroma_weights = np.zeros(12, dtype=float)
        self.vortex_strength = 0.5
        self.field_scale = 1.0

    def update(self, chroma_vector: np.ndarray, energy: float, flux: float):
        """Update potential energy field coefficients from real-time audio."""
        if chroma_vector is not None and len(chroma_vector) == 12:
            s = float(np.sum(chroma_vector))
            if s > 1e-5:
                self.chroma_weights = chroma_vector / s
            else:
                self.chroma_weights = np.ones(12, dtype=float) / 12.0
        else:
            self.chroma_weights = np.ones(12, dtype=float) / 12.0

        self.vortex_strength = 0.2 + energy * 0.8 + flux * 0.5
        self.field_scale = 0.8 + energy * 1.2

    def sample_potential(self, x: float, y: float, cx: float, cy: float, base_radius: float) -> float:
        """Evaluate scalar potential energy V(x, y) at position relative to center."""
        dx = x - cx
        dy = y - cy
        r = math.hypot(dx, dy)
        theta = math.atan2(dy, dx)
        if r < 1e-4:
            return 0.0

        r_norm = r / max(1.0, base_radius)

        # 12-fold Chroma potential wells
        v_chroma = 0.0
        for k in range(12):
            w = self.chroma_weights[k]
            if w <= 0.01:
                continue
            k_angle = theta * (1 + (k % 4)) + (k * math.pi / 6.0)
            v_chroma += w * math.cos(k_angle) * math.exp(-((r_norm - 1.0) ** 2) * 2.0)

        # Radial harmonic potential barrier
        v_radial = math.exp(-((r_norm - 0.8) ** 2) * 1.5) * 0.5

        return (v_chroma + v_radial) * self.field_scale

    def sample_force(self, x: float, y: float, cx: float, cy: float, base_radius: float) -> Tuple[float, float]:
        """
        Evaluate physical force vector F = -∇V(x, y) + F_vortex(x, y).
        Returns (fx, fy) in screen coordinate space.
        """
        dx = x - cx
        dy = y - cy
        r = math.hypot(dx, dy)
        if r < 1e-4:
            return (0.0, 0.0)

        # Numerical gradient evaluation via finite difference
        eps = 1.5
        v_center = self.sample_potential(x, y, cx, cy, base_radius)
        v_px = self.sample_potential(x + eps, y, cx, cy, base_radius)
        v_py = self.sample_potential(x, y + eps, cx, cy, base_radius)

        # Gradient force -∇V
        fx_grad = -(v_px - v_center) / eps * 120.0
        fy_grad = -(v_py - v_center) / eps * 120.0

        # Vortex tangential force (rotational curl)
        tangent_x = -dy / r
        tangent_y = dx / r
        vortex_mag = self.vortex_strength * 45.0 * math.exp(-((r / base_radius - 1.0) ** 2) * 1.2)

        fx = fx_grad + tangent_x * vortex_mag
        fy = fy_grad + tangent_y * vortex_mag

        return (fx, fy)
