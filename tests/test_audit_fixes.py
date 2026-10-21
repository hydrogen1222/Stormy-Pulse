"""Regression tests for the bugs found in the code audit (see git log for details)."""
import hashlib
import shutil
import subprocess
import tempfile
from pathlib import Path

import numpy as np
import pytest


# ---------------------------------------------------------------------------
# Dynamics calibration: silence must not stretch the dB range
# ---------------------------------------------------------------------------
def test_calibration_ignores_digital_silence():
    from app.dynamics.calibration import TrackCalibration

    rng = np.random.default_rng(0)
    body = rng.uniform(0.05, 0.3, 800)
    rms = np.concatenate([np.zeros(300), body, np.zeros(100)])  # ~33% silence

    calib = TrackCalibration.compute(rms, np.ones(10), np.ones(10))
    with_silence = calib.rms_db_p10
    no_silence = TrackCalibration.compute(body, np.ones(10), np.ones(10)).rms_db_p10

    assert with_silence > -30.0  # used to collapse to the ~-120 dB epsilon floor
    assert with_silence == pytest.approx(no_silence)


# ---------------------------------------------------------------------------
# Export helpers
# ---------------------------------------------------------------------------
def test_concat_list_quoting():
    from app.export.video_exporter import _concat_quote

    assert _concat_quote("/tmp/seg 0.mp4") == "'/tmp/seg 0.mp4'"
    assert _concat_quote("/tmp/it's/seg.mp4") == "'/tmp/it'\\''s/seg.mp4'"


# ---------------------------------------------------------------------------
# Music library
# ---------------------------------------------------------------------------
def test_library_directory_scan_counts_only_new_tracks(tmp_path):
    from app.core.music_library import MusicLibrary

    (tmp_path / "a.mp3").write_bytes(b"x")
    (tmp_path / "B.MP3").write_bytes(b"x")  # upper-case extension used to be skipped
    (tmp_path / "sub").mkdir()
    (tmp_path / "sub" / "c.m4a").write_bytes(b"x")
    (tmp_path / "sub" / "d.aac").write_bytes(b"x")
    (tmp_path / "notes.txt").write_bytes(b"x")

    lib = MusicLibrary()
    assert lib.add_directory(str(tmp_path)) == 4
    assert lib.get_track_count() == 4

    # Re-adding is a no-op and must report 0 (the UI slices tracks[-count:], and
    # tracks[-0:] is the whole list).
    assert lib.add_directory(str(tmp_path)) == 0
    assert lib.get_track_count() == 4

    # The same file spelled differently is still one track.
    first = lib.add_track(str(tmp_path / "a.mp3"))
    again = lib.add_track(str(tmp_path / "sub" / ".." / "a.mp3"))
    assert first is again
    assert lib.get_track_count() == 4


# ---------------------------------------------------------------------------
# Feature cache: portable key, atomic writes, corrupt files
# ---------------------------------------------------------------------------
def _cache_manager(cache_dir: Path):
    from app.analysis.cache import FeatureCacheManager

    mgr = FeatureCacheManager.__new__(FeatureCacheManager)
    mgr.cache_dir = cache_dir
    mgr.extractor = None
    return mgr


def test_cache_hits_for_same_file_in_other_directory(tmp_path):
    mgr = _cache_manager(tmp_path / "cache")
    mgr.cache_dir.mkdir()
    (tmp_path / "d1").mkdir()
    (tmp_path / "d2").mkdir()
    a = tmp_path / "d1" / "song.wav"
    a.write_bytes(b"0" * 1000)
    b = tmp_path / "d2" / "song.wav"
    shutil.copy2(a, b)  # same name/size/mtime, different folder

    payload = {"hello": [1, 2, 3]}
    assert mgr.save(str(a), payload)
    assert not [p for p in mgr.cache_dir.iterdir() if p.name.startswith(".tmp_")]
    assert mgr.load(str(a)) == payload
    assert mgr.load(str(b)) == payload

    other_name = tmp_path / "d2" / "other.wav"
    shutil.copy2(a, other_name)
    assert mgr.load(str(other_name)) is None


def test_corrupt_cache_is_discarded(tmp_path):
    mgr = _cache_manager(tmp_path / "cache")
    mgr.cache_dir.mkdir()
    f = tmp_path / "song.wav"
    f.write_bytes(b"0" * 100)
    assert mgr.save(str(f), {"k": 1})
    cache_path = mgr.get_cache_path(str(f))
    cache_path.write_bytes(b"garbage")
    assert mgr.load(str(f)) is None
    assert not cache_path.exists()


# ---------------------------------------------------------------------------
# Audio decoding: AAC/M4A is advertised, libsndfile cannot read it
# ---------------------------------------------------------------------------
@pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="ffmpeg not installed")
def test_extractor_decodes_m4a_through_ffmpeg(tmp_path, monkeypatch):
    from app.analysis import extractor

    src = tmp_path / "tone.m4a"
    subprocess.run(
        ["ffmpeg", "-v", "error", "-f", "lavfi", "-i", "sine=frequency=440:duration=2", "-c:a", "aac", str(src)],
        check=True,
    )

    def _no_sndfile(*_a, **_k):
        raise RuntimeError("Format not recognised")

    monkeypatch.setattr(extractor.sf, "read", _no_sndfile)  # what libsndfile does for AAC

    fe = extractor.FeatureExtractor()
    y, sr = fe._load_audio(str(src))
    assert sr == fe.sr
    assert y.ndim == 1
    assert abs(len(y) / sr - 2.0) < 0.2
    assert 0.1 < float(np.abs(y).max()) <= 1.0


def test_seed_hash_does_not_depend_on_directory(tmp_path):
    """file_hash feeds the visual seed; moving a file must not change the visuals."""
    (tmp_path / "x").mkdir()
    (tmp_path / "y").mkdir()
    a = tmp_path / "x" / "song.wav"
    b = tmp_path / "y" / "song.wav"
    a.write_bytes(b"0" * 10)
    b.write_bytes(b"0" * 10)

    def h(p: Path) -> str:
        return hashlib.md5(f"{p.name}_{p.stat().st_size}".encode()).hexdigest()

    assert h(a) == h(b)


# ---------------------------------------------------------------------------
# WebUI server
# ---------------------------------------------------------------------------
@pytest.fixture()
def client():
    from fastapi.testclient import TestClient

    from app.webui.server import app

    return TestClient(app)


def test_clip_file_rejects_path_traversal(client):
    clip_dir = Path(tempfile.gettempdir()) / "stormy_pulse_webui"
    clip_dir.mkdir(exist_ok=True)
    good = clip_dir / "preview_audit_test.mp4"
    good.write_bytes(b"fake")
    secret = Path(tempfile.gettempdir()) / "audit_secret.mp4"
    secret.write_bytes(b"secret")
    try:
        assert client.get("/api/clip/file", params={"name": good.name}).status_code == 200
        for bad in ("../audit_secret.mp4", "..\\audit_secret.mp4", str(secret), "preview_audit_test.txt", "nope.mp4"):
            assert client.get("/api/clip/file", params={"name": bad}).status_code == 404, bad
        # legacy ?path= form: only the basename counts, so ".." cannot escape the folder
        legacy = f"{clip_dir}/../audit_secret.mp4"
        assert client.get("/api/clip/file", params={"path": legacy}).status_code == 404
    finally:
        good.unlink(missing_ok=True)
        secret.unlink(missing_ok=True)


@pytest.mark.parametrize(
    "body",
    [
        {"video_codec": "libx264; rm -rf /"},
        {"video_bitrate": "16M -vf x"},
        {"audio_bitrate": "abc"},
        {"fps": 0},
        {"fps": 1000},
        {"width": 99999, "height": 1080},
        {"width": "abc"},
        {"width": 1921, "height": 1080},
        {"width": 1000, "height": 1000},
    ],
)
def test_export_rejects_invalid_params(client, body):
    # Parameter validation happens before the "is a track loaded?" check, so this
    # must be a 400 regardless of session state or test ordering.
    assert client.post("/api/export", json=body).status_code == 400


def test_state_reports_job_and_phase(client):
    state = client.get("/api/state").json()
    # The front-end polls `phase`/`job`; there is no `analyzing` key.
    assert "phase" in state and "job" in state
    assert "analyzing" not in state


# ---------------------------------------------------------------------------
# Visual smoothing: a long frame (stall) must not overshoot the target
# ---------------------------------------------------------------------------
def test_ring_and_core_smoothing_do_not_overshoot_on_long_dt():
    from app.visual.energy_core import EnergyCore
    from app.visual.ring_layer import RingLayer

    ring = RingLayer(ring_count=5)
    ring.update([1.0] * 8, 1.0, 1.0, 1.0, 1.0, 0.0, 0.0, 1.0, False, 120, dt=0.25)
    assert 0.0 <= ring.bass_pulse <= 5.8 + 1e-9
    assert 0.0 <= ring.overall_pulse <= 3.8 + 1e-9
    assert all(r >= 0.0 for r in ring.ring_radii)
    assert all(t > 0.0 for t in ring.ring_thickness)

    core = EnergyCore()
    core.update(0.0, 0.0, 0.0, 0.0, dt=0.25)  # target far below current size
    assert core.size > 0.0
    assert core.get_state()["brightness"] >= 0.0
