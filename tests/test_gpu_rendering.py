import pytest
import numpy as np
from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QImage

from app.visual.scene import Scene
from app.visual.themes import get_theme
from app.visual_gpu.viewport import VisualizerViewport
from app.visual.renderer import VisualizerRenderer


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    yield app


def test_gpu_and_cpu_render_bounding_flash(qapp):
    width, height = 1280, 720
    scene = Scene()
    theme = get_theme("Cyberpunk")
    scene.theme = theme

    # Trigger beat flash and active features
    scene.get_audio_drive = lambda: {
        "bass": 0.8,
        "mid": 0.6,
        "high": 0.7,
        "onset": 0.9,
        "beat": 1.0,
        "pressure": 0.8,
        "sparkle": 0.7,
        "tension": 0.8,
        "density": 0.6,
        "centroid": 0.5,
        "rolloff": 0.5,
    }
    scene.effects.beat_flash = 1.0

    # Render with CPU
    cpu_renderer = VisualizerRenderer()
    cpu_renderer.resize(width, height)
    cpu_renderer.scene = scene
    cpu_img = cpu_renderer.render_to_image(width, height, 0.016)

    # Render with GPU Viewport
    gpu_viewport = VisualizerViewport()
    gpu_viewport.resize(width, height)
    gpu_viewport.set_scene(scene)
    gpu_viewport.show()
    qapp.processEvents()

    gpu_img = gpu_viewport.render_to_image(width, height, 0.016)

    # Ensure images have correct dimensions
    assert gpu_img.width() == width
    assert gpu_img.height() == height
    assert cpu_img.width() == width
    assert cpu_img.height() == height

    # Convert QImage to numpy array to verify uniform edge brightness
    ptr = gpu_img.bits()
    arr = np.frombuffer(ptr, dtype=np.uint8).reshape((height, width, 4))

    # Check corners (top-left, top-right, bottom-left, bottom-right)
    # Prior to fix, top-left (within 640x480) had beat_flash addition while bottom-right did not.
    # Now beat_flash covers the full (width, height) evenly.
    top_left_pixel = arr[10, 10, :3].astype(int)
    top_right_pixel = arr[10, width - 10, :3].astype(int)
    bottom_left_pixel = arr[height - 10, 10, :3].astype(int)
    bottom_right_pixel = arr[height - 10, width - 10, :3].astype(int)

    # All four corners of the background gradient should be symmetric horizontally
    diff_top = np.abs(top_left_pixel - top_right_pixel)
    assert np.max(diff_top) < 15, f"Top left and top right differ significantly: {top_left_pixel} vs {top_right_pixel}"
