"""
Renderer - draws the visualization using QPainter.
"""
import math
import random
import time
import unicodedata
from typing import Dict, Optional

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import (
    QBrush,
    QColor,
    QFont,
    QFontDatabase,
    QFontMetrics,
    QImage,
    QLinearGradient,
    QPainter,
    QPainterPath,
    QPen,
    QRawFont,
    QRadialGradient,
)
from PySide6.QtWidgets import QWidget

from ..config.settings import settings
from ..core.lyrics import TrackLyrics
from .scene import Scene
from .themes import Theme


DEBUG_RENDER = False


def _clamp(v: float, low: float, high: float) -> float:
    return max(low, min(high, v))


def _make_round_pen(color: QColor, width: float) -> QPen:
    pen = QPen(color, width)
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    pen.setCosmetic(False)
    return pen


def _canvas_ratio_from_setting(value: str) -> tuple[str, float]:
    if str(value).strip() == "9:16":
        return "9:16", 9.0 / 16.0
    return "16:9", 16.0 / 9.0


def _normalize_text(value: str) -> str:
    if not value:
        return ""
    return unicodedata.normalize("NFC", str(value).strip())


class VisualizerRenderer(QWidget):
    """Renders the audio visualization."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.scene = Scene()
        self.target_fps = 60
        self._paint_count = 0
        self._last_print_time = time.time()
        self._actual_fps = 0.0
        self.track_title = ""
        self.track_artist = ""
        self.track_lyrics: Optional[TrackLyrics] = None
        self.playback_position = 0.0
        self.title_alpha = 0.0
        self.lyrics_alpha = 0.0
        self._grain_points = [
            (random.random(), random.random(), 0.4 + random.random() * 0.6)
            for _ in range(1300)
        ]
        self._layout_state: Dict[str, object] = {}
        self._layout_cache_key = None
        self._layout_cache_value: Dict[str, object] = {}
        self._typography_cache_key = None
        self._typography_cache_value: Dict[str, QFont] = {}
        self._offscreen_image_cache: Optional[QImage] = None
        self._hud_smooth = {"BASS": 0.0, "RMS": 0.0, "BEAT": 0.0}
        self._font_db = QFontDatabase()
        self._available_families = {name.casefold() for name in self._font_db.families()}
        self._setup_timer()
        print(f"[Renderer] Created. Size: {self.width()}x{self.height()}")

    def _setup_timer(self):
        """Timer is managed by MainWindow for sync."""
        self.timer = None

    def set_target_fps(self, fps: int):
        self.target_fps = fps
        print(f"[Renderer] Target FPS set to: {fps}")

    def _update_fps_counter(self):
        now = time.time()
        elapsed = now - self._last_print_time
        if elapsed >= 0.5:
            self._actual_fps = self._paint_count / max(elapsed, 1e-6)
            self._paint_count = 0
            self._last_print_time = now

    def set_track_info(self, title: str, artist: str, fingerprint: str = ""):
        self.track_title = _normalize_text(title) or "Unknown Track"
        self.track_artist = _normalize_text(artist) or "Unknown Artist"
        self.title_alpha = 0.0
        self._typography_cache_key = None
        
        # Use song's unique fingerprint (from analysis) to seed all visual randomness
        seed_source = fingerprint if fingerprint else f"{title}_{artist}"
        import random
        state = random.getstate() # Preserve global state
        random.seed(seed_source)
        self._grain_points = [
            (random.random(), random.random(), 0.4 + random.random() * 0.6)
            for _ in range(1300)
        ]
        random.setstate(state) # Restore global state

    def set_lyrics(self, lyrics: Optional[TrackLyrics]):
        self.track_lyrics = lyrics
        self.playback_position = 0.0
        self.lyrics_alpha = 0.0
        self._layout_cache_key = None

    def set_playback_position(self, position: float):
        self.playback_position = max(0.0, float(position))

    def start(self):
        pass

    def stop(self):
        pass

    def load_theme(self, theme: Theme):
        self.scene.theme = theme
        self.scene.ring_layer.ring_count = theme.ring_count
        print(f"[Renderer] Theme loaded: {theme.name}, palette={theme.palette_family}")

    def reset_layout_cache(self):
        """Invalidate layout and typography cache."""
        self._layout_state = {}
        self._layout_cache_key = None
        self._layout_cache_value = {}
        self._typography_cache_key = None
        self._typography_cache_value = {}

    def reset(self):
        self.scene.reset()
        self.reset_layout_cache()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setRenderHint(QPainter.RenderHint.TextAntialiasing)
        self._paint_count += 1
        self._update_fps_counter()
        self._render_scene(painter, float(self.width()), float(self.height()), 0.016)

    def render_to_image(
        self,
        width: int,
        height: int,
        frame_dt: float = 0.016,
        reuse_buffer: bool = False,
    ) -> QImage:
        """Render the current scene into an offscreen image at arbitrary resolution."""
        if reuse_buffer:
            if (
                self._offscreen_image_cache is None
                or self._offscreen_image_cache.width() != width
                or self._offscreen_image_cache.height() != height
                or self._offscreen_image_cache.format() != QImage.Format.Format_RGBA8888
            ):
                self._offscreen_image_cache = QImage(width, height, QImage.Format.Format_RGBA8888)
            image = self._offscreen_image_cache
        else:
            image = QImage(width, height, QImage.Format.Format_RGBA8888)
        image.fill(0)
        painter = QPainter(image)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setRenderHint(QPainter.RenderHint.TextAntialiasing)
        self._render_scene(painter, float(width), float(height), frame_dt)
        painter.end()
        return image

    def _render_scene(self, painter: QPainter, width: float, height: float, frame_dt: float):
        """Shared render path for onscreen painting and offscreen export."""
        dt = max(frame_dt, 0.0)
        if self.title_alpha < 1.0:
            self.title_alpha = min(1.0, self.title_alpha + dt * 1.5)
        if self.track_lyrics and self.track_lyrics.cues and self.lyrics_alpha < 1.0:
            self.lyrics_alpha = min(1.0, self.lyrics_alpha + dt * 1.7)

        if width <= 0 or height <= 0:
            return

        hud_scale = _clamp(settings.get("hud_scale", 1.0), 0.7, 1.5)
        show_title = settings.get("show_track_title", True)
        show_left_hud = settings.get("show_left_hud", True)
        show_right_hud = settings.get("show_right_hud", True)
        show_lyrics = settings.get("show_lyrics", False)
        self._layout_state = self._get_layout_metrics(
            width,
            height,
            hud_scale,
            show_title,
            show_left_hud,
            show_right_hud,
            show_lyrics,
        )

        shake_x, shake_y = self.scene.get_camera_offset()
        center = self._layout_state.get("scene_center", QPointF(width / 2, height / 2))
        cx = center.x() + shake_x
        cy = center.y() + shake_y

        self._draw_background_layer(painter, width, height, cx, cy)
        if self.scene.theme:
            self._draw_atmosphere_layer(painter, width, height, cx, cy)
            self._draw_harmonic_shell_layer(painter, cx, cy, width, height)
            self._draw_generative_structure(painter, cx, cy, width, height)
            self._draw_energy_core_layer(painter, cx, cy, width, height)
            self._draw_transient_lattice_layer(painter, cx, cy, width, height)
            if self.scene.theme.show_particles:
                self._draw_particles_layer(painter, width, height)
            self._draw_burst_effects_layer(painter, cx, cy, width, height)
        self._draw_huds(painter, width, height)

    def _layout_settings_signature(self) -> tuple:
        keys = (
            "visual_canvas_ratio",
            "layout_title_x",
            "layout_title_y",
            "layout_artist_x",
            "layout_artist_y",
            "layout_lyrics_x",
            "layout_lyrics_y",
            "layout_left_hud_x",
            "layout_left_hud_y",
            "layout_right_hud_x",
            "layout_right_hud_y",
            "module_scale_title",
            "module_scale_lyrics",
            "module_scale_left_hud",
            "module_scale_right_hud",
            "module_scale_effect",
        )
        return tuple(settings.get(k) for k in keys)

    def _get_layout_metrics(
        self,
        width: float,
        height: float,
        scale: float,
        show_title: bool,
        show_left: bool,
        show_right: bool,
        show_lyrics: bool,
    ) -> Dict[str, object]:
        lyrics_available = bool(self.track_lyrics and self.track_lyrics.cues)
        key = (
            round(width, 3),
            round(height, 3),
            round(scale, 4),
            bool(show_title),
            bool(show_left),
            bool(show_right),
            bool(show_lyrics),
            lyrics_available,
            self._layout_settings_signature(),
        )
        if key != self._layout_cache_key:
            self._layout_cache_value = self._build_layout_metrics(
                width=width,
                height=height,
                scale=scale,
                show_title=show_title,
                show_left=show_left,
                show_right=show_right,
                show_lyrics=show_lyrics,
            )
            self._layout_cache_key = key
        return self._layout_cache_value

    def _typography_settings_signature(self) -> tuple:
        keys = (
            "visual_canvas_ratio",
            "title_font_family",
            "artist_font_family",
            "lyric_font_family",
            "lyric_original_font_family",
            "lyric_translation_font_family",
            "font_scale_title",
            "font_scale_artist",
            "font_scale_lyrics",
            "font_scale_hud",
            "font_scale_left_hud",
            "font_scale_right_hud",
        )
        return tuple(settings.get(k) for k in keys)

    def _get_typography(self, width: float, height: float) -> Dict[str, QFont]:
        key = (round(width, 3), round(height, 3), self._typography_settings_signature())
        if key != self._typography_cache_key:
            self._typography_cache_value = self._build_typography(width, height)
            self._typography_cache_key = key
        return self._typography_cache_value

    def _draw_background_layer(
        self, painter: QPainter, width: float, height: float, cx: float, cy: float
    ):
        """Multi-layer restrained background: base + fog + pulse + grain."""
        theme = self.scene.theme
        effects = self.scene.effects
        frame = self.scene.current_frame
        rms = frame.rms if frame else 0.04
        energy = self.scene.global_features.energy if self.scene.global_features else 0.3
        chaos = self.scene.global_features.chaos if self.scene.global_features else 0.3

        if theme:
            base_color = QColor(*theme.get_color("background_base", 1.0))
            fog_color = QColor(*theme.get_color("background_fog", 1.0))
            halo_color = QColor(*theme.get_color("background_halo", 1.0))
            grid_color = QColor(*theme.get_color("grid_line", 1.0))
            grid_glow = QColor(*theme.get_color("grid_glow", 1.0))
            title_color = QColor(*theme.get_color("title_text", 1.0))
        else:
            base_color = QColor(14, 14, 18, 255)
            fog_color = QColor(28, 34, 40, 255)
            halo_color = QColor(54, 68, 82, 255)
            grid_color = QColor(56, 78, 102, 255)
            grid_glow = QColor(90, 148, 194, 255)
            title_color = QColor(204, 214, 224, 255)

        deep_gradient = QLinearGradient(0, 0, 0, height)
        deep_gradient.setColorAt(
            0.0,
            QColor(
                int(base_color.red() * 0.86),
                int(base_color.green() * 0.86),
                int(base_color.blue() * 0.86),
                255,
            ),
        )
        deep_gradient.setColorAt(
            0.55,
            QColor(
                int(base_color.red() * 0.84),
                int(base_color.green() * 0.84),
                int(base_color.blue() * 0.84),
                255,
            ),
        )
        deep_gradient.setColorAt(
            1.0,
            QColor(
                int(base_color.red() * 0.82),
                int(base_color.green() * 0.82),
                int(base_color.blue() * 0.82),
                255,
            ),
        )
        painter.fillRect(0, 0, int(width), int(height), deep_gradient)

        sweep_grad = QLinearGradient(width * -0.12, cy - height * 0.26, width * 1.04, cy + height * 0.32)
        sweep_grad.setColorAt(0.0, QColor(grid_glow.red(), grid_glow.green(), grid_glow.blue(), 0))
        sweep_grad.setColorAt(0.38, QColor(grid_glow.red(), grid_glow.green(), grid_glow.blue(), int(12 + energy * 8)))
        sweep_grad.setColorAt(0.62, QColor(halo_color.red(), halo_color.green(), halo_color.blue(), int(16 + rms * 22)))
        sweep_grad.setColorAt(1.0, QColor(grid_glow.red(), grid_glow.green(), grid_glow.blue(), 0))
        painter.fillRect(0, 0, int(width), int(height), sweep_grad)

        fog_shift = self.scene.time * (0.04 + (1.0 - chaos) * 0.03)
        fog_breathe = 0.92 + math.sin(self.scene.time * (0.30 + energy * 0.22)) * 0.05
        fog_a = QRadialGradient(
            cx - width * (0.20 + 0.04 * math.sin(fog_shift)),
            cy - height * (0.12 + 0.03 * math.cos(fog_shift * 0.8)),
            width * (0.68 * fog_breathe),
        )
        fog_a.setColorAt(
            0.0,
            QColor(
                fog_color.red(),
                fog_color.green(),
                fog_color.blue(),
                int(26 + rms * 16 + energy * 10),
            ),
        )
        fog_a.setColorAt(0.72, QColor(fog_color.red(), fog_color.green(), fog_color.blue(), 0))
        painter.fillRect(0, 0, int(width), int(height), fog_a)

        fog_b = QRadialGradient(
            cx + width * (0.23 + 0.03 * math.cos(fog_shift * 1.1)),
            cy + height * (0.08 + 0.02 * math.sin(fog_shift * 0.9)),
            width * 0.66,
        )
        fog_b.setColorAt(
            0.0,
            QColor(
                int((fog_color.red() + halo_color.red()) / 2),
                int((fog_color.green() + halo_color.green()) / 2),
                int((fog_color.blue() + halo_color.blue()) / 2),
                int(24 + rms * 14),
            ),
        )
        fog_b.setColorAt(0.76, QColor(halo_color.red(), halo_color.green(), halo_color.blue(), 0))
        painter.fillRect(0, 0, int(width), int(height), fog_b)

        painter.save()
        painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_Plus)
        arc_count = 3
        for idx in range(arc_count):
            arc_radius = max(width, height) * (0.34 + idx * 0.12)
            arc_grad = QRadialGradient(
                cx + math.cos(self.scene.time * 0.22 + idx * 1.7) * width * 0.11,
                cy + math.sin(self.scene.time * 0.18 + idx * 1.2) * height * 0.09,
                arc_radius,
            )
            arc_alpha = int(8 + energy * 7 - idx * 2)
            arc_grad.setColorAt(0.0, QColor(grid_glow.red(), grid_glow.green(), grid_glow.blue(), arc_alpha))
            arc_grad.setColorAt(0.58, QColor(grid_color.red(), grid_color.green(), grid_color.blue(), max(arc_alpha - 5, 0)))
            arc_grad.setColorAt(1.0, QColor(grid_color.red(), grid_color.green(), grid_color.blue(), 0))
            painter.fillRect(0, 0, int(width), int(height), arc_grad)
        painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceOver)
        painter.restore()

        vignette = QRadialGradient(cx, cy, max(width, height) * 0.88)
        vignette.setColorAt(0.62, QColor(base_color.red(), base_color.green(), base_color.blue(), 0))
        vignette.setColorAt(
            1.0,
            QColor(
                int(base_color.red() * 0.70),
                int(base_color.green() * 0.72),
                int(base_color.blue() * 0.78),
                120,
            ),
        )
        painter.fillRect(0, 0, int(width), int(height), vignette)

        env_pulse = _clamp(effects.beat_flash * 0.18 + rms * 0.04 + energy * 0.06, 0.0, 0.18)
        if env_pulse > 0.01:
            pulse_grad = QRadialGradient(cx, cy, max(width, height) * 0.90)
            pulse_grad.setColorAt(
                0.0,
                QColor(
                    halo_color.red(),
                    halo_color.green(),
                    halo_color.blue(),
                    int(34 * env_pulse * 8),
                ),
            )
            pulse_grad.setColorAt(0.78, QColor(halo_color.red(), halo_color.green(), halo_color.blue(), 0))
            painter.fillRect(0, 0, int(width), int(height), pulse_grad)

        grain_alpha = int(5 + _clamp(rms, 0.0, 1.0) * 5)
        grain_color = QColor(
            int((fog_color.red() + title_color.red()) / 2),
            int((fog_color.green() + title_color.green()) / 2),
            int((fog_color.blue() + title_color.blue()) / 2),
            grain_alpha,
        )
        painter.save()
        painter.setPen(grain_color)
        for nx, ny, strength in self._grain_points:
            if strength > 0.48:
                painter.drawPoint(QPointF(nx * width, ny * height))
        painter.restore()

    def _safe_base(self, width: float, height: float) -> float:
        central_rect = self._layout_state.get("central_rect")
        if isinstance(central_rect, QRectF):
            return max(min(central_rect.width(), central_rect.height()), min(width, height) * 0.36)
        return min(width, height)

    def _safe_radius(self, width: float, height: float) -> float:
        safe_radius = self._layout_state.get("safe_radius")
        if isinstance(safe_radius, (int, float)):
            return float(safe_radius)
        return self._safe_base(width, height) * 0.46

    def _draw_energy_core_layer(
        self, painter: QPainter, cx: float, cy: float, width: float, height: float
    ):
        """Layer: central energy core."""
        theme = self.scene.theme
        core = self.scene.energy_core.get_state()
        base = self._safe_base(width, height)
        safe_radius = self._safe_radius(width, height)

        r, g, b, _ = theme.get_color(role="foreground_primary", alpha=1.0)
        base_color = QColor(r, g, b)
        r_acc, g_acc, b_acc, _ = theme.get_color(role="accent", alpha=1.0)
        accent_color = QColor(r_acc, g_acc, b_acc)

        glow_radius = _clamp(core["glow_radius"] * 0.58, base * 0.07, safe_radius * 0.58)
        glow_grad = QRadialGradient(cx, cy, glow_radius)
        glow_grad.setColorAt(0.00, QColor(r_acc, g_acc, b_acc, 0))
        glow_grad.setColorAt(0.14, QColor(r_acc, g_acc, b_acc, int(142 * core["brightness"])))
        glow_grad.setColorAt(0.26, QColor(r, g, b, int(96 * core["brightness"])))
        glow_grad.setColorAt(0.42, QColor(r, g, b, int(24 * core["brightness"])))
        glow_grad.setColorAt(1.0, QColor(0, 0, 0, 0))
        painter.setBrush(QBrush(glow_grad))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawEllipse(QPointF(cx, cy), glow_radius, glow_radius)

        pulse_radius = _clamp(
            core["size"] * (1.05 + core["pulse"] * 0.34),
            base * 0.03,
            safe_radius * 0.66,
        )
        pulse_grad = QRadialGradient(cx, cy, pulse_radius)
        pulse_grad.setColorAt(0.00, QColor(r_acc, g_acc, b_acc, 0))
        pulse_grad.setColorAt(0.46, QColor(r_acc, g_acc, b_acc, 0))
        pulse_grad.setColorAt(0.62, QColor(r_acc, g_acc, b_acc, int(168 * core["brightness"])))
        pulse_grad.setColorAt(0.74, QColor(r, g, b, int(62 * core["brightness"])))
        pulse_grad.setColorAt(1.0, QColor(r, g, b, 0))
        painter.setBrush(QBrush(pulse_grad))
        painter.drawEllipse(QPointF(cx, cy), pulse_radius, pulse_radius)

        painter.save()
        painter.translate(cx, cy)
        line_base = max(base * 0.0022, 1.18)

        inner_size = _clamp(core["size"] * 0.42, base * 0.021, safe_radius * 0.35)
        inner_grad = QRadialGradient(0, 0, inner_size)
        inner_grad.setColorAt(0.00, QColor(255, 255, 255, 255))
        inner_grad.setColorAt(0.22, QColor(244, 248, 255, 245))
        inner_grad.setColorAt(0.58, QColor(r_acc, g_acc, b_acc, 224))
        inner_grad.setColorAt(0.82, QColor(r, g, b, 236))
        inner_grad.setColorAt(1.00, QColor(max(r - 36, 0), max(g - 36, 0), max(b - 32, 0), 255))
        painter.setBrush(QBrush(inner_grad))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawEllipse(QPointF(0, 0), inner_size, inner_size)

        rim_grad = QRadialGradient(0, 0, inner_size * 1.12)
        rim_grad.setColorAt(0.76, QColor(r_acc, g_acc, b_acc, 0))
        rim_grad.setColorAt(0.90, QColor(255, 255, 255, int(180 * core["brightness"])))
        rim_grad.setColorAt(1.00, QColor(r_acc, g_acc, b_acc, 0))
        painter.setBrush(QBrush(rim_grad))
        painter.drawEllipse(QPointF(0, 0), inner_size * 1.12, inner_size * 1.12)

        painter.setBrush(QColor(255, 255, 255, int(138 * core["brightness"])))
        painter.drawEllipse(QPointF(0, 0), inner_size * 0.075, inner_size * 0.075)

        painter.setPen(_make_round_pen(QColor(255, 255, 255, 210), line_base * 0.92))
        spoke_count = 8
        spoke_inner = inner_size * 1.28
        spoke_outer = inner_size * 1.92
        for idx in range(spoke_count):
            angle = core["rotation"] * 1.8 + (idx / spoke_count) * math.pi * 2
            x1 = math.cos(angle) * spoke_inner
            y1 = math.sin(angle) * spoke_inner
            x2 = math.cos(angle) * spoke_outer
            y2 = math.sin(angle) * spoke_outer
            painter.drawLine(QPointF(x1, y1), QPointF(x2, y2))

        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.rotate(math.degrees(core["inner_rotation"]))
        painter.setPen(_make_round_pen(QColor(r_acc, g_acc, b_acc, 218), line_base * 1.18))
        for _ in range(4):
            painter.rotate(90)
            rect = QRectF(-inner_size * 2.1, -inner_size * 2.1, inner_size * 4.2, inner_size * 4.2)
            painter.drawArc(rect, 0, int(16 * 30))

        painter.rotate(math.degrees(core["outer_rotation"] * 1.8))
        r_pri, g_pri, b_pri, _ = theme.get_color(role="foreground_primary", alpha=1.0)
        painter.setPen(
            _make_round_pen(
                QColor(r_pri, g_pri, b_pri, 232),
                line_base * (1.95 + core["pulse"] * 1.65),
            )
        )
        for _ in range(2):
            painter.rotate(180)
            rect = QRectF(-inner_size * 3.0, -inner_size * 3.0, inner_size * 6.0, inner_size * 6.0)
            painter.drawArc(rect, 0, int(16 * 58))

        painter.setPen(_make_round_pen(QColor(255, 255, 255, 92), line_base * 0.88))
        for scale in (2.0, 2.7, 3.45):
            ring_rect = QRectF(-inner_size * scale, -inner_size * scale, inner_size * scale * 2, inner_size * scale * 2)
            painter.drawArc(ring_rect, int(16 * 18), int(16 * 30))
            painter.drawArc(ring_rect, int(16 * 204), int(16 * 24))

        painter.restore()

    def _draw_generative_structure(
        self, painter: QPainter, cx: float, cy: float, width: float, height: float
    ):
        """Route rendering based on structure DNA."""
        dna = self.scene.theme
        if dna.structure_type == "vortex":
            self._draw_structure_vortex(painter, cx, cy, width, height)
        elif dna.structure_type == "pulse":
            self._draw_structure_pulse(painter, cx, cy, width, height)
        elif dna.structure_type == "organic":
            self._draw_structure_organic(painter, cx, cy, width, height)
        else:
            self._draw_structure_reactor(painter, cx, cy, width, height)

    def _draw_structure_reactor(
        self, painter: QPainter, cx: float, cy: float, width: float, height: float
    ):
        """Heavy fragmented shell style."""
        dna = self.scene.theme
        base = self._safe_base(width, height)
        max_radius = self._safe_radius(width, height) * 0.96

        for i in range(dna.ring_count):
            data = self.scene.ring_layer.get_ring_data(i)
            radius = data["radius"] * max_radius
            if radius < base * 0.014:
                continue

            role = "primary" if i % 2 == 0 else "secondary"
            color = QColor(*dna.get_color(role=role, alpha=0.78))
            pen_w = max(base * 0.0012, data["thickness"] * 0.12)
            pen = _make_round_pen(color, pen_w)
            painter.setPen(pen)

            rect = QRectF(cx - radius, cy - radius, radius * 2, radius * 2)
            rot = math.degrees(data["rotation"] * (1.0 + i * 0.18))
            seg_a = 18 + data["radius"] * 28
            seg_b = 14 + data["radius"] * 22
            painter.drawArc(rect, int(rot * 16), int(seg_a * 16))
            painter.drawArc(rect, int((rot + 180) * 16), int(seg_b * 16))

            if dna.detail_style == "spikes" and i % 2 == 0:
                acc = QColor(*dna.get_color(role="accent", alpha=0.80))
                self._draw_attachment_spikes(painter, cx, cy, radius, rot, acc, base)

    def _draw_structure_vortex(
        self, painter: QPainter, cx: float, cy: float, width: float, height: float
    ):
        """Swirling energy bands style."""
        dna = self.scene.theme
        base = self._safe_base(width, height)
        max_radius = self._safe_radius(width, height) * 0.96

        for i in range(dna.ring_count):
            data = self.scene.ring_layer.get_ring_data(i)
            path = QPainterPath()
            role = "primary" if i % 2 == 0 else "secondary"
            color = QColor(*dna.get_color(role=role, alpha=0.60))
            pts = 72
            for j in range(pts + 1):
                t = j / pts
                angle = t * math.pi * 2 + data["rotation"] * (1.0 + i * 0.10)
                r_noise = math.sin(angle * 3 + self.scene.time * 2.1) * (data["radius"] * max_radius * 0.05)
                r = (data["radius"] * max_radius) * (0.90 + t * 0.20) + r_noise
                x = cx + math.cos(angle) * r
                y = cy + math.sin(angle) * r
                if j == 0:
                    path.moveTo(x, y)
                else:
                    path.lineTo(x, y)
            painter.setPen(_make_round_pen(color, max(base * 0.0014, data["thickness"] * 0.08)))
            painter.drawPath(path)

    def _draw_structure_pulse(
        self, painter: QPainter, cx: float, cy: float, width: float, height: float
    ):
        """Radial pulse line style."""
        dna = self.scene.theme
        base = self._safe_base(width, height)
        safe_radius = self._safe_radius(width, height)
        max_radius = safe_radius * 0.94
        line_count = 26 + dna.ring_count * 7

        for i in range(line_count):
            angle = (i / line_count) * math.pi * 2 + self.scene.vortex_angle * 0.2
            ring_idx = i % dna.ring_count
            data = self.scene.ring_layer.get_ring_data(ring_idx)

            r_inner = _clamp(self.scene.energy_core.size * 0.8, base * 0.03, base * 0.16)
            r_outer = r_inner + data["radius"] * max_radius * 0.78
            r_outer = min(r_outer, safe_radius * 0.98)

            role = "primary" if ring_idx % 2 == 0 else "secondary"
            color = QColor(*dna.get_color(role=role, alpha=0.62))
            painter.setPen(_make_round_pen(color, max(base * 0.0010, data["thickness"] * 0.05)))

            x1 = cx + math.cos(angle) * r_inner
            y1 = cy + math.sin(angle) * r_inner
            x2 = cx + math.cos(angle) * r_outer
            y2 = cy + math.sin(angle) * r_outer
            painter.drawLine(QPointF(x1, y1), QPointF(x2, y2))

    def _draw_structure_organic(
        self, painter: QPainter, cx: float, cy: float, width: float, height: float
    ):
        """Wobbly organic ring style."""
        dna = self.scene.theme
        base = self._safe_base(width, height)
        max_radius = self._safe_radius(width, height) * 0.88

        for i in range(dna.ring_count):
            data = self.scene.ring_layer.get_ring_data(i)
            radius = data["radius"] * max_radius
            role = "primary" if i % 2 == 0 else "secondary"
            color = QColor(*dna.get_color(role=role, alpha=0.60))

            path = QPainterPath()
            pts = 84
            for j in range(pts + 1):
                angle = (j / pts) * math.pi * 2
                wobble_1 = math.sin(angle * 4 + self.scene.time * 3.0) * (base * 0.018)
                wobble_2 = math.cos(angle * 7 - self.scene.time * 2.0) * (base * 0.011)
                r = radius + (wobble_1 + wobble_2) * data["radius"]
                x = cx + math.cos(angle + data["rotation"]) * r
                y = cy + math.sin(angle + data["rotation"]) * r
                if j == 0:
                    path.moveTo(x, y)
                else:
                    path.lineTo(x, y)

            path.closeSubpath()
            painter.setPen(_make_round_pen(color, max(base * 0.0011, data["thickness"] * 0.07)))
            painter.drawPath(path)

    def _draw_attachment_spikes(
        self,
        painter: QPainter,
        cx: float,
        cy: float,
        radius: float,
        rotation: float,
        color: QColor,
        base: float,
    ):
        """Detail helper for reactor spikes."""
        spike_len = radius * _clamp(0.12 + base / 5000.0, 0.10, 0.18)
        painter.setPen(_make_round_pen(color, max(base * 0.0012, 1.0)))
        for ang in (0, 90, 180, 270):
            a = math.radians(rotation + ang)
            x1 = cx + math.cos(a) * radius
            y1 = cy + math.sin(a) * radius
            x2 = cx + math.cos(a) * (radius + spike_len)
            y2 = cy + math.sin(a) * (radius + spike_len)
            painter.drawLine(QPointF(x1, y1), QPointF(x2, y2))

    def _draw_atmosphere_layer(
        self, painter: QPainter, width: float, height: float, cx: float, cy: float
    ):
        """Atmosphere layer: moving vortex traces + sparse high-frequency sparks."""
        theme = self.scene.theme
        frame = self.scene.current_frame
        rms = frame.rms if frame else 0.05
        high = frame.high if frame else 0.05
        chaos = self.scene.global_features.chaos if self.scene.global_features else 0.3
        effects = self.scene.effects
        base = self._safe_base(width, height)

        arm_count = 4 + int(chaos * 4)
        max_radius = self._safe_radius(width, height) * 0.96

        r_base, g_base, b_base, _ = theme.get_color(role="foreground_secondary", alpha=1.0)
        for arm in range(arm_count):
            path = QPainterPath()
            for i in range(40):
                t = i / 39.0
                angle = t * math.pi * 2.9 + arm * (math.pi * 2 / arm_count) + self.scene.vortex_angle
                radius = t * max_radius * (1.08 - rms * 0.25)
                x = cx + math.cos(angle) * radius
                y = cy + math.sin(angle) * radius * 0.60
                if i == 0:
                    path.moveTo(x, y)
                else:
                    path.lineTo(x, y)
            alpha = int(14 + rms * 26)
            painter.setPen(_make_round_pen(QColor(r_base, g_base, b_base, alpha), max(base * 0.0012, 1.0)))
            painter.drawPath(path)

        if high > 0.42 or effects.high_energy_flash > 0.10:
            spike_count = int(6 + high * 16)
            r, g, b, _ = theme.get_color(role="accent", alpha=1.0)
            strength = max(high, effects.high_energy_flash)
            pen_w = max(base * 0.0010, 1.0 + strength * base * 0.0030)
            for _ in range(spike_count):
                angle = random.random() * math.pi * 2
                inner_r = _clamp(self.scene.energy_core.size * 0.88, base * 0.03, base * 0.16)
                outer_r = inner_r + strength * base * (0.20 + random.random() * 0.10)
                x1 = cx + math.cos(angle) * inner_r
                y1 = cy + math.sin(angle) * inner_r * 0.82
                x2 = cx + math.cos(angle) * outer_r
                y2 = cy + math.sin(angle) * outer_r * 0.82
                painter.setPen(_make_round_pen(QColor(r, g, b, int(strength * 170)), pen_w))
                painter.drawLine(QPointF(x1, y1), QPointF(x2, y2))

    def _draw_harmonic_shell_layer(
        self, painter: QPainter, cx: float, cy: float, width: float, height: float
    ):
        """Audio-reactive harmonic shells driven by smoothed multi-band controls."""
        theme = self.scene.theme
        if not theme:
            return

        drive = self.scene.get_audio_drive()
        base = self._safe_base(width, height)
        safe_radius = self._safe_radius(width, height)
        bass = _clamp(float(drive.get("bass", 0.0)), 0.0, 1.0)
        mid = _clamp(float(drive.get("mid", 0.0)), 0.0, 1.0)
        high = _clamp(float(drive.get("high", 0.0)), 0.0, 1.0)
        onset = _clamp(float(drive.get("onset", 0.0)), 0.0, 1.0)
        pressure = _clamp(float(drive.get("pressure", 0.0)), 0.0, 1.0)
        sparkle = _clamp(float(drive.get("sparkle", 0.0)), 0.0, 1.0)
        tension = _clamp(float(drive.get("tension", 0.0)), 0.0, 1.0)
        centroid = _clamp(float(drive.get("centroid", 0.0)), 0.0, 1.0)
        rolloff = _clamp(float(drive.get("rolloff", 0.0)), 0.0, 1.0)

        overall_drive = _clamp(0.24 + pressure * 0.44 + onset * 0.32, 0.0, 1.0)
        if overall_drive < 0.08:
            return

        band_values = [bass, mid, high]
        role_map = ("foreground_primary", "foreground_secondary", "accent")
        painter.save()
        painter.setBrush(Qt.BrushStyle.NoBrush)
        for idx, band_value in enumerate(band_values):
            role = role_map[idx]
            r, g, b, _ = theme.get_color(role=role, alpha=1.0)
            radius = safe_radius * (0.30 + idx * 0.10 + pressure * 0.05)
            radius = _clamp(radius, base * 0.10, safe_radius * 0.94)
            lobes = 4 + idx * 2 + int((centroid + rolloff) * 4)
            wave = safe_radius * (0.012 + band_value * 0.042 + onset * 0.020)
            wave2 = safe_radius * (0.007 + sparkle * 0.020 + tension * 0.012)

            geom = getattr(self.scene, "current_geometry_control", None)
            if geom is not None:
                lobes = max(3, int(round(lobes * (0.6 + 0.8 * geom.symmetry))))
                wave *= (0.7 + 0.6 * geom.coherence)
                wave2 *= (0.8 + 0.8 * geom.roughness)
            point_count = 88 + idx * 20
            path = QPainterPath()
            for pidx in range(point_count + 1):
                t = pidx / float(point_count)
                angle = t * math.pi * 2
                wobble_a = math.sin(angle * lobes + self.scene.time * (1.1 + idx * 0.30) + idx * 0.7) * wave
                wobble_b = math.cos(angle * (lobes * 0.5 + 1.0) - self.scene.time * (1.9 + idx * 0.24)) * wave2
                rr = radius + wobble_a + wobble_b
                x = cx + math.cos(angle) * rr
                y = cy + math.sin(angle) * rr * (0.96 + idx * 0.02)
                if pidx == 0:
                    path.moveTo(x, y)
                else:
                    path.lineTo(x, y)
            alpha = int(_clamp((42 + band_value * 128 + overall_drive * 64) * (0.76 + idx * 0.10), 0.0, 255.0))
            pen_w = max(base * (0.0012 + band_value * 0.0020), 0.9)
            painter.setPen(_make_round_pen(QColor(r, g, b, alpha), pen_w))
            painter.drawPath(path)
        painter.restore()

    def _draw_transient_lattice_layer(
        self, painter: QPainter, cx: float, cy: float, width: float, height: float
    ):
        """Transient beat/onset lattice for stronger visual hits."""
        theme = self.scene.theme
        if not theme:
            return

        drive = self.scene.get_audio_drive()
        effects = self.scene.effects
        base = self._safe_base(width, height)
        safe_radius = self._safe_radius(width, height)

        onset = _clamp(float(drive.get("onset", 0.0)), 0.0, 1.0)
        beat = _clamp(float(drive.get("beat", 0.0)), 0.0, 1.0)
        high = _clamp(float(drive.get("high", 0.0)), 0.0, 1.0)
        tension = _clamp(float(drive.get("tension", 0.0)), 0.0, 1.0)
        density = _clamp(float(drive.get("density", 0.0)), 0.0, 1.0)
        flash = _clamp(float(effects.high_energy_flash), 0.0, 1.0)
        intensity = _clamp(onset * 0.46 + beat * 0.28 + high * 0.16 + flash * 0.34, 0.0, 1.0)
        if intensity < 0.06:
            return

        r_acc, g_acc, b_acc, _ = theme.get_color(role="accent", alpha=1.0)
        r_pri, g_pri, b_pri, _ = theme.get_color(role="foreground_primary", alpha=1.0)
        ray_count = int(_clamp(20 + intensity * 58 + density * 16, 20, 96))
        inner_r = _clamp(self.scene.energy_core.size * 0.80, base * 0.04, safe_radius * 0.36)
        outer_base = safe_radius * (0.28 + intensity * 0.42 + tension * 0.10)
        angle_speed = 0.18 + high * 0.55 + beat * 0.35

        painter.save()
        painter.setBrush(Qt.BrushStyle.NoBrush)
        for idx in range(ray_count):
            t = idx / max(1.0, float(ray_count))
            angle = t * math.pi * 2 + self.scene.time * angle_speed
            variance = 0.80 + 0.20 * math.sin(self.scene.time * 4.4 + idx * 0.77)
            outer_r = inner_r + outer_base * variance

            x1 = cx + math.cos(angle) * inner_r
            y1 = cy + math.sin(angle) * inner_r
            x2 = cx + math.cos(angle) * outer_r
            y2 = cy + math.sin(angle) * outer_r

            alpha = int(_clamp(42 + intensity * 190 + (0.5 + 0.5 * math.sin(idx * 0.38 + self.scene.time * 2.4)) * 28, 0.0, 235.0))
            line_w = max(base * (0.0009 + intensity * 0.0018), 0.8)
            color = QColor(r_acc, g_acc, b_acc, alpha) if idx % 2 == 0 else QColor(r_pri, g_pri, b_pri, int(alpha * 0.78))
            painter.setPen(_make_round_pen(color, line_w))
            painter.drawLine(QPointF(x1, y1), QPointF(x2, y2))

            if idx % 3 == 0 and intensity > 0.18:
                tip_size = _clamp(base * (0.0013 + intensity * 0.0026), 0.9, base * 0.010)
                painter.setPen(Qt.PenStyle.NoPen)
                painter.setBrush(QColor(r_acc, g_acc, b_acc, int(alpha * 0.82)))
                painter.drawEllipse(QPointF(x2, y2), tip_size, tip_size * 0.86)
                painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.restore()

    def _draw_particles_layer(self, painter: QPainter, width: float, height: float):
        """Particle system layer."""
        theme = self.scene.theme
        base = self._safe_base(width, height)
        trail_w = max(base * 0.0011, 1.0)
        layout_center = self._layout_state.get("scene_center")
        if isinstance(layout_center, QPointF):
            anchor_x, anchor_y = self.scene.last_update_center
            offset_x = layout_center.x() - anchor_x
            offset_y = layout_center.y() - anchor_y
        else:
            offset_x = 0.0
            offset_y = 0.0
        for p in self.scene.particles.get_particles():
            life_ratio = _clamp(p.life / max(p.max_life, 1e-6), 0.0, 1.0)
            if p.life > 0.5:
                r, g, b, _ = theme.get_color(role="accent", alpha=1.0)
            else:
                r, g, b, _ = theme.get_color(role="foreground_primary", alpha=1.0)

            alpha = int((220 if p.is_spark else 118) * life_ratio)
            color = QColor(r, g, b, alpha)
            painter.setBrush(QBrush(color))
            painter.setPen(Qt.PenStyle.NoPen)
            size = p.size * (0.58 if p.is_spark else 0.34)
            size = _clamp(size, base * 0.0009, base * (0.0065 if p.is_spark else 0.0032))
            painter.drawEllipse(QPointF(p.x + offset_x, p.y + offset_y), size, size * (0.78 if p.is_spark else 0.72))

            if len(p.trail) > 2:
                path = QPainterPath()
                path.moveTo(p.trail[0][0] + offset_x, p.trail[0][1] + offset_y)
                for tx, ty in p.trail[1:]:
                    path.lineTo(tx + offset_x, ty + offset_y)
                trail_alpha = int(alpha * (0.42 if p.is_spark else 0.22))
                painter.setPen(_make_round_pen(QColor(r, g, b, trail_alpha), trail_w * (0.85 if p.is_spark else 0.6)))
                painter.setBrush(Qt.BrushStyle.NoBrush)
                painter.drawPath(path)

    def _draw_burst_effects_layer(
        self, painter: QPainter, cx: float, cy: float, width: float, height: float
    ):
        """Beat burst and shockwave effects."""
        effects = self.scene.effects
        theme = self.scene.theme
        base = self._safe_base(width, height)
        safe_radius = self._safe_radius(width, height)

        if effects.shockwave_active:
            r, g, b, _ = theme.get_color(role="accent", alpha=1.0)
            alpha = int(effects.shockwave_strength * 190)
            radius = _clamp(effects.shockwave_radius, base * 0.06, safe_radius * 0.96)
            edge = radius + base * 0.02
            grad = QRadialGradient(cx, cy, edge)
            grad.setColorAt(0.84, QColor(0, 0, 0, 0))
            grad.setColorAt(0.95, QColor(r, g, b, alpha))
            grad.setColorAt(1.0, QColor(0, 0, 0, 0))
            painter.setBrush(QBrush(grad))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawEllipse(QPointF(cx, cy), edge, edge)

        if effects.beat_flash > 0.1:
            r, g, b, _ = theme.get_color(role="foreground_primary", alpha=1.0)
            flash_alpha = int(effects.beat_flash * 54)
            painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_Plus)
            painter.fillRect(0, 0, int(width), int(height), QColor(r, g, b, flash_alpha))
            painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceOver)

        if effects.high_energy_flash > 0.08:
            r_acc, g_acc, b_acc, _ = theme.get_color(role="accent", alpha=1.0)
            ring_alpha = int(_clamp(58 + effects.high_energy_flash * 122, 0.0, 210.0))
            ring_radius = _clamp(self.scene.energy_core.size * (2.1 + effects.high_energy_flash * 1.9), base * 0.12, safe_radius * 0.98)
            painter.setPen(
                _make_round_pen(
                    QColor(r_acc, g_acc, b_acc, ring_alpha),
                    max(base * (0.0012 + effects.high_energy_flash * 0.0020), 1.0),
                )
            )
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawEllipse(QPointF(cx, cy), ring_radius, ring_radius * 0.92)

    def _build_layout_metrics(
        self,
        width: float,
        height: float,
        scale: float,
        show_title: bool,
        show_left: bool,
        show_right: bool,
        show_lyrics: bool,
    ) -> Dict[str, object]:
        """Build layout from a strict virtual canvas with aspect-aware composition."""
        outer_pad = min(width, height) * 0.014
        avail_w = max(10.0, width - outer_pad * 2)
        avail_h = max(10.0, height - outer_pad * 2)
        canvas_ratio_key, canvas_ratio = _canvas_ratio_from_setting(settings.get("visual_canvas_ratio", "16:9"))
        canvas_w = avail_w
        canvas_h = canvas_w / canvas_ratio
        if canvas_h > avail_h:
            canvas_h = avail_h
            canvas_w = canvas_h * canvas_ratio

        canvas_rect = QRectF(
            (width - canvas_w) * 0.5,
            (height - canvas_h) * 0.5,
            canvas_w,
            canvas_h,
        )

        unit = min(canvas_rect.width(), canvas_rect.height())
        inset_x = canvas_rect.width() * 0.018
        inset_y = canvas_rect.height() * 0.024
        lyrics_visible = bool(show_lyrics and self.track_lyrics and self.track_lyrics.cues)
        title_block_scale = _clamp(self._setting_float("module_scale_title", 1.0), 0.65, 1.85)
        lyrics_block_scale = _clamp(self._setting_float("module_scale_lyrics", 1.0), 0.65, 1.85)
        left_hud_block_scale = _clamp(self._setting_float("module_scale_left_hud", 1.0), 0.65, 1.85)
        right_hud_block_scale = _clamp(self._setting_float("module_scale_right_hud", 1.0), 0.65, 1.85)
        effect_block_scale = _clamp(self._setting_float("module_scale_effect", 1.0), 0.65, 1.85)

        if canvas_ratio_key == "9:16":
            side_margin = inset_x * 0.36
            hud_gap = canvas_rect.width() * 0.06
            usable_pair_w = max(120.0, canvas_rect.width() - side_margin * 2 - hud_gap)

            brand_w = _clamp(
                canvas_rect.width() * (0.42 + (scale - 1.0) * 0.02) * left_hud_block_scale,
                128.0,
                usable_pair_w * 0.62,
            )
            brand_h = _clamp(
                canvas_rect.height() * (0.062 + (scale - 1.0) * 0.010) * left_hud_block_scale,
                42.0,
                110.0,
            )

            monitor_w = _clamp(
                canvas_rect.width() * (0.42 + (scale - 1.0) * 0.02) * right_hud_block_scale,
                144.0,
                usable_pair_w * 0.66,
            )
            monitor_h = _clamp(
                canvas_rect.height() * (0.084 + (scale - 1.0) * 0.012) * right_hud_block_scale,
                64.0,
                canvas_rect.height() * 0.20,
            )

            if brand_w + monitor_w > usable_pair_w:
                ratio = usable_pair_w / max(brand_w + monitor_w, 1.0)
                brand_w = max(136.0, brand_w * ratio)
                monitor_w = max(152.0, monitor_w * ratio)

            left_brand_rect = QRectF(
                canvas_rect.left() + side_margin,
                canvas_rect.bottom() - inset_y * 0.44 - brand_h,
                brand_w,
                brand_h,
            )
            right_monitor_rect = QRectF(
                canvas_rect.right() - side_margin - monitor_w,
                canvas_rect.bottom() - inset_y * 0.44 - monitor_h,
                monitor_w,
                monitor_h,
            )

            title_h = _clamp(
                canvas_rect.height() * (0.118 + (scale - 1.0) * 0.016) * title_block_scale,
                58.0,
                228.0,
            ) if show_title else 0.0
            title_w = _clamp(
                canvas_rect.width() * (0.84 if lyrics_visible else 0.86) * title_block_scale,
                canvas_rect.width() * 0.40,
                canvas_rect.width() * 0.96,
            ) if show_title else 0.0
            title_rect = QRectF(
                canvas_rect.center().x() - title_w * 0.5,
                canvas_rect.top() + canvas_rect.height() * 0.016,
                title_w,
                title_h,
            )

            central_top = title_rect.bottom() + canvas_rect.height() * 0.012 if show_title else canvas_rect.top() + inset_y
            bottom_limits = [canvas_rect.bottom() - inset_y]
            if show_left:
                bottom_limits.append(left_brand_rect.top())
            if show_right:
                bottom_limits.append(right_monitor_rect.top())
            central_bottom = min(bottom_limits) - canvas_rect.height() * 0.020

            lyrics_rect = QRectF()
            if lyrics_visible:
                lyrics_h = _clamp(
                    canvas_rect.height() * (0.165 + (scale - 1.0) * 0.015) * lyrics_block_scale,
                    canvas_rect.height() * 0.10,
                    canvas_rect.height() * 0.33,
                )
                lyrics_w = _clamp(
                    (canvas_rect.width() - inset_x * 0.56) * lyrics_block_scale,
                    canvas_rect.width() * 0.52,
                    canvas_rect.width() - inset_x * 0.24,
                )
                lyrics_rect = QRectF(
                    canvas_rect.center().x() - lyrics_w * 0.5,
                    central_bottom - lyrics_h,
                    lyrics_w,
                    lyrics_h,
                )
                central_bottom = lyrics_rect.top() - canvas_rect.height() * 0.024

            scene_center = QPointF(
                canvas_rect.center().x(),
                central_top + max(central_bottom - central_top, canvas_rect.height() * 0.26) * (0.43 if lyrics_visible else 0.51),
            )
            available_w = canvas_rect.width() - inset_x * 0.55
            available_h = max(central_bottom - central_top, canvas_rect.height() * 0.32)
            fit_h = available_h
            fit_w = fit_h * canvas_ratio
            if fit_w > available_w:
                fit_w = available_w
                fit_h = fit_w / canvas_ratio

            central_rect = QRectF(
                scene_center.x() - fit_w * 0.5,
                scene_center.y() - fit_h * 0.5,
                fit_w,
                fit_h,
            )
            safe_radius = _clamp(
                max(
                    min(canvas_rect.width() * 0.34, available_h * 0.46),
                    unit * 0.21,
                ) * effect_block_scale,
                unit * 0.16,
                min(fit_w, fit_h) * 0.66,
            )

            window_bounds = QRectF(0, 0, width, height)
            title_dx, title_dy = self._module_offset("title", canvas_rect)
            left_dx, left_dy = self._module_offset("left_hud", canvas_rect)
            right_dx, right_dy = self._module_offset("right_hud", canvas_rect)
            title_rect = self._shift_rect_clamped(title_rect, window_bounds, title_dx, title_dy)
            left_brand_rect = self._shift_rect_clamped(left_brand_rect, window_bounds, left_dx, left_dy)
            right_monitor_rect = self._shift_rect_clamped(right_monitor_rect, window_bounds, right_dx, right_dy)
            if lyrics_visible and lyrics_rect.width() > 1.0 and lyrics_rect.height() > 1.0:
                lyrics_dx, lyrics_dy = self._module_offset("lyrics", canvas_rect)
                lyrics_rect = self._shift_rect_clamped(lyrics_rect, window_bounds, lyrics_dx, lyrics_dy)

            return {
                "canvas_ratio_key": canvas_ratio_key,
                "canvas_rect": canvas_rect,
                "title_rect": title_rect,
                "left_brand_rect": left_brand_rect,
                "right_monitor_rect": right_monitor_rect,
                "lyrics_rect": lyrics_rect,
                "lyrics_visible": lyrics_visible,
                "central_rect": central_rect,
                "scene_center": scene_center,
                "safe_radius": safe_radius,
            }

        hud_edge_x = canvas_rect.left() + inset_x * 0.45
        hud_edge_y = canvas_rect.bottom() - inset_y * 0.72
        brand_w = _clamp(
            canvas_rect.width() * (0.22 + (scale - 1.0) * 0.04) * left_hud_block_scale,
            unit * 0.20,
            canvas_rect.width() * 0.44,
        )
        brand_h = _clamp(
            canvas_rect.height() * (0.10 + (scale - 1.0) * 0.025) * left_hud_block_scale,
            38.0,
            168.0,
        )
        left_brand_rect = QRectF(
            hud_edge_x,
            hud_edge_y - brand_h,
            brand_w,
            brand_h,
        )

        right_column_w = _clamp(
            canvas_rect.width() * (0.28 + (scale - 1.0) * 0.03) * lyrics_block_scale,
            170.0,
            canvas_rect.width() * 0.46,
        ) if lyrics_visible else 0.0
        right_column_right = canvas_rect.right() - inset_x * 0.22
        right_column_left = right_column_right - right_column_w
        lyrics_gap = canvas_rect.width() * 0.040 if lyrics_visible else 0.0

        left_limit = left_brand_rect.right() + canvas_rect.width() * 0.060 if show_left else canvas_rect.left() + inset_x
        right_limit = right_column_left - lyrics_gap if lyrics_visible else (
            canvas_rect.right() - inset_x
        )
        min_scene_w = canvas_rect.width() * (0.26 if lyrics_visible else 0.24)
        if right_limit <= left_limit + min_scene_w:
            right_limit = left_limit + min_scene_w

        scene_center_x = (left_limit + right_limit) * 0.5
        title_h = _clamp(
            canvas_rect.height() * (0.17 + (scale - 1.0) * 0.03) * title_block_scale,
            44.0,
            222.0,
        ) if show_title else 0.0
        title_w = min(
            max(right_limit - left_limit, canvas_rect.width() * 0.30) * 0.88 * title_block_scale,
            canvas_rect.width() * (0.40 if lyrics_visible else 0.56),
        ) if show_title else 0.0
        title_rect = QRectF(
            scene_center_x - title_w * 0.5,
            canvas_rect.top() + canvas_rect.height() * 0.028,
            title_w,
            title_h,
        )

        if lyrics_visible:
            monitor_w = _clamp(right_column_w * 0.98 * right_hud_block_scale, 144.0, canvas_rect.width() * 0.44)
            monitor_h = _clamp(
                canvas_rect.height() * (0.17 + (scale - 1.0) * 0.035) * right_hud_block_scale,
                86.0,
                canvas_rect.height() * 0.34,
            )
            right_monitor_rect = QRectF(
                right_column_right - monitor_w,
                hud_edge_y - monitor_h,
                monitor_w,
                monitor_h,
            )
        else:
            monitor_w = _clamp(
                canvas_rect.width() * (0.19 + (scale - 1.0) * 0.05) * right_hud_block_scale,
                132.0,
                canvas_rect.width() * 0.36,
            )
            monitor_h = _clamp(
                canvas_rect.height() * (0.205 + (scale - 1.0) * 0.04) * right_hud_block_scale,
                96.0,
                canvas_rect.height() * 0.40,
            )
            right_monitor_rect = QRectF(
                canvas_rect.right() - inset_x * 0.45 - monitor_w,
                hud_edge_y - monitor_h,
                monitor_w,
                monitor_h,
            )

        if show_title and not lyrics_visible:
            title_right_limit = right_monitor_rect.left() - canvas_rect.width() * 0.060 if show_right else canvas_rect.right() - inset_x
            title_center_x = (left_limit + title_right_limit) * 0.5
            title_w = min(
                max(title_right_limit - left_limit, canvas_rect.width() * 0.30) * 0.88 * title_block_scale,
                canvas_rect.width() * 0.56,
            )
            title_rect = QRectF(
                title_center_x - title_w * 0.5,
                canvas_rect.top() + canvas_rect.height() * 0.028,
                title_w,
                title_h,
            )

        central_top = title_rect.bottom() + canvas_rect.height() * 0.060 if show_title else canvas_rect.top() + inset_y
        bottom_limits = [canvas_rect.bottom() - inset_y]
        if show_left:
            bottom_limits.append(left_brand_rect.top() - canvas_rect.height() * 0.042)
        if show_right:
            bottom_limits.append(right_monitor_rect.top() - canvas_rect.height() * 0.048)
        central_bottom = min(bottom_limits)
        if central_bottom <= central_top + canvas_rect.height() * 0.18:
            central_bottom = central_top + canvas_rect.height() * 0.18

        lyrics_rect = QRectF()
        if lyrics_visible:
            lyrics_top = central_top + canvas_rect.height() * 0.006
            lyrics_bottom = min(
                canvas_rect.bottom() - inset_y * 0.6,
                (right_monitor_rect.top() - canvas_rect.height() * 0.035) if show_right else (canvas_rect.bottom() - inset_y),
            )
            if lyrics_bottom <= lyrics_top + canvas_rect.height() * 0.18:
                lyrics_bottom = lyrics_top + canvas_rect.height() * 0.18
            lyrics_h = max(1.0, (lyrics_bottom - lyrics_top) * lyrics_block_scale)
            lyrics_h = min(lyrics_h, canvas_rect.bottom() - lyrics_top)
            lyrics_rect = QRectF(
                right_column_left,
                lyrics_top,
                right_column_w,
                lyrics_h,
            )

        left_safe = left_limit
        right_safe = lyrics_rect.left() - lyrics_gap if lyrics_visible else (
            right_monitor_rect.left() - canvas_rect.width() * 0.060 if show_right else canvas_rect.right() - inset_x
        )
        if right_safe <= left_safe + canvas_rect.width() * 0.24:
            left_safe = canvas_rect.left() + canvas_rect.width() * 0.18
            right_safe = (lyrics_rect.left() - lyrics_gap) if lyrics_visible else (canvas_rect.right() - canvas_rect.width() * 0.18)

        scene_center = QPointF((left_safe + right_safe) * 0.5, (central_top + central_bottom) * 0.5)
        available_w = max(right_safe - left_safe, canvas_rect.width() * 0.24)
        available_h = max(central_bottom - central_top, canvas_rect.height() * 0.18)
        fit_w = available_w
        fit_h = fit_w / canvas_ratio
        if fit_h > available_h:
            fit_h = available_h
            fit_w = fit_h * canvas_ratio

        central_rect = QRectF(
            scene_center.x() - fit_w * 0.5,
            scene_center.y() - fit_h * 0.5,
            fit_w,
            fit_h,
        )
        safe_radius = _clamp(
            max(min(fit_w, fit_h) * 0.46, unit * 0.17) * effect_block_scale,
            unit * 0.14,
            min(fit_w, fit_h) * 0.66,
        )

        window_bounds = QRectF(0, 0, width, height)
        title_dx, title_dy = self._module_offset("title", canvas_rect)
        left_dx, left_dy = self._module_offset("left_hud", canvas_rect)
        right_dx, right_dy = self._module_offset("right_hud", canvas_rect)
        title_rect = self._shift_rect_clamped(title_rect, window_bounds, title_dx, title_dy)
        left_brand_rect = self._shift_rect_clamped(left_brand_rect, window_bounds, left_dx, left_dy)
        right_monitor_rect = self._shift_rect_clamped(right_monitor_rect, window_bounds, right_dx, right_dy)
        if lyrics_visible and lyrics_rect.width() > 1.0 and lyrics_rect.height() > 1.0:
            lyrics_dx, lyrics_dy = self._module_offset("lyrics", canvas_rect)
            lyrics_rect = self._shift_rect_clamped(lyrics_rect, window_bounds, lyrics_dx, lyrics_dy)

        return {
            "canvas_ratio_key": canvas_ratio_key,
            "canvas_rect": canvas_rect,
            "title_rect": title_rect,
            "left_brand_rect": left_brand_rect,
            "right_monitor_rect": right_monitor_rect,
            "lyrics_rect": lyrics_rect,
            "lyrics_visible": lyrics_visible,
            "central_rect": central_rect,
            "scene_center": scene_center,
            "safe_radius": safe_radius,
        }

    def _build_typography(self, width: float, height: float) -> Dict[str, QFont]:
        """Unified typography system across title / subtitle / lyric / HUD."""
        base = min(width, height)
        canvas_ratio_key, _ = _canvas_ratio_from_setting(settings.get("visual_canvas_ratio", "16:9"))
        is_vertical = canvas_ratio_key == "9:16"
        title_family = settings.get("title_font_family", "")
        subtitle_family = settings.get("artist_font_family", "")
        legacy_lyric_family = settings.get("lyric_font_family", "")
        lyric_original_family = settings.get("lyric_original_font_family", "") or legacy_lyric_family
        lyric_translation_family = settings.get("lyric_translation_font_family", "") or legacy_lyric_family

        global_fallback = [
            "Segoe UI",
            "Segoe UI Variable Display",
            "Noto Sans",
            "Noto Sans CJK SC",
            "Noto Sans CJK JP",
            "Microsoft YaHei UI",
            "Yu Gothic UI",
            "Meiryo UI",
        ]
        hud_fallback = [
            "Bahnschrift",
            "DIN",
            "Segoe UI",
            "Noto Sans",
            "Microsoft YaHei UI",
            "Yu Gothic UI",
        ]

        title_font = self._make_font(
            title_family,
            global_fallback,
            _clamp(base * (0.050 if is_vertical else 0.043), 20.0 if is_vertical else 18.0, 220.0),
            QFont.Weight.DemiBold,
            _clamp(base * 0.0028, 0.5, 3.6),
        )
        subtitle_font = self._make_font(
            subtitle_family,
            global_fallback,
            _clamp(base * (0.028 if is_vertical else 0.021), 12.0 if is_vertical else 10.0, 128.0),
            QFont.Weight.Medium,
            _clamp(base * 0.0018, 0.2, 2.2),
        )

        lyric_active = self._make_font(
            lyric_original_family,
            global_fallback,
            _clamp(base * (0.030 if is_vertical else 0.026), 14.0 if is_vertical else 15.0, 140.0),
            QFont.Weight.DemiBold,
            _clamp(base * 0.0015, 0.1, 1.8),
        )
        lyric_secondary = self._make_font(
            lyric_translation_family,
            global_fallback,
            _clamp(base * (0.022 if is_vertical else 0.018), 10.0 if is_vertical else 10.0, 96.0),
            QFont.Weight.Medium,
            _clamp(base * 0.0012, 0.0, 1.4),
        )
        lyric_context = self._make_font(
            lyric_original_family,
            global_fallback,
            _clamp(base * (0.023 if is_vertical else 0.020), 10.5 if is_vertical else 11.0, 104.0),
            QFont.Weight.Normal,
            _clamp(base * 0.0012, 0.0, 1.4),
        )

        brand_label = self._make_font(
            subtitle_family,
            hud_fallback,
            _clamp(base * 0.020, 9.5, 84.0),
            QFont.Weight.DemiBold,
            _clamp(base * 0.0020, 0.4, 2.6),
        )
        brand_theme = self._make_font(
            title_family,
            hud_fallback,
            _clamp(base * 0.026, 11.0, 108.0),
            QFont.Weight.Bold,
            _clamp(base * 0.0024, 0.5, 3.2),
        )
        hud_label = self._make_font(
            subtitle_family,
            hud_fallback,
            _clamp(base * 0.019, 9.0, 80.0),
            QFont.Weight.DemiBold,
            _clamp(base * 0.0018, 0.3, 2.2),
        )
        hud_value = self._make_font(
            "Consolas",
            ["Cascadia Mono", "JetBrains Mono", "Noto Sans Mono", "Segoe UI"],
            _clamp(base * 0.0145, 8.0, 60.0),
            QFont.Weight.Normal,
            _clamp(base * 0.0012, 0.1, 1.4),
        )

        debug_font = self._make_font(
            "Consolas",
            ["Cascadia Mono", "JetBrains Mono", "Noto Sans Mono", "Segoe UI"],
            _clamp(base * 0.0125, 7.0, 52.0),
            QFont.Weight.Normal,
            _clamp(base * 0.0010, 0.1, 1.2),
        )

        title_scale = _clamp(self._setting_float("font_scale_title", 1.0), 0.5, 2.2)
        artist_scale = _clamp(self._setting_float("font_scale_artist", 1.0), 0.5, 2.2)
        lyrics_scale = _clamp(self._setting_float("font_scale_lyrics", 1.0), 0.5, 2.2)
        hud_global_scale = _clamp(self._setting_float("font_scale_hud", 1.0), 0.5, 2.2)
        left_hud_font_scale = _clamp(self._setting_float("font_scale_left_hud", 1.0), 0.5, 2.2)
        right_hud_font_scale = _clamp(self._setting_float("font_scale_right_hud", 1.0), 0.5, 2.2)

        title_font.setPointSizeF(title_font.pointSizeF() * title_scale)
        subtitle_font.setPointSizeF(subtitle_font.pointSizeF() * artist_scale)
        lyric_active.setPointSizeF(lyric_active.pointSizeF() * lyrics_scale)
        lyric_secondary.setPointSizeF(lyric_secondary.pointSizeF() * lyrics_scale)
        lyric_context.setPointSizeF(lyric_context.pointSizeF() * lyrics_scale)
        brand_label.setPointSizeF(brand_label.pointSizeF() * hud_global_scale * left_hud_font_scale)
        brand_theme.setPointSizeF(brand_theme.pointSizeF() * hud_global_scale * left_hud_font_scale)
        hud_label.setPointSizeF(hud_label.pointSizeF() * hud_global_scale * right_hud_font_scale)
        hud_value.setPointSizeF(hud_value.pointSizeF() * hud_global_scale * right_hud_font_scale)

        return {
            "title": title_font,
            "subtitle": subtitle_font,
            "brand_label": brand_label,
            "brand_theme": brand_theme,
            "hud_label": hud_label,
            "hud_value": hud_value,
            "lyric_active": lyric_active,
            "lyric_secondary": lyric_secondary,
            "lyric_context": lyric_context,
            "debug": debug_font,
        }

    def _elide_text(self, text: str, font: QFont, max_width: float) -> str:
        metrics = QFontMetrics(font)
        return metrics.elidedText(text, Qt.TextElideMode.ElideRight, int(max(10.0, max_width)))

    def _measure_text_width(self, text: str, font: QFont) -> float:
        metrics = QFontMetrics(font)
        return max(
            float(metrics.horizontalAdvance(text)),
            float(metrics.tightBoundingRect(text).width()),
        )

    def _measure_text_height(self, text: str, font: QFont) -> float:
        metrics = QFontMetrics(font)
        sample = text if text and text.strip() else "Ag"
        return max(
            float(metrics.height()),
            float(metrics.tightBoundingRect(sample).height()),
        )

    def _font_support_ratio(self, font: QFont, text: str) -> float:
        meaningful = [ch for ch in text if not ch.isspace()]
        if not meaningful:
            return 1.0
        raw = QRawFont.fromFont(font)
        if not raw.isValid():
            metrics = QFontMetrics(font)
            supported = 0
            for ch in meaningful:
                if metrics.inFontUcs4(ord(ch)):
                    supported += 1
            return supported / len(meaningful)

        supported = 0
        for ch in meaningful:
            glyphs = raw.glyphIndexesForString(ch)
            if glyphs and glyphs[0] != 0:
                supported += 1
        return supported / len(meaningful)

    def _best_font_for_text(self, font: QFont, text: str) -> QFont:
        families = [name for name in font.families() if name] or [font.family()]
        best_font = QFont(font)
        best_ratio = self._font_support_ratio(best_font, text)
        for family in families:
            candidate = QFont(font)
            candidate.setFamily(family)
            candidate.setFamilies([family])
            ratio = self._font_support_ratio(candidate, text)
            if ratio > best_ratio:
                best_ratio = ratio
                best_font = candidate
            if ratio >= 0.999:
                return candidate
        return best_font

    def _fit_font_to_width(self, text: str, font: QFont, max_width: float, min_point_size: float) -> QFont:
        fitted = self._best_font_for_text(font, _normalize_text(text))
        while self._measure_text_width(text, fitted) > max_width and fitted.pointSizeF() > min_point_size:
            fitted.setPointSizeF(fitted.pointSizeF() - 0.5)
        return fitted

    def _fit_font_to_rect(
        self,
        text: str,
        font: QFont,
        max_width: float,
        max_height: float,
        min_point_size: float,
    ) -> QFont:
        fitted = self._best_font_for_text(font, _normalize_text(text))
        width_limit = max(8.0, float(max_width))
        height_limit = max(8.0, float(max_height))
        while fitted.pointSizeF() > min_point_size:
            too_wide = self._measure_text_width(text, fitted) > width_limit
            too_tall = self._measure_text_height(text, fitted) > height_limit
            if not (too_wide or too_tall):
                break
            fitted.setPointSizeF(fitted.pointSizeF() - 0.5)
        return fitted

    def _font_family_chain(self, preferred: str, fallbacks: list[str]) -> list[str]:
        chain: list[str] = []
        for candidate in [preferred, *fallbacks]:
            normalized = _normalize_text(candidate)
            if not normalized:
                continue
            if normalized.casefold() not in self._available_families:
                continue
            if normalized not in chain:
                chain.append(normalized)
        return chain

    def _make_font(
        self,
        preferred: str,
        fallbacks: list[str],
        point_size: float,
        weight: QFont.Weight,
        letter_spacing: float,
    ) -> QFont:
        chain = self._font_family_chain(preferred, fallbacks)
        font = QFont(chain[0] if chain else preferred)
        if chain:
            font.setFamilies(chain)
        font.setPointSizeF(point_size)
        font.setWeight(weight)
        font.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, letter_spacing)
        return font

    def _setting_float(self, key: str, default: float) -> float:
        try:
            return float(settings.get(key, default))
        except (TypeError, ValueError):
            return default

    def _module_offset(self, module: str, canvas_rect: QRectF) -> tuple[float, float]:
        dx_pct = self._setting_float(f"layout_{module}_x", 0.0)
        dy_pct = self._setting_float(f"layout_{module}_y", 0.0)
        return (
            canvas_rect.width() * dx_pct / 100.0,
            canvas_rect.height() * dy_pct / 100.0,
        )

    def _shift_rect_clamped(self, rect: QRectF, container: QRectF, dx: float, dy: float) -> QRectF:
        shifted = QRectF(rect)
        shifted.translate(dx, dy)
        if shifted.left() < container.left():
            shifted.translate(container.left() - shifted.left(), 0.0)
        if shifted.right() > container.right():
            shifted.translate(container.right() - shifted.right(), 0.0)
        if shifted.top() < container.top():
            shifted.translate(0.0, container.top() - shifted.top())
        if shifted.bottom() > container.bottom():
            shifted.translate(0.0, container.bottom() - shifted.bottom())
        return shifted

    def _draw_glow_text(
        self,
        painter: QPainter,
        text: str,
        rect: QRectF,
        align: Qt.AlignmentFlag,
        font: QFont,
        color: QColor,
        glow: QColor,
        shadow_offset: float,
    ):
        """Draw text with subtle glow/shadow."""
        painter.setFont(font)
        painter.setPen(glow)
        painter.drawText(rect.translated(0, shadow_offset), align, text)
        painter.setPen(color)
        painter.drawText(rect, align, text)

    def _draw_huds(self, painter: QPainter, width: float, height: float):
        """Draw title + immersive minimal HUD (no card panels)."""
        dna = self.scene.theme
        if not dna:
            return

        opacity = _clamp(settings.get("hud_opacity", 0.8), 0.2, 1.0)
        scale = _clamp(settings.get("hud_scale", 1.0), 0.7, 1.5)
        show_title = settings.get("show_track_title", True)
        show_left = settings.get("show_left_hud", True)
        show_right = settings.get("show_right_hud", True)
        show_lyrics = settings.get("show_lyrics", False)
        debug_mode = settings.get("show_dev_hud", False)

        metrics = self._layout_state
        if not metrics:
            metrics = self._get_layout_metrics(width, height, scale, show_title, show_left, show_right, show_lyrics)
            self._layout_state = metrics
        typography = self._get_typography(width, height)

        if show_title:
            self._draw_top_title(painter, dna, metrics["title_rect"], typography, opacity)

        if metrics.get("lyrics_visible"):
            lyrics_rect = metrics.get("lyrics_rect")
            if isinstance(lyrics_rect, QRectF) and lyrics_rect.height() > 4:
                self._draw_local_veil(painter, lyrics_rect, QColor(*dna.get_color("background_fog", 1.0)[:3]), opacity * 0.72)
                self._draw_lyrics_panel(painter, dna, lyrics_rect, typography, opacity)

        if show_left or show_right:
            self._draw_bottom_huds(
                painter=painter,
                dna=dna,
                metrics=metrics,
                typography=typography,
                opacity=opacity,
                show_left=show_left,
                show_right=show_right,
                debug_mode=debug_mode,
            )

    def _draw_top_title(
        self,
        painter: QPainter,
        dna: Theme,
        top_rect: QRectF,
        typography: Dict[str, QFont],
        opacity: float,
    ):
        """Top title with adaptive sizing / truncation and restrained glow."""
        if not self.track_title or top_rect.height() <= 2:
            return

        alpha = int(255 * opacity * self.title_alpha)
        if alpha <= 0:
            return

        title_r, title_g, title_b, _ = dna.get_color(role="title_text", alpha=1.0)
        hud_r, hud_g, hud_b, _ = dna.get_color(role="hud_text", alpha=1.0)
        fog_r, fog_g, fog_b, _ = dna.get_color(role="background_fog", alpha=1.0)
        is_vertical = self._layout_state.get("canvas_ratio_key") == "9:16"
        outer_pad_x = top_rect.width() * (0.02 if is_vertical else 0.03)
        outer_pad_y = top_rect.height() * (0.04 if is_vertical else 0.05)
        block_rect = top_rect.adjusted(outer_pad_x, outer_pad_y, -outer_pad_x, -outer_pad_y)
        if block_rect.height() <= 8:
            return

        inner_rect = block_rect.adjusted(
            block_rect.width() * 0.06,
            block_rect.height() * 0.12,
            -block_rect.width() * 0.06,
            -block_rect.height() * 0.10,
        )
        title_rect = QRectF(
            inner_rect.left(),
            inner_rect.top(),
            inner_rect.width(),
            inner_rect.height() * 0.58,
        )
        max_text_w = title_rect.width()
        title_text = _normalize_text(self.track_title)
        title_font = self._fit_font_to_rect(
            title_text,
            typography["title"],
            max_text_w,
            title_rect.height() * 0.92,
            max(12.0 if is_vertical else 13.0, typography["title"].pointSizeF() * 0.56),
        )
        title_text = self._elide_text(title_text, title_font, max_text_w)
        shadow_offset = max(block_rect.height() * 0.010, 1.0)
        self._draw_glow_text(
            painter=painter,
            text=title_text,
            rect=title_rect,
            align=Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignVCenter,
            font=title_font,
            color=QColor(title_r, title_g, title_b, alpha),
            glow=QColor(title_r, title_g, title_b, int(alpha * 0.36)),
            shadow_offset=shadow_offset,
        )

        if self.track_artist:
            artist_text = _normalize_text(self.track_artist)
            artist_rect = QRectF(
                inner_rect.left(),
                inner_rect.top() + inner_rect.height() * 0.62,
                inner_rect.width(),
                inner_rect.height() * 0.30,
            )
            artist_font = self._fit_font_to_width(
                artist_text,
                typography["subtitle"],
                artist_rect.width(),
                max(9.0 if is_vertical else 9.5, typography["subtitle"].pointSizeF() * 0.70),
            )
            artist_font = self._fit_font_to_rect(
                artist_text,
                artist_font,
                artist_rect.width(),
                artist_rect.height() * 0.92,
                max(8.0 if is_vertical else 8.5, typography["subtitle"].pointSizeF() * 0.56),
            )
            artist_text = self._elide_text(artist_text, artist_font, artist_rect.width())
            canvas_rect = self._layout_state.get("canvas_rect")
            if isinstance(canvas_rect, QRectF):
                artist_dx, artist_dy = self._module_offset("artist", canvas_rect)
                artist_rect = self._shift_rect_clamped(artist_rect, canvas_rect, artist_dx, artist_dy)
            self._draw_glow_text(
                painter=painter,
                text=artist_text,
                rect=artist_rect,
                align=Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignVCenter,
                font=artist_font,
                color=QColor(hud_r, hud_g, hud_b, int(alpha * 0.92)),
                glow=QColor(title_r, title_g, title_b, int(alpha * 0.20)),
                shadow_offset=shadow_offset * 0.7,
            )

    def _draw_lyrics_panel(
        self,
        painter: QPainter,
        dna: Theme,
        rect: QRectF,
        typography: Dict[str, QFont],
        opacity: float,
    ):
        """Stable lyric block with explicit hierarchy and left-aligned reading flow."""
        lyrics = self.track_lyrics
        if not lyrics or not lyrics.cues:
            return

        alpha = int(255 * opacity * self.lyrics_alpha)
        if alpha <= 0:
            return

        title_r, title_g, title_b, _ = dna.get_color(role="title_text", alpha=1.0)
        hud_r, hud_g, hud_b, _ = dna.get_color(role="hud_text", alpha=1.0)
        acc_r, acc_g, acc_b, _ = dna.get_color(role="accent", alpha=1.0)
        is_vertical = self._layout_state.get("canvas_ratio_key") == "9:16"
        panel_rect = rect.adjusted(0, 0, 0, 0)
        if panel_rect.height() <= 10:
            return

        active_index = lyrics.active_index_at(self.playback_position)
        anchor_index = max(0, active_index)

        painter.save()
        painter.setClipRect(panel_rect.adjusted(-2, -2, 2, 2))

        # Centered active block
        content_rect = panel_rect.adjusted(
            panel_rect.width() * 0.04,
            panel_rect.height() * 0.12,
            -panel_rect.width() * 0.04,
            -panel_rect.height() * 0.12,
        )
        active_rect = content_rect
        active_corner = max(active_rect.height() * 0.12, 6.0)

        # Vertical indicator bar
        bar_rect = QRectF(
            active_rect.left() + active_rect.width() * 0.008,
            active_rect.top() + active_rect.height() * 0.20,
            max(active_rect.width() * 0.012, 3.5),
            active_rect.height() * 0.60,
        )
        painter.setBrush(QColor(title_r, title_g, title_b, int(alpha * 0.88)))
        painter.drawRoundedRect(bar_rect, bar_rect.width() * 0.5, bar_rect.width() * 0.5)

        cue = lyrics.cues[anchor_index]
        lines = tuple(_normalize_text(line) for line in cue.lines if _normalize_text(line))[:2]
        if not lines:
            lines = ("",)

        primary_font = QFont(typography["lyric_active"])
        secondary_font = QFont(typography["lyric_secondary"])
        text_left = active_rect.left() + active_rect.width() * 0.06
        text_width = active_rect.width() * 0.90

        # Proportional layout for 1 or 2 lines
        if len(lines) > 1:
            primary_rect = QRectF(
                text_left,
                active_rect.top() + active_rect.height() * 0.15,
                text_width,
                active_rect.height() * 0.40,
            )
            secondary_rect = QRectF(
                text_left,
                active_rect.top() + active_rect.height() * 0.55,
                text_width,
                active_rect.height() * 0.35,
            )
        else:
            primary_rect = QRectF(
                text_left,
                active_rect.top(),
                text_width,
                active_rect.height(),
            )
            secondary_rect = QRectF()

        # Render Core Lyric
        primary_font = self._fit_font_to_rect(lines[0], primary_font, primary_rect.width(), primary_rect.height() * 0.95, 11.0)
        primary_text = self._elide_text(lines[0], primary_font, primary_rect.width())
        self._draw_glow_text(
            painter=painter,
            text=primary_text,
            rect=primary_rect,
            align=Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
            font=primary_font,
            color=QColor(title_r, title_g, title_b, alpha),
            glow=QColor(acc_r, acc_g, acc_b, int(alpha * 0.16)),
            shadow_offset=max(active_rect.height() * 0.010, 0.45),
        )

        # Render Translation
        if len(lines) > 1:
            secondary_font = self._fit_font_to_rect(lines[1], secondary_font, secondary_rect.width(), secondary_rect.height() * 0.95, 9.5)
            secondary_text = self._elide_text(lines[1], secondary_font, secondary_rect.width())
            self._draw_glow_text(
                painter=painter,
                text=secondary_text,
                rect=secondary_rect,
                align=Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                font=secondary_font,
                color=QColor(hud_r, hud_g, hud_b, int(alpha * 0.85)),
                glow=QColor(title_r, title_g, title_b, int(alpha * 0.08)),
                shadow_offset=max(active_rect.height() * 0.008, 0.35),
            )

        painter.restore()

    def _draw_bottom_huds(
        self,
        painter: QPainter,
        dna: Theme,
        metrics: Dict[str, object],
        typography: Dict[str, QFont],
        opacity: float,
        show_left: bool,
        show_right: bool,
        debug_mode: bool,
    ):
        """Draw bottom-left brand and bottom-right monitor without panel containers."""
        fog_r, fog_g, fog_b, _ = dna.get_color(role="background_fog", alpha=1.0)
        fog_color = QColor(fog_r, fog_g, fog_b)

        if show_left:
            left_rect = metrics["left_brand_rect"]
            self._draw_local_veil(painter, left_rect, fog_color, opacity * 0.85)
            self._draw_left_hud(painter, dna, left_rect, typography, opacity, debug_mode)
        if show_right:
            right_rect = metrics["right_monitor_rect"]
            self._draw_local_veil(painter, right_rect, fog_color, opacity * 0.78)
            self._draw_right_hud(painter, dna, right_rect, typography, opacity, debug_mode)

    def _draw_local_veil(
        self,
        painter: QPainter,
        rect: QRectF,
        fog_color: QColor,
        opacity: float,
    ):
        """No-op to eliminate card tile seam artifacts, keeping text floating seamlessly."""
        pass

    def _format_family_name(self, family: str) -> str:
        return family.replace("_", " ").upper()

    def _draw_left_hud(
        self,
        painter: QPainter,
        dna: Theme,
        rect: QRectF,
        typography: Dict[str, QFont],
        opacity: float,
        debug_mode: bool,
    ):
        """Left zone: production brand label; debug details only in debug mode."""
        frame = self.scene.current_frame
        hud_r, hud_g, hud_b, _ = dna.get_color(role="hud_text", alpha=1.0)
        title_r, title_g, title_b, _ = dna.get_color(role="title_text", alpha=1.0)
        acc_r, acc_g, acc_b, _ = dna.get_color(role="accent", alpha=1.0)
        is_vertical = self._layout_state.get("canvas_ratio_key") == "9:16"
        inner = rect.adjusted(
            rect.width() * 0.05,
            rect.height() * 0.12,
            -rect.width() * 0.05,
            -rect.height() * 0.12,
        )
        line_y = inner.top() + inner.height() * 0.12
        painter.setPen(_make_round_pen(QColor(hud_r, hud_g, hud_b, int(150 * opacity)), max(rect.height() * 0.010, 1.0)))
        painter.drawLine(
            QPointF(inner.left(), line_y),
            QPointF(inner.left() + inner.width() * 0.20, line_y),
        )
        painter.setBrush(QColor(acc_r, acc_g, acc_b, int(200 * opacity)))
        painter.setPen(Qt.PenStyle.NoPen)
        dot_r = max(rect.height() * 0.012, 1.3)
        painter.drawEllipse(QPointF(inner.left(), line_y), dot_r, dot_r)

        text_left = inner.left()
        brand_label_font = QFont(typography["brand_label"])
        brand_theme_font = QFont(typography["brand_theme"])
        if is_vertical:
            brand_label_font.setPointSizeF(max(brand_label_font.pointSizeF() * 0.92, 8.5))
            brand_theme_font.setPointSizeF(max(brand_theme_font.pointSizeF() * 0.94, 9.0))
        label_rect = QRectF(text_left, inner.top() + inner.height() * 0.24, inner.width(), inner.height() * 0.30)
        theme_rect = QRectF(text_left, inner.top() + inner.height() * 0.58, inner.width(), inner.height() * 0.34)
        brand_label_font = self._fit_font_to_rect(
            "AUDIO KINETIC ENGINE",
            brand_label_font,
            label_rect.width(),
            label_rect.height() * 0.92,
            8.0,
        )
        brand_theme_font = self._fit_font_to_rect(
            self._format_family_name(dna.palette_family),
            brand_theme_font,
            theme_rect.width(),
            theme_rect.height() * 0.92,
            8.5,
        )

        painter.setFont(brand_label_font)
        painter.setPen(QColor(title_r, title_g, title_b, int(220 * opacity)))
        brand_label_text = self._elide_text("AUDIO KINETIC ENGINE", brand_label_font, label_rect.width())
        painter.drawText(
            label_rect,
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
            brand_label_text,
        )

        painter.setFont(brand_theme_font)
        painter.setPen(QColor(hud_r, hud_g, hud_b, int(232 * opacity)))
        palette_text = self._elide_text(self._format_family_name(dna.palette_family), brand_theme_font, theme_rect.width())
        painter.drawText(
            theme_rect,
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
            palette_text,
        )

        if debug_mode:
            painter.setFont(typography["debug"])
            debug_lines = [
                f"STRUCT {dna.structure_type.upper()} / {dna.detail_style.upper()}",
                f"MOTION {dna.motion_profile.upper()}",
            ]
            if frame:
                debug_lines.append(f"RMS {frame.rms:0.2f}  BASS {frame.bass:0.2f}  BEAT {frame.beat_strength:0.2f}")
            if settings.get("show_fps", True):
                target_label = "UNLIM" if self.target_fps == 0 else str(self.target_fps)
                debug_lines.append(f"FPS {self._actual_fps:0.0f} / TARGET {target_label}")

            painter.setPen(QColor(hud_r, hud_g, hud_b, int(188 * opacity)))
            y = rect.bottom() + rect.height() * 0.04
            step = rect.height() * 0.20
            for line in debug_lines:
                painter.drawText(
                    QRectF(text_left, y, rect.width() * 1.35, step),
                    Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                    line,
                )
                y += step

    def _draw_right_hud(
        self,
        painter: QPainter,
        dna: Theme,
        rect: QRectF,
        typography: Dict[str, QFont],
        opacity: float,
        debug_mode: bool,
    ):
        """Right zone: Three unified breathing monitor bars."""
        frame = self.scene.current_frame
        if not frame:
            return

        # 1. Update Smoothing for slow fall-off
        targets = {
            "BASS": _clamp(frame.bass, 0.0, 1.0),
            "RMS": _clamp(frame.rms * 1.95, 0.0, 1.0),
            "BEAT": _clamp(max(frame.beat_strength, self.scene.effects.beat_flash * 0.8), 0.0, 1.0)
        }
        
        for k, target in targets.items():
            if target > self._hud_smooth[k]:
                # Instant rise for responsiveness
                self._hud_smooth[k] = target
            else:
                # Slow fall-off (回落速度较慢)
                self._hud_smooth[k] += (target - self._hud_smooth[k]) * 0.06

        # 2. Layout Setup
        r, g, b, _ = dna.get_color(role="hud_text", alpha=1.0)
        accent_r, accent_g, accent_b, _ = dna.get_color(role="accent", alpha=1.0)
        hud_color = QColor(r, g, b)
        accent_color = QColor(accent_r, accent_g, accent_b)
        is_vertical = self._layout_state.get("canvas_ratio_key") == "9:16"

        gap = rect.height() * 0.12
        row_h = (rect.height() - gap * 2) / 3.0
        label_w = rect.width() * (0.34 if is_vertical else 0.28)
        lane_x = rect.left() + label_w + rect.width() * (0.035 if is_vertical else 0.04)
        lane_w = rect.width() - label_w - rect.width() * (0.05 if is_vertical else 0.06)

        rows = [QRectF(rect.left(), rect.top() + (row_h + gap) * i, rect.width(), row_h) for i in range(3)]
        labels = ("BASS", "RMS", "BEAT")

        # 3. Render each row
        hud_label_font = QFont(typography["hud_label"])
        if is_vertical:
            hud_label_font.setPointSizeF(max(hud_label_font.pointSizeF() * 0.80, 7.5))
        painter.setFont(hud_label_font)
        for idx, row in enumerate(rows):
            label = labels[idx]
            # Label with slight staggered opacity
            painter.setPen(QColor(r, g, b, int((200 - idx * 10) * opacity)))
            hud_label_font = self._fit_font_to_rect(
                label,
                hud_label_font,
                label_w,
                row.height() * 0.90,
                7.0,
            )
            painter.setFont(hud_label_font)
            label_text = self._elide_text(label, hud_label_font, label_w)
            painter.drawText(
                QRectF(row.left(), row.top(), label_w, row.height()),
                Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                label_text,
            )

            # Unified Breathing Bar (三者最大长度相等: lane_w)
            lane = QRectF(lane_x, row.top() + row_h * 0.22, lane_w, row_h * 0.56)
            self._draw_breathing_bar(
                painter,
                lane,
                self._hud_smooth[label],
                opacity,
                hud_color,
                accent_color
            )

        if debug_mode:
            painter.setFont(typography["hud_value"])
            painter.setPen(QColor(r, g, b, int(170 * opacity)))
            painter.drawText(
                QRectF(rect.right() - rect.width() * 0.32, rect.bottom() + rect.height() * 0.02, rect.width() * 0.32, rect.height() * 0.20),
                Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
                f"{frame.bass:0.2f}/{frame.rms:0.2f}/{frame.beat_strength:0.2f}",
            )

    def _draw_breathing_bar(
        self,
        painter: QPainter,
        lane: QRectF,
        value: float,
        opacity: float,
        base_color: QColor,
        accent_color: QColor,
    ):
        """Unified breathing bar with gradient and hazy glow (蒙眬的感觉)."""
        v = max(0.0, value)
        center_y = lane.center().y()
        bar_h = lane.height() * 0.35
        max_w = lane.width()
        active_w = max_w * v
        
        # 1. Background Track (faint aesthetic guide)
        painter.setPen(QPen(QColor(base_color.red(), base_color.green(), base_color.blue(), int(30 * opacity)), 1.2))
        painter.drawLine(QPointF(lane.left(), center_y), QPointF(lane.right(), center_y))

        if v < 0.005:
            return

        # 2. Hazy Glow (蒙眬的感觉)
        # Multiple layered soft rectangles for a hazy light-leak effect
        for i in range(3):
            glow_opacity = int((35 - i * 10) * opacity)
            if glow_opacity <= 0: continue
            
            blur = 1.5 + i * 2.0
            glow_rect = QRectF(lane.left() - blur, center_y - (bar_h/2 + blur), active_w + blur*2, bar_h + blur*2)
            
            glow_grad = QLinearGradient(glow_rect.left(), 0, glow_rect.right(), 0)
            glow_grad.setColorAt(0.0, QColor(base_color.red(), base_color.green(), base_color.blue(), glow_opacity))
            glow_grad.setColorAt(1.0, QColor(accent_color.red(), accent_color.green(), accent_color.blue(), int(glow_opacity * 1.3)))
            
            painter.setBrush(glow_grad)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawRoundedRect(glow_rect, glow_rect.height()/2, glow_rect.height()/2)

        # 3. Main Gradient Bar (呼吸条初段和最末端颜色不同)
        bar_rect = QRectF(lane.left(), center_y - bar_h/2, active_w, bar_h)
        main_grad = QLinearGradient(bar_rect.left(), 0, bar_rect.right(), 0)
        main_grad.setColorAt(0.0, QColor(base_color.red(), base_color.green(), base_color.blue(), int(200 * opacity)))
        main_grad.setColorAt(1.0, QColor(accent_color.red(), accent_color.green(), accent_color.blue(), int(240 * opacity)))
        
        painter.setBrush(main_grad)
        painter.drawRoundedRect(bar_rect, bar_h/2, bar_h/2)

        # 4. Leading Glow Tip (vibrant breathing point)
        if active_w > 2:
            tip_r = bar_h * 1.0
            head_glow = QRadialGradient(QPointF(bar_rect.right(), center_y), tip_r)
            head_glow.setColorAt(0.0, QColor(255, 255, 255, int(140 * opacity)))
            head_glow.setColorAt(0.4, QColor(accent_color.red(), accent_color.green(), accent_color.blue(), int(100 * opacity)))
            head_glow.setColorAt(1.0, QColor(accent_color.red(), accent_color.green(), accent_color.blue(), 0))
            
            painter.setBrush(head_glow)
            painter.drawEllipse(QPointF(bar_rect.right(), center_y), tip_r, tip_r)
