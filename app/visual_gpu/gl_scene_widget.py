"""OpenGL viewport used as the migration target for heavy scene layers."""
from __future__ import annotations
import time

from PySide6.QtCore import QPointF
from PySide6.QtGui import QPainter
from PySide6.QtOpenGLWidgets import QOpenGLWidget

from ..config.settings import settings
from ..visual.renderer import VisualizerRenderer, _clamp


class OpenGLSceneWidget(QOpenGLWidget):
    """
    OpenGL-backed viewport for heavy layers.

    This stage intentionally reuses the existing scene-drawing functions through
    a bridge renderer so the migration can proceed incrementally while keeping
    the original scene logic intact.
    """

    def __init__(self, scene, parent=None):
        from PySide6.QtGui import QSurfaceFormat
        super().__init__(parent)
        fmt = QSurfaceFormat()
        fmt.setSwapInterval(0)
        self.setFormat(fmt)

        self.scene = scene
        self.bridge = VisualizerRenderer()
        self.bridge.hide()
        self.bridge.scene = scene
        self.track_title = ""
        self.track_artist = ""
        self.track_lyrics = None
        self.playback_position = 0.0
        self.target_fps = 60
        self.frame_dt = 0.016
        self.setAutoFillBackground(False)
        self._needs_fbo_check = False

    def set_scene(self, scene):
        self.scene = scene
        self.bridge.scene = scene
        self.bridge._layout_state = {}
        self.bridge._layout_cache_key = None

    def set_target_fps(self, fps: int):
        self.target_fps = fps
        self.bridge.set_target_fps(fps)

    def set_track_info(self, title: str, artist: str, fingerprint: str = "", file_hash: str = ""):
        self.track_title = title
        self.track_artist = artist
        self.bridge.set_track_info(title, artist, fingerprint=fingerprint, file_hash=file_hash)

    def set_lyrics(self, lyrics):
        self.track_lyrics = lyrics
        self.bridge.set_lyrics(lyrics)

    def set_playback_position(self, position: float):
        self.playback_position = position
        self.bridge.set_playback_position(position)

    def reset_layout_cache(self):
        self.bridge.reset_layout_cache()

    def reset(self):
        self.bridge.reset()
        self.scene = self.bridge.scene

    def start(self):
        self.bridge.start()

    def stop(self):
        self.bridge.stop()

    def initializeGL(self):
        pass

    def resizeGL(self, width: int, height: int):
        self.bridge.resize(width, height)
        self.bridge._layout_state = {}
        self.update()

    def showEvent(self, event):
        super().showEvent(event)
        self.update()

    def _record_frame_paint(self, now: float):
        """Record frame timestamp for rolling actual_fps calculation."""
        last_t = getattr(self, "_last_gl_time", 0.0)
        if last_t > 0:
            dt = now - last_t
            if not hasattr(self, "_gl_frame_times"):
                self._gl_frame_times = []
            self._gl_frame_times.append(dt)
            if len(self._gl_frame_times) > 30:
                self._gl_frame_times.pop(0)
            avg_dt = sum(self._gl_frame_times) / max(1, len(self._gl_frame_times))
            self.actual_fps = 1.0 / max(1e-6, avg_dt)
        self._last_gl_time = now

    def paintGL(self):
        self._record_frame_paint(time.perf_counter())
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setRenderHint(QPainter.RenderHint.TextAntialiasing)
        self._render_scene_layers(painter, float(self.width()), float(self.height()), self.frame_dt)
        painter.end()

    def check_framebuffer_size(self):
        """Detect and recover from a stale GL framebuffer size if size changed."""
        if not self.isVisible():
            return
        dpr = self.devicePixelRatioF()
        expected_w = max(1, int(self.width() * dpr + 0.5))
        expected_h = max(1, int(self.height() * dpr + 0.5))
        if getattr(self, "_last_checked_w", None) == expected_w and getattr(self, "_last_checked_h", None) == expected_h:
            return
        self._last_checked_w = expected_w
        self._last_checked_h = expected_h

        image = self.grabFramebuffer()
        if image.isNull():
            return
        if abs(image.width() - expected_w) <= 1 and abs(image.height() - expected_h) <= 1:
            return
        print(
            f"[GL] framebuffer size mismatch: fbo={image.width()}x{image.height()} "
            f"expected={expected_w}x{expected_h} -> forcing recreation"
        )
        geometry = self.geometry()
        self.setGeometry(geometry.adjusted(0, 0, 1, 0))
        self.setGeometry(geometry)
        self.update()

    def _render_scene_layers(self, painter: QPainter, width: float, height: float, frame_dt: float):
        dt = max(frame_dt, 0.0)
        if self.bridge.title_alpha < 1.0:
            self.bridge.title_alpha = min(1.0, self.bridge.title_alpha + dt * 1.5)
        if self.bridge.track_lyrics and self.bridge.track_lyrics.cues and self.bridge.lyrics_alpha < 1.0:
            self.bridge.lyrics_alpha = min(1.0, self.bridge.lyrics_alpha + dt * 1.7)

        if width <= 0 or height <= 0:
            return

        hud_scale = _clamp(settings.get("hud_scale", 1.0), 0.7, 1.5)
        show_title = settings.get("show_track_title", True)
        show_artist = settings.get("show_track_artist", True)
        show_top_info = show_title or show_artist
        show_left_hud = settings.get("show_left_hud", True)
        show_right_hud = settings.get("show_right_hud", True)
        show_lyrics = settings.get("show_lyrics", False)
        self.bridge._layout_state = self.bridge._get_layout_metrics(
            width,
            height,
            hud_scale,
            show_top_info,
            show_left_hud,
            show_right_hud,
            show_lyrics,
        )

        shake_x, shake_y = self.scene.get_camera_offset()
        center = self.bridge._layout_state.get("scene_center", QPointF(width / 2, height / 2))
        cx = center.x() + shake_x
        cy = center.y() + shake_y

        self.bridge._draw_background_layer(painter, width, height, cx, cy)
        if self.scene.theme:
            self.bridge._draw_atmosphere_layer(painter, width, height, cx, cy)
            self.bridge._draw_harmonic_shell_layer(painter, cx, cy, width, height)
            self.bridge._draw_generative_structure(painter, cx, cy, width, height)
            self.bridge._draw_energy_core_layer(painter, cx, cy, width, height)
            self.bridge._draw_transient_lattice_layer(painter, cx, cy, width, height)
            if self.scene.theme.show_particles:
                self.bridge._draw_particles_layer(painter, width, height)
            self.bridge._draw_burst_effects_layer(painter, cx, cy, width, height)

