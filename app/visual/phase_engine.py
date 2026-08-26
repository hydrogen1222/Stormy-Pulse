"""
Condensed Matter Physical Phase Engine.
Calculates real-time Order Parameters (η), Effective Temperature (T_eff),
and Phase State Transitions (Crystalline -> Hydrodynamic Fluid -> Plasma).
"""
from __future__ import annotations

import math
import numpy as np
from dataclasses import dataclass
from typing import Tuple, Dict


def _clamp(v: float, low: float = 0.0, high: float = 1.0) -> float:
    return max(low, min(high, float(v)))


@dataclass
class PhaseState:
    """Condensed matter phase parameters at a given instant."""
    order_parameter: float    # η in [0, 1]: 1 = crystalline order, 0 = disorder
    effective_temp: float     # T_eff in [0, 2]: thermal energy / excitation
    anisotropy: float         # γ in [0, 1]: directionality / high-low ratio
    phase_name: str           # "crystalline", "hydrodynamic", or "plasma"
    
    # Phase mixing weights (sums to 1.0)
    w_crystalline: float
    w_hydrodynamic: float
    w_plasma: float


class PhaseEngine:
    """Dynamic phase state tracker with hysteresis and thermal inertia."""

    def __init__(self):
        self.order_param = 0.5
        self.temp_eff = 0.3
        self.anisotropy = 0.5

        # Smoothed phase weights
        self.w_crys = 0.4
        self.w_fluid = 0.5
        self.w_plas = 0.1

    def update(
        self,
        rms: float,
        bass: float,
        mid: float,
        high: float,
        onset_strength: float,
        flatness: float,
        harmonic_e: float,
        percussive_e: float,
        flux: float,
        dt: float = 0.016,
    ) -> PhaseState:
        """Update order parameters and phase weights from continuous audio frame."""
        dt = max(0.001, float(dt))

        # 0. Calculate Activity Gate
        activity = _clamp(rms * 1.8 + bass * 0.6 + onset_strength * 0.6, 0.0, 1.0)
        is_dormant = activity < 0.05

        # 1. Calculate instant Order Parameter (η)
        tot_energy = max(1e-5, harmonic_e + percussive_e)
        hpr = harmonic_e / tot_energy
        instant_eta = _clamp(hpr * (1.0 - _clamp(flatness, 0.0, 0.9)), 0.0, 1.0) if not is_dormant else 0.6

        # 2. Calculate instant Effective Temperature (T_eff)
        energy_scale = rms * 0.45 + bass * 0.35 + onset_strength * 0.20
        instant_temp = _clamp(energy_scale * (1.0 + flux * 1.5), 0.0, 2.0) if not is_dormant else 0.0

        # 3. Calculate instant Anisotropy (γ)
        low_band = max(1e-4, bass)
        high_band = max(1e-4, high)
        instant_gamma = _clamp(high_band / (low_band + high_band), 0.0, 1.0)

        # 4. Thermal Inertia Smoothing (Attack / Decay)
        alpha_t = min(1.0, dt * (4.0 if instant_temp > self.temp_eff else 1.8))
        alpha_e = min(1.0, dt * 2.5)
        alpha_g = min(1.0, dt * 2.0)

        self.temp_eff += (instant_temp - self.temp_eff) * alpha_t
        self.order_param += (instant_eta - self.order_param) * alpha_e
        self.anisotropy += (instant_gamma - self.anisotropy) * alpha_g

        if is_dormant:
            self.w_crys += (0.80 - self.w_crys) * min(1.0, dt * 3.0)
            self.w_fluid += (0.15 - self.w_fluid) * min(1.0, dt * 3.0)
            self.w_plas += (0.05 - self.w_plas) * min(1.0, dt * 3.0)
            phase_name = "dormant"
        else:
            # 5. Compute Raw Phase Distances & Weights
            crys_score = max(0.0, self.order_param * 1.5 - self.temp_eff * 0.8)
            plas_score = max(0.0, self.temp_eff * 1.2 - self.order_param * 0.6)
            fluid_score = max(0.2, 1.0 - abs(self.order_param - 0.5) - abs(self.temp_eff - 0.5))

            tot_score = max(1e-5, crys_score + fluid_score + plas_score)
            t_crys = crys_score / tot_score
            t_fluid = fluid_score / tot_score
            t_plas = plas_score / tot_score

            w_speed = min(1.0, dt * 3.2)
            self.w_crys += (t_crys - self.w_crys) * w_speed
            self.w_fluid += (t_fluid - self.w_fluid) * w_speed
            self.w_plas += (t_plas - self.w_plas) * w_speed

            if self.w_crys >= self.w_fluid and self.w_crys >= self.w_plas:
                phase_name = "crystalline"
            elif self.w_plas >= self.w_crys and self.w_plas >= self.w_fluid:
                phase_name = "plasma"
            else:
                phase_name = "hydrodynamic"

        w_tot = max(1e-5, self.w_crys + self.w_fluid + self.w_plas)
        self.w_crys /= w_tot
        self.w_fluid /= w_tot
        self.w_plas /= w_tot

        return PhaseState(
            order_parameter=self.order_param,
            effective_temp=self.temp_eff,
            anisotropy=self.anisotropy,
            phase_name=phase_name,
            w_crystalline=self.w_crys,
            w_hydrodynamic=self.w_fluid,
            w_plasma=self.w_plas,
        )
