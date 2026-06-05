"""
Offline video export pipeline backed by ffmpeg.
"""
from __future__ import annotations

import math
import shlex
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional

from PySide6.QtCore import Qt
from PySide6.QtGui import QImage
from PySide6.QtWidgets import QApplication

from ..analysis.features import FeatureCache
from ..core.music_library import Track
from ..visual_gpu import VisualizerViewport


ProgressCallback = Callable[[int, str], None]
CancelCheck = Callable[[], bool]


class VideoExportError(RuntimeError):
    """Raised when offline export fails."""


class VideoExportCancelled(VideoExportError):
    """Raised when the user aborts export."""


@dataclass
class VideoExportOptions:
    """User-configurable parameters for video export."""

    output_path: str
    width: int = 1920
    height: int = 1080
    fps: int = 60
    video_codec: str = "libx264"
    preset: str = "slow"
    crf: Optional[int] = 18
    video_bitrate: str = ""
    pixel_format: str = "yuv420p"
    include_audio: bool = True
    audio_codec: str = "aac"
    audio_bitrate: str = "320k"
    extra_ffmpeg_args: str = ""


class VideoExporter:
    """Exports the current visualizer scene into a video file."""

    def __init__(self, ffmpeg_path: str = "ffmpeg"):
        self.ffmpeg_path = ffmpeg_path

    def export_track(
        self,
        track: Track,
        feature_cache: FeatureCache,
        options: VideoExportOptions,
        progress_callback: Optional[ProgressCallback] = None,
        cancel_check: Optional[CancelCheck] = None,
    ) -> Path:
        """Render the track offline and encode it through ffmpeg."""
        self._validate_options(options)
        output_path = Path(options.output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        app = QApplication.instance()
        if app is None:
            raise VideoExportError("视频导出需要活动的 Qt 应用上下文。")

        renderer = VisualizerViewport()
        renderer.resize(options.width, options.height)
        renderer.move(-20000, -20000)
        renderer.setAttribute(Qt.WidgetAttribute.WA_DontShowOnScreen, True)
        renderer.set_target_fps(options.fps)
        renderer.scene.load_track_features(feature_cache.global_features)
        renderer.set_track_info(track.metadata.title, track.metadata.artist)
        renderer.set_lyrics(track.load_lyrics())
        renderer.show()
        app.processEvents()

        ffmpeg_cmd = self._build_ffmpeg_command(track, options)
        proc = subprocess.Popen(
            ffmpeg_cmd,
            stdin=subprocess.PIPE,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
        )

        duration = max(feature_cache.duration, 0.0)
        total_frames = max(1, int(math.ceil(duration * options.fps)))
        dt = 1.0 / max(options.fps, 1)
        last_report_time = time.perf_counter()
        avg_render_ms = 0.0
        avg_write_ms = 0.0

        try:
            self._report(progress_callback, 0, "准备离屏渲染器")
            for frame_index in range(total_frames):
                if cancel_check and cancel_check():
                    raise VideoExportCancelled("用户取消导出")

                t = min(frame_index * dt, max(duration - 1e-6, 0.0))
                frame = feature_cache.get_frame_at_time(t)
                renderer.set_playback_position(t)
                renderer.scene.update(frame, frame is not None, float(options.width), float(options.height), dt)

                render_start = time.perf_counter()
                image = renderer.render_to_image(options.width, options.height, dt)
                render_end = time.perf_counter()

                self._write_image(proc.stdin, image)
                write_end = time.perf_counter()

                render_ms = (render_end - render_start) * 1000.0
                write_ms = (write_end - render_end) * 1000.0
                if frame_index == 0:
                    avg_render_ms = render_ms
                    avg_write_ms = write_ms
                else:
                    avg_render_ms = avg_render_ms * 0.92 + render_ms * 0.08
                    avg_write_ms = avg_write_ms * 0.92 + write_ms * 0.08

                now = time.perf_counter()
                if frame_index == 0 or frame_index == total_frames - 1 or (now - last_report_time) >= 0.10:
                    pct = int(((frame_index + 1) / total_frames) * 100)
                    self._report(
                        progress_callback,
                        min(pct, 99),
                        f"正在渲染帧 {frame_index + 1}/{total_frames} | 渲染 {avg_render_ms:.1f}ms | 写入编码器 {avg_write_ms:.1f}ms",
                    )
                    last_report_time = now

            if proc.stdin:
                proc.stdin.close()

            stderr_text = ""
            if proc.stderr:
                stderr_text = proc.stderr.read().decode("utf-8", errors="ignore")
            return_code = proc.wait()
            if return_code != 0:
                raise VideoExportError(stderr_text.strip() or f"ffmpeg exited with code {return_code}")

            self._report(progress_callback, 100, "导出完成")
            return output_path

        except Exception:
            if proc.stdin and not proc.stdin.closed:
                proc.stdin.close()
            proc.terminate()
            try:
                proc.wait(timeout=3)
            except Exception:
                proc.kill()
            if output_path.exists():
                try:
                    output_path.unlink()
                except Exception:
                    pass
            raise
        finally:
            renderer.hide()
            renderer.deleteLater()
            app.processEvents()

    def _validate_options(self, options: VideoExportOptions):
        if options.width < 320 or options.height < 180:
            raise VideoExportError("导出分辨率过小")
        if options.width % 2 != 0 or options.height % 2 != 0:
            raise VideoExportError("导出分辨率必须是偶数，便于编码器处理")
        if options.fps <= 0:
            raise VideoExportError("导出 FPS 必须大于 0")
        if options.height * 16 != options.width * 9:
            raise VideoExportError("导出分辨率必须保持 16:9")

    def _build_ffmpeg_command(self, track: Track, options: VideoExportOptions) -> list[str]:
        cmd = [
            self.ffmpeg_path,
            "-y",
            "-hide_banner",
            "-loglevel",
            "error",
            "-f",
            "rawvideo",
            "-vcodec",
            "rawvideo",
            "-pix_fmt",
            "rgba",
            "-s",
            f"{options.width}x{options.height}",
            "-r",
            str(options.fps),
            "-i",
            "-",
        ]

        if options.include_audio:
            cmd += ["-i", track.file_path, "-map", "0:v:0", "-map", "1:a:0?"]

        cmd += ["-c:v", options.video_codec]
        if options.preset and self._codec_supports_preset(options.video_codec):
            cmd += ["-preset", options.preset]
        if options.crf is not None and self._codec_supports_crf(options.video_codec):
            cmd += ["-crf", str(options.crf)]
        if options.video_bitrate:
            cmd += ["-b:v", options.video_bitrate]
        if options.pixel_format:
            cmd += ["-pix_fmt", options.pixel_format]

        if options.include_audio:
            cmd += ["-c:a", options.audio_codec, "-b:a", options.audio_bitrate, "-shortest"]
        else:
            cmd += ["-an"]

        if options.extra_ffmpeg_args.strip():
            cmd += shlex.split(options.extra_ffmpeg_args, posix=False)

        if Path(options.output_path).suffix.lower() in {".mp4", ".m4v"}:
            cmd += ["-movflags", "+faststart"]

        cmd += [options.output_path]
        return cmd

    def _codec_supports_preset(self, codec: str) -> bool:
        return codec in {
            "libx264",
            "libx265",
            "libsvtav1",
            "h264_nvenc",
            "hevc_nvenc",
            "h264_amf",
            "hevc_amf",
            "av1_amf",
            "prores_ks",
        }

    def _codec_supports_crf(self, codec: str) -> bool:
        return codec in {"libx264", "libx265", "libsvtav1", "libvpx-vp9"}

    def _write_image(self, stream, image: QImage):
        if image.format() != QImage.Format.Format_RGBA8888:
            image = image.convertToFormat(QImage.Format.Format_RGBA8888)
        stream.write(image.constBits())

    def _report(self, callback: Optional[ProgressCallback], value: int, message: str):
        if callback:
            callback(max(0, min(100, value)), message)
