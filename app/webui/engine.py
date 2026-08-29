"""
Headless visualizer session engine for WebUI.
Manages audio analysis, offscreen frame rendering, clip preview generation, and full export.

Visual themes are generated per track from analyzed features (Visual DNA). The WebUI
exposes honest override knobs on top of that DNA (structure archetype, palette family,
hue shift, energy/chaos/brightness) instead of fake preset names.
"""
from __future__ import annotations

import hashlib
import math
import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

# Headless-first: force the Qt offscreen platform on Linux unless the operator
# explicitly chose one (SSH X11 forwarding may set an unreachable DISPLAY).
if sys.platform.startswith("linux"):
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PIL import Image

from app.config.settings import settings
from app.core.lyrics import parse_lrc_file
from app.core.music_library import Track
from app.analysis.cache import FeatureCacheManager
from app.analysis.features import FeatureCache, GlobalFeatureSet
from app.dynamics.context import build_dynamics_bundle
from app.visual.renderer import VisualizerRenderer
from app.visual.themes import SCIENTIFIC_FAMILY_ORDER, apply_dna_overrides
from app.export.video_exporter import VideoExporter, VideoExportOptions

STRUCTURE_CHOICES: List[str] = ["auto", "pulse", "vortex", "reactor", "organic"]
PALETTE_FAMILIES: List[str] = ["auto"] + list(SCIENTIFIC_FAMILY_ORDER)

AVAILABLE_THEMES: List[str] = PALETTE_FAMILIES  # backward-compat alias

# Rendering settings the browser can tweak; applied as non-persistent overrides.
_UI_SETTINGS_KEYS = frozenset({
    "visual_canvas_ratio",
    "show_track_title", "show_track_artist", "show_lyrics",
    "show_left_hud", "show_right_hud", "show_fps",
    "hud_scale", "hud_opacity",
    "font_scale_title", "font_scale_artist", "font_scale_lyrics", "font_scale_hud",
    "module_scale_title", "module_scale_artist", "module_scale_lyrics",
    "module_scale_effect",
    "layout_title_x", "layout_title_y",
    "layout_artist_x", "layout_artist_y",
    "layout_lyrics_x", "layout_lyrics_y",
    "custom_track_title", "custom_track_artist",
})


def _filter_ui_settings(custom_settings: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    if not custom_settings:
        return {}
    return {k: v for k, v in custom_settings.items() if k in _UI_SETTINGS_KEYS and v is not None}


def _md5_file(path: Path, chunk_size: int = 1 << 20) -> str:
    digest = hashlib.md5()
    with open(path, "rb") as f:
        while True:
            chunk = f.read(chunk_size)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()


def ensure_qt_application():
    """Ensure a global Qt application exists for offscreen font/image operations."""
    from PySide6.QtWidgets import QApplication

    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


class WebUISession:
    """Session state manager for a WebUI user."""

    def __init__(self):
        self.app = ensure_qt_application()
        self.cache_manager = FeatureCacheManager()
        self.track: Optional[Track] = None
        self.feature_cache: Optional[FeatureCache] = None
        self.renderer: Optional[VisualizerRenderer] = None
        self.dynamics_bundle = None
        self.lyrics_path: str = ""
        self._base_features: Optional[GlobalFeatureSet] = None
        self._theme_signature: Optional[tuple] = None
        self._live_last_t: Optional[float] = None

    # ------------------------------------------------------------------
    # Upload stabilization
    # ------------------------------------------------------------------
    def _stabilize_upload(self, path: str) -> str:
        """Copy an uploaded temp file to a content-addressed stable location.

        Gradio hands every upload a random temp filename, which defeats the
        feature cache (keyed by name/size/mtime). Copying to a stable name lets
        repeated uploads of the same file hit the analysis cache. The original
        filename stem is preserved because it doubles as the fallback track
        title when the file carries no metadata tags.
        """
        src = Path(path)
        stem = "".join(ch for ch in src.stem if ch not in '<>:"/\\|?*').strip()[:80]
        stable_dir = settings.get_cache_dir() / "webui_uploads"
        stable_dir.mkdir(parents=True, exist_ok=True)
        digest = _md5_file(src)
        stable = stable_dir / f"{digest}_{stem or 'audio'}{src.suffix.lower()}"
        if not stable.exists():
            shutil.copy2(src, stable)
        return str(stable)

    # ------------------------------------------------------------------
    # Track loading / analysis
    # ------------------------------------------------------------------
    def load_audio(
        self,
        audio_path: str,
        lrc_path: Optional[str] = None,
        progress_cb: Optional[Callable[[int, str], None]] = None,
    ) -> Dict[str, Any]:
        """Load and analyze an audio track."""
        if not audio_path or not Path(audio_path).is_file():
            raise FileNotFoundError(f"音频文件不存在: {audio_path}")

        if progress_cb:
            progress_cb(5, "稳定化上传文件...")

        stable_audio = self._stabilize_upload(audio_path)
        stable_lrc = self._stabilize_upload(lrc_path) if lrc_path and Path(lrc_path).is_file() else None

        if progress_cb:
            progress_cb(10, "读取音频元数据...")

        self.track = Track(stable_audio)
        # The stable copy's name is content-hashed for cache reuse; when the file
        # carries no embedded title tag, restore the original readable filename.
        if self.track.metadata.title == Path(stable_audio).stem:
            self.track.metadata.title = Path(audio_path).stem or self.track.metadata.title
        self.lyrics_path = stable_lrc
        if stable_lrc:
            try:
                self.track.lyrics = parse_lrc_file(stable_lrc)
            except Exception as exc:
                print(f"[WebUI Engine] Failed to parse uploaded LRC: {exc}")
                self.track.lyrics = None

        def _on_extract_progress(current: int, total: int, msg: str):
            if progress_cb and total > 0:
                pct = int(15 + (current / total) * 75)
                progress_cb(min(pct, 90), f"分析音频特征: {msg}")

        self.feature_cache = self.cache_manager.get_or_extract(
            stable_audio,
            progress_callback=_on_extract_progress,
        )

        if not self.feature_cache:
            raise RuntimeError("音频特征分析失败")

        if progress_cb:
            progress_cb(92, "构建动力学物理场...")

        self.dynamics_bundle = None
        try:
            self.dynamics_bundle = build_dynamics_bundle(self.feature_cache, simulation_hz=60.0)
        except Exception as e:
            print(f"[WebUI Engine] Dynamics compile warning: {e}")

        # Setup renderer
        self.renderer = VisualizerRenderer()
        self.renderer.resize(1280, 720)
        self._base_features = self.feature_cache.global_features
        self._theme_signature = None
        if self.dynamics_bundle:
            self.renderer.scene.set_dynamics_bundle(self.dynamics_bundle)
        self._ensure_theme({})

        f_hash = getattr(self.feature_cache.metadata, "file_hash", "")
        self.renderer.set_track_info(
            self.track.metadata.title,
            self.track.metadata.artist,
            file_hash=f_hash,
        )
        if self.track.lyrics:
            self.renderer.set_lyrics(self.track.lyrics)

        if progress_cb:
            progress_cb(100, "分析完成！")

        return self.describe_track()

    def describe_track(self) -> Dict[str, Any]:
        """Compile metadata + DNA summary for UI display."""
        gf = self._base_features
        theme = self.renderer.scene.theme if self.renderer else None

        def _clean(value: str) -> str:
            # Strip control characters that occasionally leak in from odd
            # filename encodings so the UI never shows mojibake artifacts.
            return "".join(ch for ch in str(value) if ch.isprintable()).strip() if value else value

        title = ""
        if self.track:
            title = _clean(self.track.metadata.title or Path(self.track.file_path).stem)
        return {
            "title": title,
            "artist": _clean((self.track.metadata.artist or "未知艺术家") if self.track else ""),
            "album": (self.track.metadata.album or "未知专辑") if self.track else "",
            "duration": round(self.feature_cache.duration, 2),
            "duration_str": f"{int(self.feature_cache.duration // 60):02d}:{int(self.feature_cache.duration % 60):02d}",
            "bpm": round(gf.tempo, 1) if gf else 120.0,
            "mood": getattr(gf, "mood", "chill") if gf else "chill",
            "archetype": getattr(gf, "structure_prior", "reactor") if gf else "reactor",
            "energy": round(float(gf.energy), 3) if gf else 0.5,
            "chaos": round(float(gf.chaos), 3) if gf else 0.3,
            "brightness": round(float(gf.brightness), 3) if gf else 0.5,
            "dna_structure": gf.structure_type if gf else "reactor",
            "dna_hue": round(float(gf.theme_hue_base), 1) if gf else 200.0,
            "dna_family": getattr(theme, "palette_family", "") if theme else "",
            "has_lyrics": bool(self.track and self.track.lyrics and self.track.lyrics.cues),
            "file_path": self.track.file_path if self.track else "",
        }

    # ------------------------------------------------------------------
    # Visual DNA overrides
    # ------------------------------------------------------------------
    def _track_seed(self) -> int:
        if self.dynamics_bundle is not None and getattr(self.dynamics_bundle, "track_seed", 0):
            return int(self.dynamics_bundle.track_seed)
        if self._base_features is not None:
            return int(self._base_features.theme_hue_base * 100)
        return 0

    def _compute_effective_features(self, visual: Dict[str, Any]) -> Optional[GlobalFeatureSet]:
        """Apply DNA overrides (structure/family/hue/energy...) onto analyzed features."""
        if self._base_features is None:
            return None
        return apply_dna_overrides(self._base_features, visual, track_seed=self._track_seed())

    def _ensure_theme(self, visual: Dict[str, Any]) -> None:
        """Rebuild the scene theme when DNA overrides changed. Resets transients."""
        if self.renderer is None:
            return
        signature = (
            str(visual.get("structure") or "auto"),
            str(visual.get("palette_family") or "auto"),
            round(float(visual.get("hue_shift") or 0.0), 2),
            None if visual.get("energy") is None else round(float(visual["energy"]), 3),
            None if visual.get("chaos") is None else round(float(visual["chaos"]), 3),
            None if visual.get("brightness") is None else round(float(visual["brightness"]), 3),
        )
        if signature == self._theme_signature:
            return
        self._theme_signature = signature
        effective = self._compute_effective_features(visual)
        if effective is not None:
            self.renderer.scene.load_track_features(effective)

    def _effective_title_artist(self, custom_settings: Dict[str, Any]) -> tuple:
        c_title = str(custom_settings.get("custom_track_title", "") or "").strip()
        c_artist = str(custom_settings.get("custom_track_artist", "") or "").strip()
        title = c_title or (self.track.metadata.title if self.track else "")
        artist = c_artist or (self.track.metadata.artist if self.track else "")
        return title, artist

    def _setup_renderer_for_track(self, renderer: VisualizerRenderer, visual: Dict[str, Any]) -> None:
        """Attach bundle/features/theme to a (possibly fresh) renderer."""
        if self.dynamics_bundle is not None:
            renderer.scene.set_dynamics_bundle(self.dynamics_bundle)
        effective = self._compute_effective_features(visual)
        if effective is not None:
            renderer.scene.load_track_features(effective)
        if self.track is not None and self.track.lyrics:
            renderer.set_lyrics(self.track.lyrics)

    # ------------------------------------------------------------------
    # Rendering
    # ------------------------------------------------------------------
    def render_frame(
        self,
        timestamp: float,
        width: int = 1280,
        height: int = 720,
        custom_settings: Optional[Dict[str, Any]] = None,
        visual_overrides: Optional[Dict[str, Any]] = None,
        mode: str = "still",
        playing: Optional[bool] = None,
    ) -> Image.Image:
        """
        Render a frame. Two modes:

        - ``still`` (default): deterministic scrub frame — O(1) seek plus a short
          warm-up so identical timestamps give identical pixels.
        - ``live``: desktop-parity continuous evolution. The persistent scene is
          advanced frame-by-frame exactly like the desktop player loop, so
          particles accumulate, beat events trigger bursts/shockwaves, the vortex
          keeps rotating and envelopes evolve naturally. A jump (seek or re-anchor)
          falls back to a fast O(1) seek before continuing.
        """
        ensure_qt_application()
        ui_settings = _filter_ui_settings(custom_settings)
        visual = visual_overrides or {}
        f_hash = getattr(self.feature_cache.metadata, "file_hash", "") if self.feature_cache else ""

        with settings.override(ui_settings):
            if not self.feature_cache or not self.renderer:
                if self.renderer is None:
                    self.renderer = VisualizerRenderer()
                    self._base_features = None
                    self._theme_signature = None
                self.renderer.resize(width, height)
                title, artist = self._effective_title_artist(ui_settings)
                self.renderer.set_track_info(title, artist)
                # Stills: skip the live fade-in and pin animation time for determinism.
                self.renderer.title_alpha = 1.0
                self.renderer.lyrics_alpha = 1.0
                self.renderer.reset_hud_smoothing()
                self.renderer.scene.time = max(0.0, float(timestamp))
                qimg = self.renderer.render_to_image(width, height, 0.016, reuse_buffer=False)
                return self._qimage_to_pil(qimg, width, height)

            self.renderer.resize(width, height)
            self._ensure_theme(visual)
            title, artist = self._effective_title_artist(ui_settings)
            track_sig = (title, artist, f_hash)
            if getattr(self.renderer, "_webui_track_sig", None) != track_sig:
                self.renderer._webui_track_sig = track_sig
                self.renderer.set_track_info(title, artist, file_hash=f_hash)
                self._live_last_t = None

            duration = self.feature_cache.duration
            t = max(0.0, min(float(timestamp), duration))

            if mode == "live":
                self._render_live(t, width, height, playing)
            else:
                self._render_still(t, width, height)

            qimg = self.renderer.render_to_image(width, height, 0.016, reuse_buffer=False)
            return self._qimage_to_pil(qimg, width, height)

    def _render_still(self, t: float, width: int, height: int) -> None:
        """Deterministic scrub frame: O(1) seek + envelope warm-up."""
        renderer = self.renderer
        # Stills show the fully faded-in state and carry no cross-render
        # HUD smoothing so identical timestamps render identical pixels.
        renderer.title_alpha = 1.0
        renderer.lyrics_alpha = 1.0
        renderer.reset_hud_smoothing()
        renderer.scene.seek_interactive(t, width=float(width), height=float(height))
        frame = self.feature_cache.get_frame_at_time(t)
        renderer.set_playback_position(t)
        # Warm up the smoothed envelopes toward steady state so stills keep
        # the visual richness of a live playback (drive starts at zero after seek).
        for _ in range(12):
            renderer.scene.update(frame, frame is not None, float(width), float(height), 0.016)
        self._live_last_t = None

    def _render_live(self, t: float, width: int, height: int, playing: Optional[bool]) -> None:
        """Desktop-parity continuous update on the persistent scene."""
        renderer = self.renderer
        frame = self.feature_cache.get_frame_at_time(t)
        renderer.set_playback_position(t)

        last = getattr(self, "_live_last_t", None)
        is_playing = True if playing is None else bool(playing)

        if not is_playing:
            # Desktop paused behaviour: idle drift animation, no audio frame input.
            renderer.scene.update(None, False, float(width), float(height), 0.016)
            self._live_last_t = t
            return

        if last is None or t < last - 0.05 or t - last > 0.4:
            # Re-anchor after seeks/pauses: O(1) deterministic snapshot, then
            # a short warm-up so envelopes are near steady state when the
            # continuous evolution continues on the next request.
            renderer.scene.seek_interactive(t, width=float(width), height=float(height))
            for _ in range(8):
                renderer.scene.update(frame, frame is not None, float(width), float(height), 0.016)
        else:
            dt = max(0.001, min(t - last, 0.25))
            renderer.scene.update(frame, frame is not None, float(width), float(height), dt)
        self._live_last_t = t

    @staticmethod
    def _qimage_to_pil(qimg, width: int, height: int) -> Image.Image:
        """Convert PySide6 QImage (RGBA8888) to a PIL Image (RGB)."""
        from PySide6.QtGui import QImage

        if qimg.isNull():
            return Image.new("RGB", (width, height), (15, 17, 30))

        if qimg.format() != QImage.Format.Format_RGBA8888:
            qimg = qimg.convertToFormat(QImage.Format.Format_RGBA8888)

        import numpy as np

        ptr = qimg.constBits()
        arr = np.frombuffer(ptr, dtype=np.uint8).reshape((qimg.height(), qimg.width(), 4))
        return Image.fromarray(arr[:, :, :3], mode="RGB")

    # ------------------------------------------------------------------
    # Preview clip
    # ------------------------------------------------------------------
    def generate_preview_clip(
        self,
        start_time: float,
        duration: float = 5.0,
        width: int = 1280,
        height: int = 720,
        fps: int = 30,
        custom_settings: Optional[Dict[str, Any]] = None,
        visual_overrides: Optional[Dict[str, Any]] = None,
        progress_cb: Optional[Callable[[int, str], None]] = None,
    ) -> str:
        """
        Generate a short MP4 clip honoring the same visual settings as the preview frame.
        Returns the absolute filepath of the temporary mp4 file.
        """
        if not self.track or not self.feature_cache:
            raise RuntimeError("尚未加载任何音频文件")

        ui_settings = _filter_ui_settings(custom_settings)
        visual = visual_overrides or {}
        f_hash = getattr(self.feature_cache.metadata, "file_hash", "")

        temp_dir = Path(tempfile.gettempdir()) / "stormy_pulse_webui"
        temp_dir.mkdir(parents=True, exist_ok=True)
        clip_path = temp_dir / f"preview_{int(time.time())}_{int(start_time)}.mp4"

        start_t = max(0.0, min(float(start_time), self.feature_cache.duration - 0.5))
        end_t = min(start_t + duration, self.feature_cache.duration)
        clip_dur = max(0.5, end_t - start_t)
        total_frames = max(1, int(math.ceil(clip_dur * fps)))
        dt = 1.0 / max(fps, 1)

        cmd = [
            "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
            "-ss", str(start_t),
            "-t", str(clip_dur),
            "-i", str(self.track.file_path),
            "-f", "rawvideo",
            "-vcodec", "rawvideo",
            "-pix_fmt", "rgba",
            "-s", f"{width}x{height}",
            "-r", str(fps),
            "-i", "-",
            "-map", "1:v:0",
            "-map", "0:a:0?",
            "-c:v", "libx264",
            "-preset", "veryfast",
            "-crf", "22",
            "-pix_fmt", "yuv420p",
            "-c:a", "aac",
            "-b:a", "192k",
            "-shortest",
            str(clip_path),
        ]

        with settings.override(ui_settings):
            renderer = VisualizerRenderer()
            renderer.resize(width, height)
            renderer.set_target_fps(fps)
            self._setup_renderer_for_track(renderer, visual)
            title, artist = self._effective_title_artist(ui_settings)
            renderer.set_track_info(title, artist, file_hash=f_hash)

            proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stderr=subprocess.PIPE)
            try:
                # Fast deterministic start state, then advance naturally.
                renderer.scene.seek_interactive(start_t, width=float(width), height=float(height))
                for i in range(total_frames):
                    cur_t = start_t + i * dt
                    frame = self.feature_cache.get_frame_at_time(cur_t)
                    renderer.set_playback_position(cur_t)
                    renderer.scene.update(frame, frame is not None, float(width), float(height), dt)
                    img = renderer.render_to_image(width, height, dt, reuse_buffer=True)
                    proc.stdin.write(bytes(img.constBits()))

                    if progress_cb and i % 15 == 0:
                        pct = int((i / total_frames) * 100)
                        progress_cb(pct, f"渲染片段帧: {i}/{total_frames}")

                proc.stdin.close()
                stderr_text = proc.stderr.read().decode("utf-8", errors="ignore")
                return_code = proc.wait(timeout=60)
                if return_code != 0:
                    raise RuntimeError(f"ffmpeg 编码预览片段失败: {stderr_text.strip() or return_code}")
            except Exception:
                if proc.stdin and not proc.stdin.closed:
                    proc.stdin.close()
                proc.kill()
                raise

        if progress_cb:
            progress_cb(100, "片段渲染完成！")

        return str(clip_path)

    # ------------------------------------------------------------------
    # Full export
    # ------------------------------------------------------------------
    def export_video(
        self,
        options: VideoExportOptions,
        custom_settings: Optional[Dict[str, Any]] = None,
        visual_overrides: Optional[Dict[str, Any]] = None,
        progress_cb: Optional[Callable[[int, str], None]] = None,
        cancel_check: Optional[Callable[[], bool]] = None,
    ) -> str:
        """Execute the full export pipeline with browser-side visual overrides."""
        if not self.track or not self.feature_cache:
            raise RuntimeError("尚未加载任何音频文件")

        ui_settings = _filter_ui_settings(custom_settings)
        visual = visual_overrides or {}
        # Sync the session renderer's theme, then ship both override dicts to the
        # exporter so sequential and parallel workers render identical visuals.
        self._ensure_theme(visual)

        title, artist = self._effective_title_artist(ui_settings)
        options.ui_overrides = {**ui_settings}
        options.feature_overrides = {**visual}
        options.title_override = title
        options.artist_override = artist
        options.lyrics_path = self.lyrics_path or ""

        exporter = VideoExporter()

        def _on_export_progress(pct: int, msg: str):
            if progress_cb:
                progress_cb(pct, msg)

        output_path = exporter.export_track(
            track=self.track,
            feature_cache=self.feature_cache,
            options=options,
            progress_callback=_on_export_progress,
            cancel_check=cancel_check,
        )
        return str(output_path)
