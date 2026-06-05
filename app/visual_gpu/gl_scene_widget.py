"""OpenGL viewport used as the migration target for heavy scene layers."""
from __future__ import annotations

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
        super().__init__(parent)
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

    def set_scene(self, scene):
        self.scene = scene
        self.bridge.scene = scene
        self.bridge._layout_state = {}
        self.bridge._layout_cache_key = None

    def set_target_fps(self, fps: int):
        self.target_fps = fps
        self.bridge.set_target_fps(fps)

    def set_track_info(self, title: str, artist: str):
        self.track_title = title
        self.track_artist = artist
        self.bridge.set_track_info(title, artist)

    def set_lyrics(self, lyrics):
        self.track_lyrics = lyrics
        self.bridge.set_lyrics(lyrics)

    def set_playback_position(self, position: float):
        self.playback_position = position
        self.bridge.set_playback_position(position)

    def reset(self):
        self.bridge.reset()
        self.scene = self.bridge.scene

    def start(self):
        self.bridge.start()

    def stop(self):
        self.bridge.stop()

    def initializeGL(self):
        # The actual shader replacement will be implemented in later steps.
        pass

    def resizeGL(self, width: int, height: int):
        self.bridge._layout_state = {}

    def paintGL(self):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setRenderHint(QPainter.RenderHint.TextAntialiasing)
        self._render_scene_layers(painter, float(self.width()), float(self.height()), self.frame_dt)
        painter.end()

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
        show_left_hud = settings.get("show_left_hud", True)
        show_right_hud = settings.get("show_right_hud", True)
        show_lyrics = settings.get("show_lyrics", False)
        self.bridge._layout_state = self.bridge._get_layout_metrics(
            width,
            height,
            hud_scale,
            show_title,
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

