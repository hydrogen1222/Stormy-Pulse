"""
Renderer - draws the visualization using QPainter.
"""
import math
import random
import time
from typing import Dict, Optional

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import (
    QBrush,
    QColor,
    QFont,
    QFontMetrics,
    QImage,
    QLinearGradient,
    QPainter,
    QPainterPath,
    QPen,
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
        self._hud_smooth = {"BASS": 0.0, "RMS": 0.0, "BEAT": 0.0}
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

    def set_track_info(self, title: str, artist: str):
        self.track_title = title if title else "Unknown Track"
        self.track_artist = artist if artist else "Unknown Artist"
        self.title_alpha = 0.0

    def set_lyrics(self, lyrics: Optional[TrackLyrics]):
        self.track_lyrics = lyrics
        self.playback_position = 0.0
        self.lyrics_alpha = 0.0

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

    def reset(self):
        self.scene.reset()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setRenderHint(QPainter.RenderHint.TextAntialiasing)
        self._paint_count += 1
        self._update_fps_counter()
        self._render_scene(painter, float(self.width()), float(self.height()), 0.016)

    def render_to_image(self, width: int, height: int, frame_dt: float = 0.016) -> QImage:
        """Render the current scene into an offscreen image at arbitrary resolution."""
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
        self._layout_state = self._build_layout_metrics(
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
            self._draw_generative_structure(painter, cx, cy, width, height)
            self._draw_energy_core_layer(painter, cx, cy, width, height)
            if self.scene.theme.show_particles:
                self._draw_particles_layer(painter, width, height)
            self._draw_burst_effects_layer(painter, cx, cy, width, height)
        self._draw_huds(painter, width, height)

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
        """Build layout from a strict virtual 16:9 canvas."""
        outer_pad = min(width, height) * 0.014
        avail_w = max(10.0, width - outer_pad * 2)
        avail_h = max(10.0, height - outer_pad * 2)
        canvas_ratio = 16.0 / 9.0
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

        hud_edge_x = width * 0.018
        hud_edge_y = height * 0.026

        brand_w = _clamp(canvas_rect.width() * (0.22 + (scale - 1.0) * 0.04), unit * 0.28, canvas_rect.width() * 0.28)
        brand_h = _clamp(canvas_rect.height() * (0.10 + (scale - 1.0) * 0.025), 48.0, 118.0)
        left_brand_rect = QRectF(
            hud_edge_x,
            height - hud_edge_y - brand_h,
            brand_w,
            brand_h,
        )

        lyrics_visible = bool(show_lyrics and self.track_lyrics and self.track_lyrics.cues)
        right_column_w = _clamp(
            canvas_rect.width() * (0.28 + (scale - 1.0) * 0.03),
            220.0,
            canvas_rect.width() * 0.34,
        ) if lyrics_visible else 0.0
        right_column_right = canvas_rect.right() - inset_x * 0.22
        right_column_left = right_column_right - right_column_w
        lyrics_gap = canvas_rect.width() * 0.040 if lyrics_visible else 0.0

        left_limit = left_brand_rect.right() + canvas_rect.width() * 0.060 if show_left else canvas_rect.left() + inset_x
        right_limit = right_column_left - lyrics_gap if lyrics_visible else (
            canvas_rect.right() - inset_x if not show_right else width - hud_edge_x
        )
        min_scene_w = canvas_rect.width() * (0.26 if lyrics_visible else 0.24)
        if right_limit <= left_limit + min_scene_w:
            right_limit = left_limit + min_scene_w

        scene_center_x = (left_limit + right_limit) * 0.5
        title_h = _clamp(canvas_rect.height() * (0.17 + (scale - 1.0) * 0.03), 58.0, 156.0) if show_title else 0.0
        title_w = min(
            max(right_limit - left_limit, canvas_rect.width() * 0.30) * 0.88,
            canvas_rect.width() * (0.34 if lyrics_visible else 0.44),
        ) if show_title else 0.0
        title_rect = QRectF(
            scene_center_x - title_w * 0.5,
            canvas_rect.top() + canvas_rect.height() * 0.028,
            title_w,
            title_h,
        )

        if lyrics_visible:
            monitor_w = _clamp(right_column_w * 0.98, 188.0, right_column_w)
            monitor_h = _clamp(canvas_rect.height() * (0.17 + (scale - 1.0) * 0.035), 126.0, canvas_rect.height() * 0.22)
            right_monitor_rect = QRectF(
                right_column_right - monitor_w,
                height - hud_edge_y - monitor_h,
                monitor_w,
                monitor_h,
            )
        else:
            monitor_w = _clamp(canvas_rect.width() * (0.19 + (scale - 1.0) * 0.05), 184.0, canvas_rect.width() * 0.24)
            monitor_h = _clamp(canvas_rect.height() * (0.205 + (scale - 1.0) * 0.04), 136.0, canvas_rect.height() * 0.28)
            right_monitor_rect = QRectF(
                width - hud_edge_x - monitor_w,
                height - hud_edge_y - monitor_h,
                monitor_w,
                monitor_h,
            )

        if show_title and not lyrics_visible:
            title_right_limit = right_monitor_rect.left() - canvas_rect.width() * 0.060 if show_right else canvas_rect.right() - inset_x
            title_center_x = (left_limit + title_right_limit) * 0.5
            title_w = min(
                max(title_right_limit - left_limit, canvas_rect.width() * 0.30) * 0.88,
                canvas_rect.width() * 0.44,
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
            lyrics_rect = QRectF(
                right_column_left,
                lyrics_top,
                right_column_w,
                lyrics_bottom - lyrics_top,
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
        safe_radius = max(min(fit_w, fit_h) * 0.46, unit * 0.17)

        return {
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
        """Unified typography system across title / brand / HUD."""
        base = min(width, height)
        title_family = settings.get("title_font_family", "") or "Segoe UI Semibold"
        artist_family = settings.get("artist_font_family", "") or "Segoe UI"
        legacy_lyric_family = settings.get("lyric_font_family", "")
        lyric_original_family = settings.get("lyric_original_font_family", "") or legacy_lyric_family or "Microsoft YaHei UI"
        lyric_translation_family = settings.get("lyric_translation_font_family", "") or legacy_lyric_family or "Microsoft YaHei UI"

        title_font = QFont(title_family)
        title_font.setPointSizeF(_clamp(base * 0.043, 18.0, 56.0))
        title_font.setWeight(QFont.Weight.DemiBold)
        title_font.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, _clamp(base * 0.0032, 0.8, 4.8))

        artist_font = QFont(artist_family)
        artist_font.setPointSizeF(_clamp(base * 0.020, 10.0, 25.0))
        artist_font.setWeight(QFont.Weight.Light)
        artist_font.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, _clamp(base * 0.0024, 0.6, 3.0))

        brand_label = QFont("Bahnschrift SemiCondensed")
        brand_label.setPointSizeF(_clamp(base * 0.0175, 9.0, 18.0))
        brand_label.setWeight(QFont.Weight.DemiBold)
        brand_label.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, _clamp(base * 0.0025, 0.8, 3.8))

        brand_theme = QFont("Bahnschrift")
        brand_theme.setPointSizeF(_clamp(base * 0.021, 10.0, 22.0))
        brand_theme.setWeight(QFont.Weight.Bold)
        brand_theme.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, _clamp(base * 0.0034, 1.0, 4.5))

        hud_label = QFont("Bahnschrift")
        hud_label.setPointSizeF(_clamp(base * 0.017, 8.5, 17.0))
        hud_label.setWeight(QFont.Weight.DemiBold)
        hud_label.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, _clamp(base * 0.0022, 0.5, 3.4))

        hud_value = QFont("Consolas")
        hud_value.setPointSizeF(_clamp(base * 0.0135, 7.5, 14.5))
        hud_value.setWeight(QFont.Weight.Normal)
        hud_value.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, _clamp(base * 0.0018, 0.3, 2.0))

        lyric_active = QFont(lyric_original_family)
        lyric_active.setPointSizeF(_clamp(base * 0.026, 15.0, 30.0))
        lyric_active.setWeight(QFont.Weight.DemiBold)

        lyric_secondary = QFont(lyric_translation_family)
        lyric_secondary.setPointSizeF(_clamp(base * 0.018, 10.0, 21.0))
        lyric_secondary.setWeight(QFont.Weight.Normal)

        lyric_context = QFont(lyric_original_family)
        lyric_context.setPointSizeF(_clamp(base * 0.020, 11.0, 23.0))
        lyric_context.setWeight(QFont.Weight.Normal)

        debug_font = QFont("Consolas")
        debug_font.setPointSizeF(_clamp(base * 0.0125, 7.0, 13.5))
        debug_font.setWeight(QFont.Weight.Normal)
        debug_font.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, _clamp(base * 0.0015, 0.2, 1.8))

        return {
            "title": title_font,
            "artist": artist_font,
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
            metrics = self._build_layout_metrics(width, height, scale, show_title, show_left, show_right, show_lyrics)
            self._layout_state = metrics
        typography = self._build_typography(width, height)

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

        max_text_w = top_rect.width() * 0.90
        title_font = QFont(typography["title"])
        min_title_size = max(12.0, title_font.pointSizeF() * 0.58)
        while QFontMetrics(title_font).horizontalAdvance(self.track_title) > max_text_w and title_font.pointSizeF() > min_title_size:
            title_font.setPointSizeF(title_font.pointSizeF() - 1.0)

        title_text = self._elide_text(self.track_title, title_font, max_text_w)
        shadow_offset = max(top_rect.height() * 0.016, 1.0)
        title_rect = QRectF(
            top_rect.left(),
            top_rect.top(),
            top_rect.width(),
            top_rect.height() * 0.46,
        )
        self._draw_glow_text(
            painter=painter,
            text=title_text,
            rect=title_rect,
            align=Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignBottom,
            font=title_font,
            color=QColor(title_r, title_g, title_b, alpha),
            glow=QColor(title_r, title_g, title_b, int(alpha * 0.42)),
            shadow_offset=shadow_offset,
        )

        if self.track_artist:
            artist_font = QFont(typography["artist"])
            max_artist_w = top_rect.width() * 0.84
            min_artist_size = max(8.0, artist_font.pointSizeF() * 0.62)
            while QFontMetrics(artist_font).horizontalAdvance(self.track_artist) > max_artist_w and artist_font.pointSizeF() > min_artist_size:
                artist_font.setPointSizeF(artist_font.pointSizeF() - 1.0)
            artist_text = self._elide_text(self.track_artist, artist_font, max_artist_w)

            artist_rect = QRectF(
                top_rect.left(),
                top_rect.top() + top_rect.height() * 0.62,
                top_rect.width(),
                top_rect.height() * 0.22,
            )
            self._draw_glow_text(
                painter=painter,
                text=artist_text,
                rect=artist_rect,
                align=Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignVCenter,
                font=artist_font,
                color=QColor(title_r, title_g, title_b, int(alpha * 0.78)),
                glow=QColor(255, 255, 255, int(alpha * 0.14)),
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
        """Right-side synchronized lyrics with grouped bilingual cues."""
        lyrics = self.track_lyrics
        if not lyrics or not lyrics.cues:
            return

        alpha = int(255 * opacity * self.lyrics_alpha)
        if alpha <= 0:
            return

        title_r, title_g, title_b, _ = dna.get_color(role="title_text", alpha=1.0)
        hud_r, hud_g, hud_b, _ = dna.get_color(role="hud_text", alpha=1.0)
        acc_r, acc_g, acc_b, _ = dna.get_color(role="accent", alpha=1.0)
        content_rect = QRectF(
            rect.left(),
            rect.top() + rect.height() * 0.06,
            rect.width(),
            rect.height() * 0.86,
        )
        if content_rect.height() <= 10:
            return

        active_index = lyrics.active_index_at(self.playback_position)
        anchor_index = max(0, active_index)
        active_bar_x = rect.left() - rect.width() * 0.035
        prev_index = anchor_index - 1 if anchor_index > 0 else -1
        next_index = anchor_index + 1 if anchor_index + 1 < len(lyrics.cues) else -1

        active_rect = QRectF(
            content_rect.left(),
            content_rect.top() + content_rect.height() * 0.29,
            content_rect.width(),
            content_rect.height() * 0.30,
        )
        context_h = content_rect.height() * 0.11
        prev_rect = QRectF(
            content_rect.left(),
            content_rect.top() + content_rect.height() * 0.02,
            content_rect.width(),
            context_h,
        )
        next_rect = QRectF(
            content_rect.left(),
            active_rect.bottom() + content_rect.height() * 0.16,
            content_rect.width(),
            context_h,
        )

        painter.save()
        painter.setClipRect(rect.adjusted(-2, -2, 2, 2))

        def draw_context(cue_index: int, block_rect: QRectF, alpha_scale: float):
            if cue_index < 0 or cue_index >= len(lyrics.cues):
                return
            lines = lyrics.cues[cue_index].lines[:1]
            if not lines:
                return
            font = QFont(typography["lyric_context"])
            font.setPointSizeF(max(font.pointSizeF() * 0.88, 10.0))
            line_rect = QRectF(
                block_rect.left() + rect.width() * 0.036,
                block_rect.top(),
                block_rect.width() * 0.90,
                block_rect.height() * 0.72,
            )
            text = self._elide_text(lines[0], font, line_rect.width())
            self._draw_glow_text(
                painter=painter,
                text=text,
                rect=line_rect,
                align=Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                font=font,
                color=QColor(hud_r, hud_g, hud_b, int(alpha * alpha_scale)),
                glow=QColor(acc_r, acc_g, acc_b, int(alpha * alpha_scale * 0.08)),
                shadow_offset=max(block_rect.height() * 0.02, 1.0),
            )

        if prev_index >= 0:
            draw_context(prev_index, prev_rect, 0.36)

        cue = lyrics.cues[anchor_index]
        lines = cue.lines[:2]
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(acc_r, acc_g, acc_b, int(alpha * 0.82)))
        painter.drawRoundedRect(
            QRectF(active_bar_x, active_rect.top(), rect.width() * 0.012, active_rect.height()),
            rect.width() * 0.006,
            rect.width() * 0.006,
        )

        primary_font = QFont(typography["lyric_active"])
        primary_font.setPointSizeF(primary_font.pointSizeF() * 1.02)
        secondary_font = QFont(typography["lyric_secondary"])
        secondary_font.setPointSizeF(max(secondary_font.pointSizeF() * 0.88, 10.0))
        text_left = active_rect.left() + rect.width() * 0.036
        text_width = active_rect.width() * 0.90
        primary_rect = QRectF(
            text_left,
            active_rect.top() + active_rect.height() * 0.09,
            text_width,
            active_rect.height() * 0.34,
        )
        secondary_rect = QRectF(
            text_left,
            active_rect.top() + active_rect.height() * 0.61,
            text_width,
            active_rect.height() * 0.16,
        )

        primary_text = self._elide_text(lines[0], primary_font, primary_rect.width())
        self._draw_glow_text(
            painter=painter,
            text=primary_text,
            rect=primary_rect,
            align=Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
            font=primary_font,
            color=QColor(title_r, title_g, title_b, alpha),
            glow=QColor(acc_r, acc_g, acc_b, int(alpha * 0.34)),
            shadow_offset=max(active_rect.height() * 0.025, 1.0),
        )
        if len(lines) > 1:
            secondary_text = self._elide_text(lines[1], secondary_font, secondary_rect.width())
            self._draw_glow_text(
                painter=painter,
                text=secondary_text,
                rect=secondary_rect,
                align=Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                font=secondary_font,
                color=QColor(hud_r, hud_g, hud_b, int(alpha * 0.62)),
                glow=QColor(255, 255, 255, int(alpha * 0.08)),
                shadow_offset=max(active_rect.height() * 0.02, 1.0),
            )

        if next_index >= 0:
            draw_context(next_index, next_rect, 0.34)
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

        line_y = rect.top() + rect.height() * 0.22
        painter.setPen(QPen(QColor(hud_r, hud_g, hud_b, int(130 * opacity)), max(rect.height() * 0.012, 1.0)))
        painter.drawLine(
            QPointF(rect.left() + rect.width() * 0.01, line_y),
            QPointF(rect.left() + rect.width() * 0.20, line_y),
        )
        painter.setBrush(QColor(acc_r, acc_g, acc_b, int(205 * opacity)))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawEllipse(QPointF(rect.left() + rect.width() * 0.01, line_y), rect.height() * 0.018, rect.height() * 0.018)

        text_left = rect.left() + rect.width() * 0.03
        painter.setFont(typography["brand_label"])
        painter.setPen(QColor(title_r, title_g, title_b, int(220 * opacity)))
        painter.drawText(
            QRectF(text_left, rect.top() + rect.height() * 0.28, rect.width() * 0.95, rect.height() * 0.26),
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
            "AUDIO KINETIC ENGINE",
        )

        painter.setFont(typography["brand_theme"])
        painter.setPen(QColor(hud_r, hud_g, hud_b, int(232 * opacity)))
        painter.drawText(
            QRectF(text_left, rect.top() + rect.height() * 0.55, rect.width() * 0.95, rect.height() * 0.34),
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
            self._format_family_name(dna.palette_family),
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
            y = rect.bottom() + rect.height() * 0.06
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

        gap = rect.height() * 0.12
        row_h = (rect.height() - gap * 2) / 3.0
        label_w = rect.width() * 0.28
        lane_x = rect.left() + label_w + rect.width() * 0.04
        lane_w = rect.width() - label_w - rect.width() * 0.06

        rows = [QRectF(rect.left(), rect.top() + (row_h + gap) * i, rect.width(), row_h) for i in range(3)]
        labels = ("BASS", "RMS", "BEAT")

        # 3. Render each row
        painter.setFont(typography["hud_label"])
        for idx, row in enumerate(rows):
            label = labels[idx]
            # Label with slight staggered opacity
            painter.setPen(QColor(r, g, b, int((200 - idx * 10) * opacity)))
            painter.drawText(
                QRectF(row.left(), row.top(), label_w, row.height()),
                Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                label,
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
