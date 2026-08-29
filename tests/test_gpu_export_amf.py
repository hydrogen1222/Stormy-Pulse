"""Tests for GPU Viewport reuse_buffer and AV1_AMF export pipeline."""
import os
import subprocess
import tempfile
from pathlib import Path
from unittest.mock import MagicMock
import pytest
from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QImage

from app.core.music_library import Track
from app.export.video_exporter import VideoExporter, VideoExportOptions
from app.visual_gpu.viewport import VisualizerViewport
from app.visual_gpu.hud_overlay import HudOverlayRenderer


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    yield app


def test_gpu_viewport_reuse_buffer_continuous(qapp):
    """Verify GPU viewport accepts reuse_buffer=True, renders multiple frames without error, and caches buffer."""
    width, height = 640, 360
    viewport = VisualizerViewport()
    viewport.resize(width, height)
    viewport.show()
    qapp.processEvents()

    # Frame 1 with reuse_buffer=True
    img1 = viewport.render_to_image(width, height, 0.016, reuse_buffer=True)
    assert not img1.isNull()
    assert img1.width() == width
    assert img1.height() == height
    assert img1.format() == QImage.Format.Format_RGBA8888

    # Frame 2 with reuse_buffer=True
    img2 = viewport.render_to_image(width, height, 0.016, reuse_buffer=True)
    assert not img2.isNull()
    assert img2.width() == width
    assert img2.height() == height

    # HudOverlayRenderer direct test
    overlay = HudOverlayRenderer(viewport.scene, viewport)
    o_img1 = overlay.render_overlay_to_image(width, height, 0.016, reuse_buffer=True)
    assert not o_img1.isNull()
    o_img2 = overlay.render_overlay_to_image(width, height, 0.016, reuse_buffer=True)
    assert not o_img2.isNull()


def test_video_exporter_amf_command_building():
    """Verify AV1_AMF command includes D3D11 device, hwupload, quality preset, and avoids CRF/libx264/yuv420p."""
    exporter = VideoExporter()
    track = Track("dummy.mp3")
    track.metadata.title = "Test Title"
    track.metadata.artist = "Test Artist"

    options = VideoExportOptions(
        output_path="test_out.mp4",
        width=1920,
        height=1080,
        fps=60,
        video_codec="av1_amf",
        preset="high_quality",
        crf=18,
        pixel_format="yuv420p",
        video_bitrate="16M",
        use_gpu_renderer=True,
    )

    cmd = exporter._build_rawvideo_ffmpeg_command(track, options)
    cmd_str = " ".join(cmd)

    # Required D3D11 / AMF arguments
    assert "-init_hw_device" in cmd
    d3d_idx = cmd.index("-init_hw_device")
    assert cmd[d3d_idx + 1] == "d3d11va=amf:0"
    assert "-filter_hw_device" in cmd
    filter_idx = cmd.index("-filter_hw_device")
    assert cmd[filter_idx + 1] == "amf"

    assert "-vf" in cmd
    vf_idx = cmd.index("-vf")
    assert cmd[vf_idx + 1] == "format=rgba,hwupload"

    assert "-c:v" in cmd
    cv_idx = cmd.index("-c:v")
    assert cmd[cv_idx + 1] == "av1_amf"

    assert "-quality" in cmd
    quality_idx = cmd.index("-quality")
    assert cmd[quality_idx + 1] == "high_quality"

    assert "-usage" in cmd
    usage_idx = cmd.index("-usage")
    assert cmd[usage_idx + 1] == "transcoding"

    assert "-b:v" in cmd
    bv_idx = cmd.index("-b:v")
    assert cmd[bv_idx + 1] == "16M"

    # Forbidden arguments for AMF rawvideo hwupload
    assert "-crf" not in cmd
    assert "libx264" not in cmd
    # Output section should not have -pix_fmt yuv420p
    output_section = cmd[cmd.index("-c:v"):]
    assert "-pix_fmt" not in output_section


def test_video_exporter_cpu_libx264_command_building():
    """Verify standard CPU libx264 command remains untouched with CRF and yuv420p."""
    exporter = VideoExporter()
    track = Track("dummy.mp3")
    track.metadata.title = "Test Title"
    track.metadata.artist = "Test Artist"

    options = VideoExportOptions(
        output_path="test_cpu.mp4",
        width=1920,
        height=1080,
        fps=60,
        video_codec="libx264",
        preset="slow",
        crf=18,
        pixel_format="yuv420p",
        use_gpu_renderer=False,
    )

    cmd = exporter._build_rawvideo_ffmpeg_command(track, options)
    cmd_str = " ".join(cmd)

    assert "-init_hw_device" not in cmd
    assert "-filter_hw_device" not in cmd
    assert "format=rgba,hwupload" not in cmd_str
    assert "-c:v" in cmd
    cv_idx = cmd.index("-c:v")
    assert cmd[cv_idx + 1] == "libx264"
    assert "-preset" in cmd
    preset_idx = cmd.index("-preset")
    assert cmd[preset_idx + 1] == "slow"
    assert "-crf" in cmd
    crf_idx = cmd.index("-crf")
    assert cmd[crf_idx + 1] == "18"
    
    # Check output pixel format
    output_section = cmd[cv_idx:]
    assert "-pix_fmt" in output_section
    out_pix_idx = output_section.index("-pix_fmt")
    assert output_section[out_pix_idx + 1] == "yuv420p"


def test_video_exporter_gpu_routing(monkeypatch):
    """use_gpu_renderer parallelizes across GPU worker contexts when workers>1,
    and falls back to the sequential single-context path when workers==1."""
    exporter = VideoExporter()
    track = Track("dummy.mp3")
    feature_cache = MagicMock()
    feature_cache.duration = 10.0

    called_parallel = []
    called_sequential = []

    def fake_parallel(*args, **kwargs):
        called_parallel.append(kwargs.get("worker_count"))
        return Path("out.mp4")

    def fake_sequential(*args, **kwargs):
        called_sequential.append(True)
        return Path("out.mp4")

    monkeypatch.setattr(exporter, "_export_track_parallel", fake_parallel)
    monkeypatch.setattr(exporter, "_export_track_sequential", fake_sequential)

    gpu_options = dict(
        output_path="out.mp4",
        width=1280,
        height=720,
        fps=60,
        video_codec="libx264",
        use_gpu_renderer=True,
    )

    # GPU + several workers => parallel GPU segments
    exporter.export_track(track, feature_cache, VideoExportOptions(cpu_render_workers=4, **gpu_options))
    assert called_parallel and called_parallel[0] == 4, "GPU rendering should parallelize across GL contexts"
    assert not called_sequential

    # GPU + single worker => sequential (one GL context)
    exporter.export_track(track, feature_cache, VideoExportOptions(cpu_render_workers=1, **gpu_options))
    assert called_sequential, "GPU with 1 worker must use the sequential path"


def test_segment_worker_signature_accepts_gpu():
    """The spawned worker supports GPU (OpenGL) segment rendering."""
    import inspect

    from app.export.video_exporter import _render_segment_worker_impl

    sig = inspect.signature(_render_segment_worker_impl)
    assert "use_gpu" in sig.parameters


def test_amf_native_single_frame_smoke(qapp):
    """Smoke test: execute native ffmpeg rawvideo encode with D3D11 AMF if available."""
    try:
        res = subprocess.run(["ffmpeg", "-h", "encoder=av1_amf"], capture_output=True, text=True)
        if res.returncode != 0:
            pytest.skip("av1_amf not supported by local ffmpeg")
    except Exception:
        pytest.skip("ffmpeg executable not found")

    width, height = 320, 180
    fps = 30

    with tempfile.TemporaryDirectory() as td:
        out_path = Path(td) / "smoke_av1.mp4"
        cmd = [
            "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
            "-init_hw_device", "d3d11va=amf:0",
            "-filter_hw_device", "amf",
            "-f", "rawvideo",
            "-vcodec", "rawvideo",
            "-pix_fmt", "rgba",
            "-s", f"{width}x{height}",
            "-r", str(fps),
            "-i", "-",
            "-vf", "format=rgba,hwupload",
            "-c:v", "av1_amf",
            "-quality", "speed",
            "-usage", "transcoding",
            "-b:v", "5M",
            "-an",
            str(out_path)
        ]

        proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stderr=subprocess.PIPE)
        viewport = VisualizerViewport()
        viewport.resize(width, height)
        viewport.show()
        qapp.processEvents()

        frame_bytes = viewport.render_to_image(width, height, 0.033, reuse_buffer=True).constBits()
        for _ in range(2):
            proc.stdin.write(frame_bytes)
        proc.stdin.close()
        proc.wait(timeout=10)

        assert out_path.exists()
        assert out_path.stat().st_size > 0
