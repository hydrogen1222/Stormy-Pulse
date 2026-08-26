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

    def get_state_at_time(self, time: float) -> MaterialState:
        """Query state at any timestamp with fast O(1) indexing."""
        if len(self.states) == 0:
            return MaterialState(0.5, 0.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, "dormant")

        time = max(0.0, float(time))
        idx = int(time / self.dt)

        if idx >= len(self.states):
            return self.states[-1]

        return self.states[idx]


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
