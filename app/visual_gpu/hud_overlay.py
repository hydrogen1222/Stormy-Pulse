"""Transparent overlay renderer for title, lyrics, and HUD."""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QImage, QPainter

from ..visual.renderer import VisualizerRenderer


class HudOverlayRenderer(VisualizerRenderer):
    """Reuse the existing QPainter HUD stack as a transparent overlay."""

    def __init__(self, scene, parent=None):
        super().__init__(parent)
        self.scene = scene
        self.frame_dt = 0.016
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setStyleSheet("background: transparent; border: none;")

    def sync_from_renderer(self, source: VisualizerRenderer):
        """Mirror state from the scene renderer so both layers stay aligned."""
        self.scene = source.scene
        self.track_title = source.track_title
        self.track_artist = source.track_artist
        self.track_lyrics = source.track_lyrics
        self.playback_position = source.playback_position
        self.title_alpha = source.title_alpha
        self.lyrics_alpha = source.lyrics_alpha
        self.target_fps = source.target_fps
        self._actual_fps = source._actual_fps
        self._hud_smooth = dict(source._hud_smooth)
        self._layout_state = dict(source._layout_state)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setRenderHint(QPainter.RenderHint.TextAntialiasing)
        self._paint_count += 1
        self._update_fps_counter()
        self._render_hud_only(painter, float(self.width()), float(self.height()), self.frame_dt)
        painter.end()

    def render_overlay_to_image(self, width: int, height: int, frame_dt: float = 0.016):
        image = QImage(width, height, QImage.Format.Format_RGBA8888)
        image.fill(0)
        painter = QPainter(image)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setRenderHint(QPainter.RenderHint.TextAntialiasing)
        self._render_hud_only(painter, float(width), float(height), frame_dt)
        painter.end()
        return image

    def _render_hud_only(self, painter: QPainter, width: float, height: float, frame_dt: float):
        dt = max(frame_dt, 0.0)
        if self.title_alpha < 1.0:
            self.title_alpha = min(1.0, self.title_alpha + dt * 1.5)
        if self.track_lyrics and self.track_lyrics.cues and self.lyrics_alpha < 1.0:
            self.lyrics_alpha = min(1.0, self.lyrics_alpha + dt * 1.7)

        if width <= 0 or height <= 0:
            return

        self._draw_huds(painter, width, height)

