"""
Analytical Circle-of-Fifths Potential Energy Surface (PES) & Force Decomposition Field.
Uses Fourier angular mode compression (m=1..4) with exact analytical gradients -∇V
and phase-weighted force decomposition (potential, curl, stochastic).
"""
from __future__ import annotations

import math
import numpy as np
from typing import Tuple, Optional

from .context import VisualContext
from .material import MaterialState


class AnalyticalPESField:
    """Fourier-compressed analytical Circle-of-Fifths PES field engine."""

    def __init__(self):
        # Circle-of-fifths angle mapping for 12 pitch classes: (7 * k) % 12
        self.pitch_angles = np.array([2.0 * math.pi * ((7 * k) % 12) / 12.0 for k in range(12)], dtype=float)
        self.fourier_c_re = np.zeros(5, dtype=float)
        self.fourier_c_im = np.zeros(5, dtype=float)
        self.field_gain = 1.0
        self.tonal_confidence = 0.0

    def update(self, ctx: VisualContext, material: Optional[MaterialState] = None):
        """Update Fourier mode coefficients from VisualContext and MaterialState."""
        chroma = ctx.chroma if ctx.chroma is not None and len(ctx.chroma) == 12 else np.ones(12) / 12.0
        chroma_sum = float(np.sum(chroma))

        if chroma_sum > 1e-5:
            w_k = chroma / chroma_sum
        else:
            w_k = np.ones(12, dtype=float) / 12.0

        self.tonal_confidence = 0.0 if math.isnan(ctx.tonal_confidence) else float(ctx.tonal_confidence)
        self.energy_fast = 0.0 if math.isnan(ctx.energy_fast) else float(ctx.energy_fast)
        self.potential_gain = (0.5 + 1.2 * self.energy_fast) * self.tonal_confidence
        self.curl_gain = 0.5 + 1.2 * self.energy_fast

        # Compute Fourier coefficients C_m = sum_k w_k * exp(-i * m * theta_k) for m=1..4
        for m in range(1, 5):
            angles = m * self.pitch_angles
            self.fourier_c_re[m] = float(np.sum(w_k * np.cos(angles)))
            self.fourier_c_im[m] = float(np.sum(w_k * np.sin(angles)))

    def sample_potential(self, x: float, y: float, cx: float, cy: float, base_radius: float) -> float:
        """Evaluate scalar potential energy V(x,y) analytically."""
        dx = x - cx
        dy = y - cy
        r = math.hypot(dx, dy)
        theta = math.atan2(dy, dx)

        if r < 1e-4:
            return 0.0

        r_norm = r / max(1.0, base_radius)

        # Fourier angular potential mode summation
        v_angular = 0.0
        for m in range(1, 5):
            c_re = self.fourier_c_re[m]
            c_im = self.fourier_c_im[m]
            v_angular += (c_re * math.cos(m * theta) - c_im * math.sin(m * theta))

        radial_envelope = math.exp(-((r_norm - 1.0) ** 2) * 2.0)
        v_radial_barrier = math.exp(-((r_norm - 0.75) ** 2) * 1.5) * 0.5

        return (v_angular * radial_envelope + v_radial_barrier) * self.potential_gain

    def sample_force(
        self,
        x: float,
        y: float,
        cx: float,
        cy: float,
        base_radius: float,
        material: Optional[MaterialState] = None,
    ) -> Tuple[float, float]:
        """
        Evaluate physical force vector with exact analytical gradient -∇V
        and physical force decomposition (potential, curl, stochastic).
        """
        dx = x - cx
        dy = y - cy
        r = math.hypot(dx, dy)
        if r < 1e-4:
            return (0.0, 0.0)

        theta = math.atan2(dy, dx)
        r_norm = r / max(1.0, base_radius)

        # Analytical partial derivatives ∂V/∂r and ∂V/∂θ
        v_ang = 0.0
        dv_ang_dtheta = 0.0
        for m in range(1, 5):
            c_re = self.fourier_c_re[m]
            c_im = self.fourier_c_im[m]
            v_ang += (c_re * math.cos(m * theta) - c_im * math.sin(m * theta))
            dv_ang_dtheta += m * (-c_re * math.sin(m * theta) - c_im * math.cos(m * theta))

        rad_env = math.exp(-((r_norm - 1.0) ** 2) * 2.0)
        d_rad_env = -4.0 * (r_norm - 1.0) * rad_env / max(1.0, base_radius)

        rad_bar = math.exp(-((r_norm - 0.75) ** 2) * 1.5) * 0.5
        d_rad_bar = -3.0 * (r_norm - 0.75) * rad_bar / max(1.0, base_radius)

        dv_dr = (v_ang * d_rad_env + d_rad_bar) * self.potential_gain
        dv_dtheta = (dv_ang_dtheta * rad_env) * self.potential_gain

        # Polar force components F_r = -∂V/∂r, F_θ = -(1/r) ∂V/∂θ
        fr = -dv_dr * 180.0
        ftheta = -(dv_dtheta / max(1.0, r)) * 180.0

        # Convert polar force to Cartesian (fx_pot, fy_pot)
        cos_t = dx / r
        sin_t = dy / r
        fx_pot = fr * cos_t - ftheta * sin_t
        fy_pot = fr * sin_t + ftheta * cos_t

        # Tangential rotational curl force (independent of tonal confidence)
        tangent_x = -sin_t
        tangent_y = cos_t
        vortex_mag = 40.0 * self.curl_gain * math.exp(-((r_norm - 1.0) ** 2) * 1.2)
        fx_curl = tangent_x * vortex_mag
        fy_curl = tangent_y * vortex_mag

        # Plasma stochastic scattering force
        plasma_mag = 50.0 * (0.4 + 1.2 * (material.excitation if material else 0.5))
        fx_plas = cos_t * plasma_mag * (math.sin(r_norm * 8.0 + theta * 3.0))
        fy_plas = sin_t * plasma_mag * (math.cos(r_norm * 8.0 - theta * 3.0))

        # Phase weights force decomposition
        if material is not None:
            w_c = material.w_crystalline
            w_f = material.w_hydrodynamic
            w_p = material.w_plasma
        else:
            w_c, w_f, w_p = 0.5, 0.4, 0.1

        fx = w_c * 1.5 * fx_pot + w_f * 1.8 * fx_curl + w_p * 2.0 * fx_plas
        fy = w_c * 1.5 * fy_pot + w_f * 1.8 * fy_curl + w_p * 2.0 * fy_plas

        return (fx, fy)
