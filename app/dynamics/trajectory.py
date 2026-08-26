"""
Material State Trajectory Compiler & Sequence Container.
Precompiles track trajectory at a fixed 60 Hz simulation rate.
"""
from __future__ import annotations

import math
import numpy as np
from typing import List, Optional

from .context import VisualContextBuilder, VisualContext
from .material import MaterialStateEngine, MaterialState


class MaterialStateSequence:
    """Precompiled, deterministic 60 Hz material state trajectory."""

    def __init__(self, times: np.ndarray, states: List[MaterialState]):
        self.times = times
        self.states = states
        self.dt = 1.0 / 60.0 if len(times) < 2 else float(times[1] - times[0])

    def get_state_at_time(self, time: float, interpolate: bool = True) -> MaterialState:
        """Query state at any timestamp with fast O(1) indexing and optional linear interpolation."""
        if len(self.states) == 0:
            return MaterialState(0.5, 0.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, "dormant")

        time = max(0.0, float(time))
        idx_f = time / self.dt
        i0 = int(math.floor(idx_f))

        if i0 >= len(self.states) - 1:
            return self.states[-1]

        if not interpolate:
            return self.states[i0]

        i1 = i0 + 1
        u = float(idx_f - i0)

        s0 = self.states[i0]
        s1 = self.states[i1]

        order = (1.0 - u) * s0.order + u * s1.order
        excitation = (1.0 - u) * s0.excitation + u * s1.excitation
        mobility = (1.0 - u) * s0.mobility + u * s1.mobility
        defect = (1.0 - u) * s0.defect_density + u * s1.defect_density
        activity = (1.0 - u) * s0.activity + u * s1.activity

        w_crys = (1.0 - u) * s0.w_crystalline + u * s1.w_crystalline
        w_fluid = (1.0 - u) * s0.w_hydrodynamic + u * s1.w_hydrodynamic
        w_plas = (1.0 - u) * s0.w_plasma + u * s1.w_plasma

        w_tot = max(1e-5, w_crys + w_fluid + w_plas)
        w_crys /= w_tot
        w_fluid /= w_tot
        w_plas /= w_tot

        if activity < 0.05:
            phase_name = "dormant"
        elif w_crys >= w_fluid and w_crys >= w_plas:
            phase_name = "crystalline"
        elif w_plas >= w_crys and w_plas >= w_fluid:
            phase_name = "plasma"
        else:
            phase_name = "hydrodynamic"

        return MaterialState(
            order=max(0.0, min(1.0, float(order))),
            excitation=max(0.0, min(2.0, float(excitation))),
            mobility=max(0.0, min(1.0, float(mobility))),
            defect_density=max(0.0, min(1.0, float(defect))),
            activity=max(0.0, min(1.0, float(activity))),
            w_crystalline=w_crys,
            w_hydrodynamic=w_fluid,
            w_plasma=w_plas,
            phase_name=phase_name,
        )


class MaterialTrajectoryCompiler:
    """Compiles track trajectory at fixed 60 Hz rate."""

    @classmethod
    def compile(
        cls,
        context_builder: VisualContextBuilder,
        duration: float,
        simulation_hz: float = 60.0,
    ) -> MaterialStateSequence:
        """Precompile entire track trajectory sequentially."""
        dt = 1.0 / max(1.0, float(simulation_hz))
        n_steps = int(math.ceil(max(1.0, float(duration)) / dt))

        times = np.arange(n_steps, dtype=float) * dt
        engine = MaterialStateEngine()
        states: List[MaterialState] = []

        for t in times:
            ctx = context_builder.at(t)
            st = engine.update(ctx, dt=dt)
            states.append(st)

        return MaterialStateSequence(times=times, states=states)
