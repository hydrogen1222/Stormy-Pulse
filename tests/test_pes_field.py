import pytest
import numpy as np
from app.visual.pes_field import PESField


def test_pes_field_potential_and_force():
    pes = PESField()
    chroma = np.array([1.0, 0.2, 0.5, 0.1, 0.8, 0.3, 0.2, 0.9, 0.4, 0.1, 0.6, 0.2])
    pes.update(chroma, energy=0.7, flux=0.4)

    # Sample potential energy at position
    v = pes.sample_potential(100.0, 100.0, cx=0.0, cy=0.0, base_radius=200.0)
    assert isinstance(v, float)

    # Sample force vector
    fx, fy = pes.sample_force(100.0, 100.0, cx=0.0, cy=0.0, base_radius=200.0)
    assert isinstance(fx, float)
    assert isinstance(fy, float)
    # Gradient force should not be NaN or Infinity
    assert not np.isnan(fx) and not np.isinf(fx)
    assert not np.isnan(fy) and not np.isinf(fy)
