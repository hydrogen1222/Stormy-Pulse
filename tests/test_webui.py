"""
Tests for the FastAPI WebUI server, engine, and hardware detection.
"""
import io
import tempfile
import time
from pathlib import Path

import numpy as np
import pytest
from fastapi.testclient import TestClient
from PIL import Image

from app.webui import server as webui_server
from app.webui.hardware import (
    get_system_info,
    detect_available_encoders,
    get_encoder_dropdown_choices,
    get_default_encoder,
)
from app.webui.engine import (
    WebUISession,
    PALETTE_FAMILIES,
    STRUCTURE_CHOICES,
    _filter_ui_settings,
)
from app.webui.server import (
    app,
    _frame_size,
    _ui_settings_from_params,
    _visual_from_params,
)
from app.config.settings import settings
from app.visual.themes import apply_dna_overrides, Theme, SCIENTIFIC_FAMILY_ORDER
from app.analysis.features import GlobalFeatureSet


def test_hardware_detection():
    """Test system info and encoder detection."""
    sys_info = get_system_info()
    assert "os" in sys_info
    assert sys_info["cpu_cores"] >= 1
    assert "ffmpeg_available" in sys_info
    assert "ram_total_gb" in sys_info

    encoders = detect_available_encoders()
    assert "recommended" in encoders
    assert "cpu_software" in encoders

    choices = get_encoder_dropdown_choices()
    assert len(choices) > 0
    assert all(isinstance(c, (list, tuple)) and len(c) == 2 for c in choices)
    assert get_default_encoder(choices) in {codec for _, codec in choices}


def test_session_engine_frame_render():
    """Test offscreen frame rendering with various structures and aspect ratios."""
    session = WebUISession()

    img_16_9 = session.render_frame(
        0.0, 640, 360,
        custom_settings={"visual_canvas_ratio": "16:9"},
    )
    assert isinstance(img_16_9, Image.Image)
    assert img_16_9.size == (640, 360)

    img_9_16 = session.render_frame(
        0.0, 360, 640,
        custom_settings={"visual_canvas_ratio": "9:16"},
    )
    assert img_9_16.size == (360, 640)

    img_custom = session.render_frame(
        0.0, 640, 360,
        custom_settings={
            "custom_track_title": "Custom Song",
            "custom_track_artist": "Custom Singer",
        },
    )
    assert isinstance(img_custom, Image.Image)


def test_render_does_not_persist_settings():
    """Rendering with UI overrides must never touch the persisted settings file."""
    session = WebUISession()
    config_file = settings.config_file
    before = config_file.read_text(encoding="utf-8") if config_file.exists() else ""
    value_before = settings.get("layout_title_x")

    session.render_frame(
        0.0, 320, 180,
        custom_settings={
            "show_lyrics": True,
            "layout_title_x": 12.5,
            "hud_scale": 1.4,
            "custom_track_title": "不落盘测试",
        },
    )

    after = config_file.read_text(encoding="utf-8") if config_file.exists() else ""
    assert before == after
    assert settings.get("layout_title_x") == value_before


def test_dna_overrides_drive_theme():
    """All palette families and structures can be forced through overrides."""
    base = GlobalFeatureSet.compute_defaults()
    for family in SCIENTIFIC_FAMILY_ORDER:
        eff = apply_dna_overrides(base, {"palette_family": family}, track_seed=12345)
        theme = Theme(name="x", features=eff, track_seed=12345)
        assert theme.palette_family == family, (family, theme.palette_family)

    eff = apply_dna_overrides(base, {"structure": "organic"}, track_seed=1)
    assert Theme(name="x", features=eff, track_seed=1).structure_type == "organic"
    assert apply_dna_overrides(base, {}, track_seed=1) is base


def test_filter_ui_settings():
    """UI settings are filtered to known keys."""
    filtered = _filter_ui_settings({
        "show_lyrics": True,
        "theme": "Cyberpunk",   # stale key must be dropped
        "layout_title_x": 5.0,
        "unknown_key": "x",
        "nulled": None,
    })
    assert filtered == {"show_lyrics": True, "layout_title_x": 5.0}


def test_param_mapping_shapes():
    s = _ui_settings_from_params({
        "aspect": "9:16", "custom_title": "T", "custom_artist": "A",
        "show_title": True, "show_artist": False,
        "title_scale": 1.2, "title_x": 3.0, "title_y": 4.0,
        "artist_scale": 0.9, "artist_x": 1.0, "artist_y": 2.0,
        "show_lyrics": True, "lyrics_scale": 1.1, "lyrics_x": 0.0, "lyrics_y": 0.0,
        "show_left_hud": True, "show_right_hud": False,
        "hud_scale": 1.3, "effect_scale": 1.0,
    })
    assert s["visual_canvas_ratio"] == "9:16"
    assert s["font_scale_title"] == s["module_scale_title"] == 1.2
    assert s["show_right_hud"] is False
    assert s["show_fps"] is False

    v = _visual_from_params({
        "structure": "vortex", "palette_family": "aurora_teal", "hue_shift": -30.0,
        "energy": 0.7, "chaos": 0.2, "brightness": 0.9,
    })
    assert v["structure"] == "vortex" and v["palette_family"] == "aurora_teal"

    assert _frame_size("16:9", 720) == (1280, 720)
    assert _frame_size("9:16", 720) == (406, 720)
    odd = _frame_size("16:9", 400, 639, 361)
    assert odd[0] % 2 == 0 and odd[1] % 2 == 0


def test_available_structures_and_families_render():
    """Every DNA dropdown choice renders without errors."""
    session = WebUISession()
    for structure in STRUCTURE_CHOICES:
        if structure == "auto":
            continue
        img = session.render_frame(0.0, 320, 180, visual_overrides={"structure": structure})
        assert img is not None and img.size == (320, 180)

    for family in PALETTE_FAMILIES:
        if family == "auto":
            continue
        img = session.render_frame(0.0, 320, 180, visual_overrides={"palette_family": family})
        assert img is not None


def test_deterministic_still_render():
    """Same timestamp + same overrides render pixel-identical stills."""
    session = WebUISession()
    kwargs = dict(
        timestamp=3.0, width=320, height=180,
        custom_settings={"custom_track_title": "确定性"},
        visual_overrides={"structure": "pulse"},
    )
    a = session.render_frame(**kwargs)
    b = session.render_frame(**kwargs)
    assert list(a.getdata()) == list(b.getdata())


# ---------------------------------------------------------------------------
# FastAPI server endpoints
# ---------------------------------------------------------------------------
def _make_wav_bytes(seconds: int = 8, sr: int = 11025) -> bytes:
    import soundfile as sf

    t = np.arange(int(sr * seconds)) / sr
    audio = 0.25 * np.sin(2 * np.pi * 440.0 * t)
    click_env = np.exp(-np.arange(300) / 40.0)
    for i in np.arange(0, seconds, 0.5):
        idx = int(i * sr)
        audio[idx: idx + 300] += 0.8 * click_env
    buf = io.BytesIO()
    sf.write(buf, audio, sr, format="WAV")
    return buf.getvalue()


def test_index_and_system_endpoints():
    client = TestClient(app)
    r = client.get("/")
    assert r.status_code == 200
    assert "Stormy-Pulse" in r.text

    r = client.get("/api/system")
    assert r.status_code == 200
    data = r.json()
    assert data["default_encoder"]
    assert isinstance(data["encoder_choices"], list) and data["encoder_choices"]

    r = client.get("/api/state")
    assert r.status_code == 200
    state = r.json()
    assert "phase" in state and "params" in state and "export" in state


def test_frame_without_track_is_409():
    client = TestClient(app)
    saved_track = webui_server._session.track
    saved_cache = webui_server._session.feature_cache
    webui_server._session.track = None
    webui_server._session.feature_cache = None
    try:
        r = client.get("/api/frame", params={"t": 0.0})
        assert r.status_code == 409
    finally:
        webui_server._session.track = saved_track
        webui_server._session.feature_cache = saved_cache


def test_params_roundtrip():
    client = TestClient(app)
    r = client.post("/api/params", json={"structure": "vortex", "bogus_key": 1})
    assert r.status_code == 200
    assert r.json()["params"]["structure"] == "vortex"
    assert "bogus_key" not in r.json()["params"]
    # restore default
    client.post("/api/params", json={"structure": "auto"})


def test_upload_analyze_frame_audio_flow():
    """Full happy path: upload -> auto analysis -> frame + audio endpoints."""
    client = TestClient(app)
    wav = _make_wav_bytes()

    r = client.post(
        "/api/upload",
        files={"audio": ("smoke_tone.wav", wav, "audio/wav")},
    )
    assert r.status_code == 200, r.text
    assert r.json()["started"] is True

    state = None
    for _ in range(180):
        state = client.get("/api/state").json()
        if state["phase"] == "ready":
            break
        if state["phase"] == "error":
            pytest.fail(f"analysis failed: {state['error']}")
        time.sleep(1.0)
    assert state and state["phase"] == "ready", "analysis timed out"
    assert state["has_audio"] is True
    assert state["track"]["duration"] > 0

    # Frame endpoint serves JPEGs
    r = client.get("/api/frame", params={"t": 1.0})
    assert r.status_code == 200
    assert r.headers["content-type"] == "image/jpeg"
    assert "X-Frame-Time" in r.headers
    img = Image.open(io.BytesIO(r.content))
    assert img.size == (1280, 720)

    # DNA override changes frame without error
    client.post("/api/params", json={"structure": "vortex", "palette_family": "aurora_teal"})
    r = client.get("/api/frame", params={"t": 2.0})
    assert r.status_code == 200
    client.post("/api/params", json={"structure": "auto", "palette_family": "auto"})

    # Audio endpoint supports Range requests (browser seeking)
    r = client.get("/api/audio")
    assert r.status_code == 200
    assert r.headers.get("accept-ranges") == "bytes"
    assert int(r.headers["content-length"]) > 1000

    r = client.get("/api/audio", headers={"Range": "bytes=0-99"})
    assert r.status_code == 206
    assert r.headers["content-length"] == "100"
    assert r.headers["content-range"].startswith("bytes 0-99/")


def test_live_mode_desktop_parity():
    """Live mode evolves the scene continuously (desktop parity); still mode
    stays deterministic; paused live mode runs the idle drift animation."""
    session = webui_server._session
    if not (session.track and session.feature_cache):
        pytest.skip("requires the analyzed track from the upload test")

    frame = dict(width=320, height=180, mode="live")

    a = session.render_frame(2.0, frame["width"], frame["height"], mode="live", playing=True)
    b = session.render_frame(2.2, frame["width"], frame["height"], mode="live", playing=True)
    c = session.render_frame(2.4, frame["width"], frame["height"], mode="live", playing=True)
    # Continuous evolution: consecutive live frames differ (particles/rotation/bursts)
    assert list(a.getdata()) != list(b.getdata())
    assert list(b.getdata()) != list(c.getdata())

    # Scrub stills remain deterministic
    s1 = session.render_frame(3.0, 320, 180, mode="still")
    s2 = session.render_frame(3.0, 320, 180, mode="still")
    assert list(s1.getdata()) == list(s2.getdata())

    # Paused: desktop-style idle drift keeps animating
    p1 = session.render_frame(4.0, 320, 180, mode="live", playing=False)
    p2 = session.render_frame(4.5, 320, 180, mode="live", playing=False)
    assert list(p1.getdata()) != list(p2.getdata())

    # The frame endpoint accepts the mode/playing params
    client = TestClient(app)
    r = client.get("/api/frame", params={"t": 1.0, "mode": "live", "playing": 1})
    assert r.status_code == 200
    r = client.get("/api/frame", params={"t": 1.0, "mode": "live", "playing": 0})
    assert r.status_code == 200


def test_gpu_probe_endpoint():
    """/api/gpu reports GL frame-render availability without crashing the server."""
    client = TestClient(app)
    r = client.get("/api/gpu")
    assert r.status_code == 200
    assert isinstance(r.json()["gpu_render_available"], bool)


def test_export_cancel_endpoint():
    """Cancel endpoint is safe to call any time (idle export = no-op)."""
    client = TestClient(app)
    r = client.post("/api/export/cancel")
    assert r.status_code == 200
    assert r.json()["cancelling"] is False


def test_export_cancel_pipeline():
    """A pre-cancelled export aborts quickly through the cooperative cancel hook."""
    import threading as _threading

    from app.export.video_exporter import VideoExportCancelled, VideoExportOptions

    session = webui_server._session
    if not (session.track and session.feature_cache):
        pytest.skip("requires the analyzed track from the upload test")

    cancel_event = _threading.Event()
    cancel_event.set()  # cancel before the first frame

    out = Path(tempfile.gettempdir()) / "stormy_pulse_cancel_test.mp4"
    options = VideoExportOptions(
        output_path=str(out),
        width=640, height=360, fps=24,
        video_codec="libx264", preset="speed",
        cpu_render_workers=1,  # sequential path => cancel checked on frame 0
    )
    t0 = time.time()
    with pytest.raises(VideoExportCancelled):
        session.export_video(options=options, cancel_check=cancel_event.is_set)
    assert time.time() - t0 < 60
    assert not out.exists()
