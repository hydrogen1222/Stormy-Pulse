import pytest
from app.dynamics.deterministic import deterministic_float, deterministic_uniform, deterministic_hash_uint64


def test_deterministic_reproducibility():
    """Verify stateless hash produces bit-identical float values across repeated calls."""
    v1 = deterministic_float(12345, "particles", 100, 5)
    v2 = deterministic_float(12345, "particles", 100, 5)
    assert v1 == v2
    assert 0.0 <= v1 < 1.0


def test_deterministic_distinctness():
    """Verify different ticks produce distinct random values."""
    v1 = deterministic_float(12345, "particles", 100, 0)
    v2 = deterministic_float(12345, "particles", 101, 0)
    v3 = deterministic_float(12345, "sparks", 100, 0)

    assert v1 != v2
    assert v1 != v3
    assert v2 != v3


def test_deterministic_uniform_range():
    """Verify deterministic_uniform respects [low, high) bounds."""
    for tick in range(50):
        val = deterministic_uniform(42, "stream", tick, low=-15.0, high=15.0)
        assert -15.0 <= val < 15.0
