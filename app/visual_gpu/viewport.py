"""Composite visualizer viewport for the OpenGL migration renderer."""
from __future__ import annotations

import time

from PySide6.QtGui import QImage, QPainter
from PySide6.QtWidgets import QApplication, QWidget

from ..config.settings import settings
from ..visual.scene import Scene
from .gl_scene_widget import OpenGLSceneWidget
from .hud_overlay import HudOverlayRenderer

_FBO_WATCHDOG_INTERVAL = 2.0  # seconds


class VisualizerViewport(QWidget):
    """Stack an OpenGL scene widget under a transparent HUD overlay."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.scene = Scene()
        self.track_title = ""
        self.track_artist = ""
        self.track_lyrics = None
        self.playback_position = 0.0
        self._last_fbo_watchdog = 0.0
        self.gl_widget = OpenGLSceneWidget(self.scene, self)
        self.overlay = HudOverlayRenderer(self.scene, self)
        self.gl_widget.raise_()
        self.overlay.raise_()

    def resizeEvent(self, event):
        rect = self.rect()
        self.gl_widget.setGeometry(rect)
        self.overlay.setGeometry(rect)
        self._rebuild_layout_state()
        self._sync_overlay_state()
        super().resizeEvent(event)

    def set_scene(self, scene):
        self.scene = scene
        self.gl_widget.set_scene(scene)
        self.overlay.scene = scene
        self._rebuild_layout_state()
        self._sync_overlay_state()

    def _rebuild_layout_state(self):
        width = float(self.width())
        height = float(self.height())
        if width <= 0 or height <= 0:
            return

        layout = self.gl_widget.bridge._get_layout_metrics(
            width,
            height,
            settings.get("hud_scale", 1.0),
            settings.get("show_track_title", True),
            settings.get("show_left_hud", True),
            settings.get("show_right_hud", True),
            settings.get("show_lyrics", False),
        )
        self.gl_widget.bridge._layout_state = layout
        self.overlay._layout_state = dict(layout)

    def _sync_overlay_state(self):
        self.overlay.sync_from_renderer(self.gl_widget.bridge)

    def set_target_fps(self, fps: int):
        self.gl_widget.set_target_fps(fps)
        self.overlay.set_target_fps(fps)

    def set_track_info(self, title: str, artist: str):
        self.track_title = title
        self.track_artist = artist
        self.gl_widget.set_track_info(title, artist)
        self._rebuild_layout_state()
        self._sync_overlay_state()

    def set_lyrics(self, lyrics):
        self.track_lyrics = lyrics
        self.gl_widget.set_lyrics(lyrics)
        self._rebuild_layout_state()
        self._sync_overlay_state()

    def set_playback_position(self, position: float):
        self.playback_position = position
        self.gl_widget.set_playback_position(position)
        self._sync_overlay_state()

    def start(self):
        self.gl_widget.start()
        self.overlay.start()

    def stop(self):
        self.gl_widget.stop()
        self.overlay.stop()

    def reset_layout_cache(self):
        """Reset layout and typography cache across GL widget and HUD overlay."""
        self.gl_widget.reset_layout_cache()
        self.overlay.reset_layout_cache()
        self._rebuild_layout_state()
        self._sync_overlay_state()

    def reset(self):
        self.scene.reset()
        self.gl_widget.set_scene(self.scene)
        self.overlay.scene = self.scene
        self.gl_widget.reset()
        self.overlay.reset()
        self.reset_layout_cache()

    def render_to_image(self, width: int, height: int, frame_dt: float = 0.016) -> QImage:
        """Render a composited frame from the GL scene and HUD overlay."""
        if self.width() != width or self.height() != height:
            self.resize(width, height)
            self.gl_widget.resize(width, height)
            self.overlay.resize(width, height)

        self.gl_widget.frame_dt = frame_dt
        self.overlay.frame_dt = frame_dt
        self._rebuild_layout_state()
        self._sync_overlay_state()

        if not self.isVisible():
            self.move(-20000, -20000)
            self.show()
            QApplication.processEvents()

        self.gl_widget.repaint()
        QApplication.processEvents()

        scene_image = self.gl_widget.grabFramebuffer()
        self._sync_overlay_state()
        overlay_image = self.overlay.render_overlay_to_image(width, height, frame_dt)

        composite = QImage(width, height, QImage.Format.Format_RGBA8888)
        composite.fill(0)
        painter = QPainter(composite)
        painter.drawImage(0, 0, scene_image)
        painter.drawImage(0, 0, overlay_image)
        painter.end()
        return composite

    def update(self):
        self._rebuild_layout_state()
        self._sync_overlay_state()
        self.gl_widget.update()
        self.overlay.update()
        self._run_fbo_watchdog()
        super().update()

    def _run_fbo_watchdog(self):
        """Periodically verify the GL framebuffer matches the widget size.

        Window-state races (minimize/restore around resizes) can leave the
        QOpenGLWidget framebuffer at a stale size, which renders the scene
        clipped with a black block on the remainder (visible GPU-mode bug).
        The watchdog detects and repairs that state within a couple seconds.
        """
        now = time.monotonic()
        if now - self._last_fbo_watchdog < _FBO_WATCHDOG_INTERVAL:
            return
        self._last_fbo_watchdog = now
        self.gl_widget.check_framebuffer_size()
