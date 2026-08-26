"""
Material State Engine & Hysteresis Dynamics.
Implements continuous artificial material state (order, excitation, mobility, defect_density)
with path-dependent hysteresis and defect creation/healing dynamics.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Tuple

from .context import VisualContext


def _clamp(v: float, low: float = 0.0, high: float = 1.0) -> float:
    return max(low, min(high, float(v)))


@dataclass(frozen=True)
class GeometryControl:
    """Continuous renderer geometry control parameters derived from MaterialState."""

    symmetry: float        # Order * (1 - defect_density)
    coherence: float       # Order * (1 - 0.5 * excitation)
    circulation: float     # w_hydrodynamic * mobility
    fragmentation: float   # defect_density * (0.4 + 0.6 * w_plasma)
    roughness: float       # w_plasma * excitation
    angular_lock: float    # w_crystalline


@dataclass(frozen=True)
class MaterialState:
    """Snapshot of continuous artificial material state at time t."""

    order: float           # η ∈ [0, 1]: structural alignment / crystalline coherence
    excitation: float      # E ∈ [0, 2]: thermal energy / kinetic excitation
    mobility: float        # M ∈ [0, 1]: fluid transport capability / advection rate
    defect_density: float  # D ∈ [0, 1]: path-dependent memory / lattice damage
    activity: float        # A ∈ [0, 1]: signal activity gate

    w_crystalline: float
    w_hydrodynamic: float
    w_plasma: float

    phase_name: str

    @property
    def geometry_control(self) -> GeometryControl:
        """Derive continuous GeometryControl for rendering."""
        return GeometryControl(
            symmetry=_clamp(self.order * (1.0 - self.defect_density), 0.0, 1.0),
            coherence=_clamp(self.order * (1.0 - 0.5 * min(1.0, self.excitation)), 0.0, 1.0),
            circulation=_clamp(self.w_hydrodynamic * self.mobility, 0.0, 1.0),
            fragmentation=_clamp(self.defect_density * (0.4 + 0.6 * self.w_plasma), 0.0, 1.0),
            roughness=_clamp(self.w_plasma * min(1.0, self.excitation), 0.0, 1.0),
            angular_lock=_clamp(self.w_crystalline, 0.0, 1.0),
        )


class MaterialStateEngine:
    """Integrated physical state tracker with defect damage hysteresis."""

    def __init__(self):
        self.order = 0.6
        self.excitation = 0.2
        self.mobility = 0.3
        self.defect_density = 0.0
        self.w_crys = 0.7
        self.w_fluid = 0.23
        self.w_plas = 0.07

    def update(self, ctx: VisualContext, dt: float = 0.016) -> MaterialState:
        """Advance material state by dt given current VisualContext."""
        dt = max(0.001, float(dt))

        activity = ctx.activity
        is_dormant = activity < 0.05

        # 1. Excitation Dynamics (Fast attack, slow decay relaxation)
        exc_target = (
            0.25 * ctx.energy_fast
            + 0.15 * ctx.energy_slow
            + 0.20 * ctx.flux
            + 0.18 * ctx.onset
            + 0.17 * ctx.transient_density
            + 0.05 * max(0.0, ctx.energy_trend)
        ) if not is_dormant else 0.0

        tau_exc = 0.12 if exc_target > self.excitation else 0.55
        alpha_exc = 1.0 - math.exp(-dt / tau_exc)
        self.excitation += (exc_target - self.excitation) * alpha_exc

        # 2. Defect Creation & Healing Dynamics (Hysteresis & L4 Susceptibility)
        susceptibility = 1.0 + 0.20 * ctx.novelty + 0.15 * ctx.boundary_impulse
        damage = (0.40 * ctx.onset + 0.30 * ctx.flux + 0.30 * self.excitation) * susceptibility
        create_rate = 1.8
        heal_rate = 0.25

        d_defect_create = create_rate * damage * (1.0 - self.defect_density) * dt
        d_defect_heal = heal_rate * (1.0 - self.excitation) * (0.3 + 0.7 * ctx.harmonic_ratio) * self.defect_density * dt

        self.defect_density = _clamp(self.defect_density + d_defect_create - d_defect_heal, 0.0, 1.0)

        # 3. Order Dynamics (Suppressed by defect_density)
        order_drive = ctx.tonal_confidence * (1.0 - ctx.spectral_noise) * (0.35 + 0.65 * ctx.harmonic_ratio)
        order_target = order_drive * (1.0 - 0.75 * self.defect_density) if not is_dormant else 0.65

        tau_order = 0.40
        alpha_order = 1.0 - math.exp(-dt / tau_order)
        self.order += (order_target - self.order) * alpha_order

        # 4. Mobility Dynamics (Consumes beat_density & energy_slow)
        mob_target = _clamp(
            0.35 * self.excitation + 0.35 * ctx.beat_density + 0.20 * self.defect_density + 0.10 * ctx.energy_slow,
            0.0, 1.0
        ) if not is_dormant else 0.0
        tau_mob = 0.30
        self.mobility += (mob_target - self.mobility) * (1.0 - math.exp(-dt / tau_mob))

        # 5. Soft Phase Weights Assignment (Continuous softmax distances)
        # Prototypes in (Order, Excitation, Defect) space:
        # Crys:   (0.85, 0.15, 0.10)
        # Fluid:  (0.50, 0.50, 0.40)
        # Plasma: (0.15, 0.95, 0.80)
        d_crys_sq = 2.0 * (self.order - 0.85)**2 + 1.5 * (self.excitation - 0.15)**2 + 1.0 * (self.defect_density - 0.10)**2
        d_fluid_sq = 1.0 * (self.order - 0.50)**2 + 1.5 * (self.excitation - 0.50)**2 + 1.0 * (self.defect_density - 0.40)**2
        d_plas_sq = 1.5 * (self.order - 0.15)**2 + 2.0 * (self.excitation - 0.95)**2 + 1.5 * (self.defect_density - 0.80)**2

        beta = 4.0
        exp_crys = math.exp(-beta * d_crys_sq)
        exp_fluid = math.exp(-beta * d_fluid_sq)
        exp_plas = math.exp(-beta * d_plas_sq)

        tot_exp = max(1e-5, exp_crys + exp_fluid + exp_plas)
        target_w_crys = exp_crys / tot_exp
        target_w_fluid = exp_fluid / tot_exp
        target_w_plas = exp_plas / tot_exp

        tau_w = 0.25
        alpha_w = 1.0 - math.exp(-dt / tau_w)
        self.w_crys += (target_w_crys - self.w_crys) * alpha_w
        self.w_fluid += (target_w_fluid - self.w_fluid) * alpha_w
        self.w_plas += (target_w_plas - self.w_plas) * alpha_w

        w_tot = max(1e-5, self.w_crys + self.w_fluid + self.w_plas)
        self.w_crys /= w_tot
        self.w_fluid /= w_tot
        self.w_plas /= w_tot

        if is_dormant:
            phase_name = "dormant"
        elif self.w_crys >= self.w_fluid and self.w_crys >= self.w_plas:
            phase_name = "crystalline"
        elif self.w_plas >= self.w_crys and self.w_plas >= self.w_fluid:
            phase_name = "plasma"
        else:
            phase_name = "hydrodynamic"

        return MaterialState(
            order=self.order,
            excitation=self.excitation,
            mobility=self.mobility,
            defect_density=self.defect_density,
            activity=activity,
            w_crystalline=self.w_crys,
            w_hydrodynamic=self.w_fluid,
            w_plasma=self.w_plas,
            phase_name=phase_name,
        )
