import pytest
from PySide6.QtWidgets import QApplication

@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    yield app


def test_mainwindow_startup_light_theme_initialization(qapp, monkeypatch):
    """Phase VIII-A: Verify MainWindow initializes in Light Mode when settings.app_theme=light."""
    from app.config.settings import Settings
    from app.ui.main_window import MainWindow

    _original_get = Settings.get
    def mocked_get(self, key, default=None):
        if key == "app_theme":
            return "light"
        return _original_get(self, key, default)

    monkeypatch.setattr(Settings, "get", mocked_get)

    window = MainWindow()

    assert window.objectName() == "mainWindow"
    assert "QWidget#mainWindow" in window.styleSheet()
    assert "background-color: #f8fafc" in window.styleSheet()
    assert "rgba(248, 250, 252, 0.95)" in window.playlist_panel.styleSheet()
    assert "color: #0f172a" in window.title_label.styleSheet()
    assert "color: #334155" in window.artist_label.styleSheet()
    assert "color: #64748b" in window.status_label.styleSheet()
    assert "background: #ffffff" in window.track_info.styleSheet()


def test_settings_dialog_theme_live_update_confirm_and_restore(qapp, monkeypatch):
    """Phase VIII-B: Verify theme live update, dark->light->dark toggling, save persistence, and cancel restoration."""
    from app.ui.main_window import MainWindow
    from app.ui.settings_dialog import SettingsDialog

    window = MainWindow()
    window.settings.set("app_theme", "dark")
    window.settings.set("fps", 60)
    window._apply_settings_values({"app_theme": "dark", "fps": 60})

    assert "background-color: #0b0d19" in window.styleSheet()

    live_updates = []
    dialog = SettingsDialog(
        window,
        settings_data=window.settings.data,
        gpu_available=window._gpu_available,
        render_backend=window._render_backend,
        on_live_update=lambda vals: (live_updates.append(vals), window._apply_settings_values(vals)),
    )

    # 1. Initially dark
    assert "background-color: #0e101f" in dialog.styleSheet()
    assert dialog.fps_combo.findText("30") >= 0

    # 2. Switch to light
    light_idx = 1 if dialog.theme_combo.itemData(1) == "light" else 0
    dialog.theme_combo.setCurrentIndex(light_idx)

    assert "background-color: #f8fafc" in dialog.styleSheet()
    assert "background-color: #ffffff" in dialog.styleSheet()
    assert len(live_updates) > 0
    assert live_updates[-1]["app_theme"] == "light"
    assert "background-color: #f8fafc" in window.styleSheet()
    assert "rgba(248, 250, 252, 0.95)" in window.playlist_panel.styleSheet()

    # 3. Switch back to dark
    dark_idx = 1 if light_idx == 0 else 0
    dialog.theme_combo.setCurrentIndex(dark_idx)
    assert "background-color: #0e101f" in dialog.styleSheet()
    assert live_updates[-1]["app_theme"] == "dark"
    assert "background-color: #0b0d19" in window.styleSheet()

    # 4. Switch to light again
    dialog.theme_combo.setCurrentIndex(light_idx)
    assert "background-color: #f8fafc" in dialog.styleSheet()
    assert live_updates[-1]["app_theme"] == "light"

    # 5. Test Cancel / Restore
    window._restore_settings_snapshot({"app_theme": "dark", "fps": 60}, "cpu")
    assert window.settings.get("app_theme") == "dark"
    assert "background-color: #0b0d19" in window.styleSheet()
    assert window.update_timer.interval() == 17
    assert window.visualizer.target_fps == 60
    assert window._render_backend == "cpu"

    # 6. Test Accept / Save persistence with 30 fps
    fps_30_idx = dialog.fps_combo.findText("30")
    assert fps_30_idx >= 0
    dialog.fps_combo.setCurrentIndex(fps_30_idx)
    collected = dialog.collect_settings()
    assert collected["fps"] == 30
    assert collected["app_theme"] == "light"

    window._apply_settings_values(collected)
    assert window.settings.get("app_theme") == "light"
    assert window.settings.get("fps") == 30
    assert "background-color: #f8fafc" in window.styleSheet()
    assert window.update_timer.interval() == 33
    assert window.visualizer.target_fps == 30


def test_mainwindow_on_settings_clicked_smoke(qapp, monkeypatch):
    """Phase VIII-C: Verify MainWindow._on_settings_clicked opens, accepts, and rejects properly."""
    from app.ui.main_window import MainWindow
    from app.ui.settings_dialog import SettingsDialog

    window = MainWindow()
    window.settings.set("app_theme", "dark")
    window.settings.set("fps", 60)
    window._apply_settings_values({"app_theme": "dark", "fps": 60})

    # Test Accept Flow
    def fake_exec_accept(self):
        self.theme_combo.setCurrentIndex(1 if self.theme_combo.itemData(1) == "light" else 0)
        self.fps_combo.setCurrentText("30")
        return 1

    monkeypatch.setattr(SettingsDialog, "exec", fake_exec_accept)
    window._on_settings_clicked()
    assert window.settings.get("app_theme") == "light"
    assert window.settings.get("fps") == 30
    assert "background-color: #f8fafc" in window.styleSheet()

    # Test Reject / Cancel Flow
    def fake_exec_reject(self):
        self.theme_combo.setCurrentIndex(1 if self.theme_combo.itemData(1) == "dark" else 0)
        self.fps_combo.setCurrentText("120")
        return 0

    monkeypatch.setattr(SettingsDialog, "exec", fake_exec_reject)
    window._on_settings_clicked()
    # Should restore back to pre-click snapshot (which was light, 30)
    assert window.settings.get("app_theme") == "light"
    assert window.settings.get("fps") == 30
