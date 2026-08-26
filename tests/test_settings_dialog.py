import pytest
from PySide6.QtWidgets import QApplication
from app.config.settings import DEFAULT_SETTINGS, settings
from app.ui.settings_dialog import SettingsDialog
from app.visual_gpu.viewport import VisualizerViewport
from app.visual.renderer import VisualizerRenderer


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    yield app


def test_settings_dialog_initialization(qapp):
    data = DEFAULT_SETTINGS.copy()
    dialog = SettingsDialog(None, data, gpu_available=True, render_backend="gpu")
    
    assert dialog.windowTitle() == "引擎与界面设置"
    collected = dialog.collect_settings()
    assert collected["fps"] == 60
    assert collected["visual_canvas_ratio"] == "16:9"
    assert collected["render_backend"] == "gpu"
    assert collected["show_track_title"] is True
    assert collected["module_scale_title"] == 1.0


def test_settings_dialog_reset_defaults(qapp):
    data = DEFAULT_SETTINGS.copy()
    data["layout_title_x"] = 15.0
    data["module_scale_title"] = 1.5
    
    dialog = SettingsDialog(None, data)
    assert dialog.title_x_spin.value() == 15.0
    assert dialog.title_scale_spin.value() == 1.5
    
    dialog._reset_layout_defaults()
    assert dialog.title_x_spin.value() == 0.0
    assert dialog.title_scale_spin.value() == 1.0

    collected = dialog.collect_settings()
    assert collected["layout_title_x"] == 0.0
    assert collected["module_scale_title"] == 1.0


def test_layout_cache_invalidation_and_scaling(qapp):
    # Reset layout_title_x to baseline 0.0
    settings.set("layout_title_x", 0.0)

    renderer = VisualizerRenderer()
    renderer.resize(1280, 720)

    # Baseline metrics at 0% X offset
    m1 = renderer._get_layout_metrics(1280, 720, 1.0, True, True, True, False)
    t1_x = m1["title_rect"].x()

    # Shift layout offset to +15%
    settings.set("layout_title_x", 15.0)
    renderer.reset_layout_cache()

    m2 = renderer._get_layout_metrics(1280, 720, 1.0, True, True, True, False)
    t2_x = m2["title_rect"].x()

    # Offset must translate title_rect X position rightward
    assert t2_x > t1_x + 10.0, f"Title X did not shift as expected: {t1_x} vs {t2_x}"

    # Test GPU Viewport cache invalidation
    viewport = VisualizerViewport()
    viewport.resize(1280, 720)
    settings.set("layout_title_x", 30.0)
    viewport.reset_layout_cache()
    v_x = viewport.gl_widget.bridge._layout_state["title_rect"].x()
    assert v_x > t2_x, f"GPU viewport Title X did not update: {t2_x} vs {v_x}"

    # Clean up settings
    settings.set("layout_title_x", 0.0)
