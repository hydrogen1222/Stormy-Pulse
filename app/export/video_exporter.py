"""
Offline video export pipeline backed by ffmpeg.
"""
from __future__ import annotations

import math
import multiprocessing as mp
import os
import queue
import shlex
import subprocess
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, Optional

from PySide6.QtGui import QImage

from ..analysis.cache import FeatureCacheManager
from ..analysis.features import FeatureCache
from ..config.settings import settings
from ..core.lyrics import parse_lrc_file
from ..core.music_library import Track
from ..visual.renderer import VisualizerRenderer


ProgressCallback = Callable[[int, str], None]
CancelCheck = Callable[[], bool]

_SEGMENT_INTERMEDIATE_CODEC = "libx264"
_SEGMENT_INTERMEDIATE_PIX_FMT = "yuv420p"  # x264 lossless is more stable with standard yuv420p
_SEGMENT_INTERMEDIATE_ARGS = ["-preset", "ultrafast", "-crf", "0"]
_RENDER_PROGRESS_WEIGHT = 88

# Semantic quality names (WebUI) mapped onto codec-native x264/x265 presets.
_QUALITY_PRESET_ALIASES = {
    "high_quality": "veryslow",
    "quality": "slow",
    "balanced": "medium",
    "speed": "faster",
}


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
    cpu_render_workers: int = 0
    use_gpu_renderer: bool = False
    # Headless/WebUI surface overrides: applied around rendering without touching
    # the persisted settings file, and propagated into parallel worker processes.
    ui_overrides: Dict[str, Any] = field(default_factory=dict)
    feature_overrides: Dict[str, Any] = field(default_factory=dict)
    title_override: str = ""
    artist_override: str = ""
    lyrics_path: str = ""


def _write_image_to_stream(stream, image: QImage):
    if image.format() != QImage.Format.Format_RGBA8888:
        image = image.convertToFormat(QImage.Format.Format_RGBA8888)
    stream.write(image.constBits())


def _aspect_ratio_key(width: int, height: int) -> str:
    if width * 16 == height * 9:
        return "9:16"
    if height * 16 == width * 9:
        return "16:9"
    return ""


def _build_segment_ffmpeg_command(
    ffmpeg_path: str,
    output_path: str,
    width: int,
    height: int,
    fps: int,
) -> list[str]:
    return [
        ffmpeg_path,
        "-y",
        "-hide_banner",
        "-loglevel",
        "error",
        "-threads",
        "2",  # Limit threads per sub-process to prevent global thread explosion
        "-f",
        "rawvideo",
        "-vcodec",
        "rawvideo",
        "-pix_fmt",
        "rgba",
        "-s",
        f"{width}x{height}",
        "-r",
        str(fps),
        "-i",
        "-",
        "-c:v",
        _SEGMENT_INTERMEDIATE_CODEC,
        *_SEGMENT_INTERMEDIATE_ARGS,
        "-pix_fmt",
        _SEGMENT_INTERMEDIATE_PIX_FMT,
        "-an",
        output_path,
    ]


def _resolve_lyrics(track: Track, lyrics_path: str = ""):
    """Prefer an explicit lyrics override (WebUI upload), else the adjacent .lrc file."""
    if lyrics_path:
        try:
            return parse_lrc_file(lyrics_path)
        except Exception as exc:
            print(f"[Exporter] Failed to parse lyrics override {lyrics_path}: {exc}")
            return None
    return track.load_lyrics()


def _resolve_scene_features(feature_cache: FeatureCache, feature_overrides: Optional[dict], track_seed: int = 0):
    """Apply DNA overrides onto analyzed global features for scene/theme creation."""
    from app.visual.themes import apply_dna_overrides

    return apply_dna_overrides(feature_cache.global_features, feature_overrides, track_seed)


def _render_segment_worker(
    ffmpeg_path: str,
    track_path: str,
    title: str,
    artist: str,
    width: int,
    height: int,
    fps: int,
    start_frame: int,
    end_frame: int,
    duration: float,
    segment_path: str,
    worker_index: int,
    progress_queue,
    cancel_event,
    ui_overrides: Optional[dict] = None,
    feature_overrides: Optional[dict] = None,
    lyrics_path: str = "",
    use_gpu: bool = False,
):
    """Entry point for spawned worker processes: apply UI overrides, then render."""
    with settings.override(ui_overrides):
        _render_segment_worker_impl(
            ffmpeg_path, track_path, title, artist, width, height, fps,
            start_frame, end_frame, duration, segment_path, worker_index,
            progress_queue, cancel_event, feature_overrides, lyrics_path, use_gpu,
        )


def _render_segment_worker_impl(
    ffmpeg_path: str,
    track_path: str,
    title: str,
    artist: str,
    width: int,
    height: int,
    fps: int,
    start_frame: int,
    end_frame: int,
    duration: float,
    segment_path: str,
    worker_index: int,
    progress_queue,
    cancel_event,
    feature_overrides: Optional[dict] = None,
    lyrics_path: str = "",
    use_gpu: bool = False,
):
    """Render one contiguous segment into a temporary lossless file.

    With ``use_gpu=True`` the segment renders through the OpenGL viewport
    (this child process's main thread is its Qt GUI thread).
    """
    try:
        from PySide6.QtWidgets import QApplication

        app = QApplication.instance() or QApplication([])
        cache = FeatureCacheManager().load(track_path)
        if cache is None:
            progress_queue.put(("error", worker_index, "未能在子进程中加载分析缓存"))
            return

        if use_gpu:
            from app.visual_gpu.viewport import VisualizerViewport
            renderer = VisualizerViewport()
        else:
            renderer = VisualizerRenderer()
        renderer.resize(width, height)
        renderer.set_target_fps(fps)

        track = Track(track_path)

        bundle = None
        try:
            from app.dynamics.context import build_dynamics_bundle
            bundle = build_dynamics_bundle(cache, simulation_hz=60.0)
            renderer.scene.set_dynamics_bundle(bundle)
        except Exception as err:
            print(f"[ExportWorker] Dynamics compile fallback: {err}")

        seed = int(getattr(bundle, "track_seed", 0) or 0)
        renderer.scene.load_track_features(_resolve_scene_features(cache, feature_overrides, seed))
        f_hash = getattr(cache.metadata, "file_hash", "")
        renderer.set_track_info(title, artist, file_hash=f_hash)
        renderer.set_lyrics(_resolve_lyrics(track, lyrics_path))

        ffmpeg_cmd = _build_segment_ffmpeg_command(ffmpeg_path, segment_path, width, height, fps)
        proc = subprocess.Popen(
            ffmpeg_cmd,
            stdin=subprocess.PIPE,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
        )

        dt = 1.0 / max(fps, 1)
        rendered = 0
        report_every = max(1, (end_frame - start_frame) // 24)

        try:
            start_time = max(0.0, start_frame * dt)
            renderer.scene.rebuild_to_time(start_time, width=width, height=height, fps=fps)

            for frame_index in range(start_frame, end_frame):
                if cancel_event.is_set():
                    raise VideoExportCancelled("用户取消导出")

                t = min(frame_index * dt, max(duration - 1e-6, 0.0))
                frame = cache.get_frame_at_time(t)
                renderer.set_playback_position(t)
                renderer.scene.update(frame, frame is not None, float(width), float(height), dt)

                image = renderer.render_to_image(width, height, dt, reuse_buffer=True)
                _write_image_to_stream(proc.stdin, image)
                rendered += 1
                if rendered == 1 or rendered == (end_frame - start_frame) or rendered % report_every == 0:
                    progress_queue.put(("progress", worker_index, rendered))

            if proc.stdin:
                proc.stdin.close()
            stderr_text = ""
            if proc.stderr:
                stderr_text = proc.stderr.read().decode("utf-8", errors="ignore")
            return_code = proc.wait()
            if return_code != 0:
                raise VideoExportError(stderr_text.strip() or f"segment ffmpeg exited with code {return_code}")

            progress_queue.put(("done", worker_index, segment_path))
            app.processEvents()
        except Exception as exc:
            if proc.stdin and not proc.stdin.closed:
                proc.stdin.close()
            proc.terminate()
            try:
                proc.wait(timeout=2)
            except Exception:
                proc.kill()
            progress_queue.put(("error", worker_index, str(exc)))
    except Exception as exc:
        progress_queue.put(("error", worker_index, str(exc)))


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

        # GPU (OpenGL) rendering also parallelizes: each spawned worker owns its
        # own GL context, so N workers render N segments concurrently (the
        # per-frame bottleneck is the GL readback + composite, which scales).
        worker_count = self._resolve_worker_count(options, feature_cache.duration)
        if worker_count > 1:
            try:
                return self._export_track_parallel(
                    track=track,
                    feature_cache=feature_cache,
                    options=options,
                    worker_count=worker_count,
                    progress_callback=progress_callback,
                    cancel_check=cancel_check,
                )
            except Exception as exc:
                self._report(progress_callback, 0, f"并行渲染回退到单线程: {exc}")

        return self._export_track_sequential(
            track=track,
            feature_cache=feature_cache,
            options=options,
            progress_callback=progress_callback,
            cancel_check=cancel_check,
        )

    def _export_track_sequential(
        self,
        track: Track,
        feature_cache: FeatureCache,
        options: VideoExportOptions,
        progress_callback: Optional[ProgressCallback],
        cancel_check: Optional[CancelCheck],
    ) -> Path:
        output_path = Path(options.output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        if options.use_gpu_renderer:
            from app.visual_gpu.viewport import VisualizerViewport
            renderer = VisualizerViewport()
            renderer.resize(options.width, options.height)
            renderer.set_target_fps(options.fps)
        else:
            renderer = VisualizerRenderer()
            renderer.resize(options.width, options.height)
            renderer.set_target_fps(options.fps)

        try:
            from app.dynamics.context import build_dynamics_bundle
            bundle = build_dynamics_bundle(feature_cache, simulation_hz=60.0)
            renderer.scene.set_dynamics_bundle(bundle)
        except Exception as err:
            print(f"[ExportSeq] Dynamics compile fallback: {err}")
            bundle = None

        seq_seed = int(getattr(bundle, "track_seed", 0) or 0)
        renderer.scene.load_track_features(_resolve_scene_features(feature_cache, options.feature_overrides, seq_seed))
        seq_f_hash = getattr(feature_cache.metadata, "file_hash", "")
        seq_title = options.title_override.strip() or track.metadata.title
        seq_artist = options.artist_override.strip() or track.metadata.artist
        renderer.set_track_info(seq_title, seq_artist, file_hash=seq_f_hash)
        renderer.set_lyrics(_resolve_lyrics(track, options.lyrics_path))

        duration = max(feature_cache.duration, 0.0)
        total_frames = max(1, int(math.ceil(duration * options.fps)))
        dt = 1.0 / max(options.fps, 1)
        last_report_time = time.perf_counter()
        avg_render_ms = 0.0
        avg_write_ms = 0.0

        with settings.override(options.ui_overrides):
            ffmpeg_cmd = self._build_rawvideo_ffmpeg_command(track, options)
            proc = subprocess.Popen(
                ffmpeg_cmd,
                stdin=subprocess.PIPE,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE,
            )

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
                    image = renderer.render_to_image(options.width, options.height, dt, reuse_buffer=True)
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

    def _export_track_parallel(
        self,
        track: Track,
        feature_cache: FeatureCache,
        options: VideoExportOptions,
        worker_count: int,
        progress_callback: Optional[ProgressCallback],
        cancel_check: Optional[CancelCheck],
    ) -> Path:
        output_path = Path(options.output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        duration = max(feature_cache.duration, 0.0)
        total_frames = max(1, int(math.ceil(duration * options.fps)))
        frame_ranges = self._partition_frames(total_frames, worker_count)
        ctx = mp.get_context("spawn")
        progress_queue = ctx.Queue()
        cancel_event = ctx.Event()
        segment_progress = {idx: 0 for idx in range(len(frame_ranges))}
        segment_outputs: dict[int, str] = {}
        processes = []

        with tempfile.TemporaryDirectory(prefix="mv_export_") as temp_dir:
            try:
                self._report(progress_callback, 0, f"启动 {worker_count} 个并行渲染进程")
                for idx, (start_frame, end_frame) in enumerate(frame_ranges):
                    segment_path = str(Path(temp_dir) / f"segment_{idx:03d}.mkv")
                    proc = ctx.Process(
                        target=_render_segment_worker,
                        args=(
                            self.ffmpeg_path,
                            track.file_path,
                            options.title_override.strip() or track.metadata.title,
                            options.artist_override.strip() or track.metadata.artist,
                            options.width,
                            options.height,
                            options.fps,
                            start_frame,
                            end_frame,
                            duration,
                            segment_path,
                            idx,
                            progress_queue,
                            cancel_event,
                            options.ui_overrides,
                            options.feature_overrides,
                            options.lyrics_path,
                            options.use_gpu_renderer,
                        ),
                        daemon=True,
                    )
                    proc.start()
                    processes.append(proc)

                done_count = 0
                while done_count < len(processes):
                    if cancel_check and cancel_check():
                        cancel_event.set()
                        raise VideoExportCancelled("用户取消导出")

                    try:
                        msg_type, worker_index, payload = progress_queue.get(timeout=0.2)
                    except queue.Empty:
                        for proc in processes:
                            if proc.exitcode not in (None, 0):
                                raise VideoExportError(f"渲染子进程异常退出: {proc.exitcode}")
                        continue

                    if msg_type == "progress":
                        segment_progress[worker_index] = int(payload)
                        rendered_frames = sum(segment_progress.values())
                        pct = min(
                            int(rendered_frames / max(total_frames, 1) * _RENDER_PROGRESS_WEIGHT),
                            _RENDER_PROGRESS_WEIGHT,
                        )
                        self._report(
                            progress_callback,
                            pct,
                            f"并行渲染中 {rendered_frames}/{total_frames} 帧 | 进程 {worker_index + 1}/{len(processes)}",
                        )
                    elif msg_type == "done":
                        segment_outputs[worker_index] = str(payload)
                        done_count += 1
                    elif msg_type == "error":
                        cancel_event.set()
                        raise VideoExportError(str(payload))

                for proc in processes:
                    proc.join()
                    if proc.exitcode not in (0, None):
                        raise VideoExportError(f"渲染子进程异常退出: {proc.exitcode}")

                if len(segment_outputs) != len(frame_ranges):
                    raise VideoExportError("并行渲染未生成完整的中间片段")

                concat_list = Path(temp_dir) / "segments.txt"
                concat_list.write_text(
                    "".join(
                        f"file '{Path(segment_outputs[idx]).as_posix()}'\n"
                        for idx in range(len(frame_ranges))
                    ),
                    encoding="utf-8",
                )

                self._report(progress_callback, _RENDER_PROGRESS_WEIGHT + 2, "合并中间片段并编码最终视频")
                final_cmd = self._build_concat_ffmpeg_command(track, options, concat_list)
                proc = subprocess.Popen(
                    final_cmd,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.PIPE,
                )
                stderr_text = ""
                if proc.stderr:
                    stderr_text = proc.stderr.read().decode("utf-8", errors="ignore")
                return_code = proc.wait()
                if return_code != 0:
                    raise VideoExportError(stderr_text.strip() or f"ffmpeg exited with code {return_code}")

                self._report(progress_callback, 100, "导出完成")
                return output_path
            except Exception:
                cancel_event.set()
                for proc in processes:
                    if proc.is_alive():
                        proc.terminate()
                for proc in processes:
                    try:
                        proc.join(timeout=1)
                    except Exception:
                        pass
                if output_path.exists():
                    try:
                        output_path.unlink()
                    except Exception:
                        pass
                raise

    def _resolve_worker_count(self, options: VideoExportOptions, duration: float) -> int:
        if options.cpu_render_workers > 0:
            # If user explicitly specified workers, respect it fully
            return options.cpu_render_workers

        # Auto-mode: Cap workers to prevent MemoryError (OOM) on systems with high core counts but limited RAM/Swap
        cpu_count = os.cpu_count() or 1
        return max(1, min(4, cpu_count // 2 if cpu_count > 4 else cpu_count))

    def _partition_frames(self, total_frames: int, worker_count: int) -> list[tuple[int, int]]:
        chunk = max(1, math.ceil(total_frames / max(worker_count, 1)))
        ranges = []
        start = 0
        while start < total_frames:
            end = min(total_frames, start + chunk)
            ranges.append((start, end))
            start = end
        return ranges

    def _validate_options(self, options: VideoExportOptions):
        if options.width < 320 or options.height < 180:
            raise VideoExportError("导出分辨率过小")
        if options.width % 2 != 0 or options.height % 2 != 0:
            raise VideoExportError("导出分辨率必须是偶数，便于编码器处理")
        if options.fps <= 0:
            raise VideoExportError("导出 FPS 必须大于 0")
        if not _aspect_ratio_key(options.width, options.height):
            raise VideoExportError("导出分辨率必须保持 16:9 或 9:16")

    def _build_rawvideo_ffmpeg_command(self, track: Track, options: VideoExportOptions) -> list[str]:
        cmd = [
            self.ffmpeg_path,
            "-y",
            "-hide_banner",
            "-loglevel",
            "error",
        ]
        if options.video_codec in {"av1_amf", "h264_amf", "hevc_amf"}:
            cmd += [
                "-init_hw_device",
                "d3d11va=amf:0",
                "-filter_hw_device",
                "amf",
            ]
        cmd += [
            "-threads",
            "0",
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
        return self._append_output_args(cmd, track, options)

    def _build_concat_ffmpeg_command(self, track: Track, options: VideoExportOptions, concat_list: Path) -> list[str]:
        cmd = [
            self.ffmpeg_path,
            "-y",
            "-hide_banner",
            "-loglevel",
            "error",
            "-threads",
            "4",  # Limit threads to reduce memory usage during 4K AV1 encoding
            "-f",
            "concat",
            "-safe",
            "0",
            "-i",
            str(concat_list),
        ]
        if options.video_codec in {"av1_amf", "h264_amf", "hevc_amf"}:
            # The hwupload filter in the AMF output chain needs an explicit
            # D3D11 device, same as the rawvideo pipeline.
            cmd += ["-init_hw_device", "d3d11va=amf:0", "-filter_hw_device", "amf"]
        return self._append_output_args(cmd, track, options)

    def _append_output_args(self, cmd: list[str], track: Track, options: VideoExportOptions) -> list[str]:
        if options.include_audio:
            cmd += ["-i", track.file_path, "-map", "0:v:0", "-map", "1:a:0?"]

        is_amf = options.video_codec in {"av1_amf", "h264_amf", "hevc_amf"}

        if is_amf:
            cmd += ["-vf", "format=rgba,hwupload"]

        cmd += ["-c:v", options.video_codec]

        # Preset / Quality handling
        if is_amf:
            quality_val = options.preset if options.preset in {"high_quality", "quality", "balanced", "speed"} else "quality"
            cmd += ["-quality", quality_val]
            cmd += ["-usage", "transcoding"]
        elif options.preset:
            # WebUI exposes semantic quality names; translate them to codec-native
            # presets because x264/x265 reject values like "quality".
            preset_val = _QUALITY_PRESET_ALIASES.get(options.preset, options.preset)
            # Codec-specific preset mapping for SVT-AV1 and NVENC
            if options.video_codec == "libsvtav1":
                mapping = {"veryslow": "1", "slower": "2", "slow": "4", "medium": "6", "fast": "8", "faster": "10", "veryfast": "12", "ultrafast": "13"}
                preset_val = mapping.get(options.preset, options.preset)
            elif options.video_codec in {"h264_nvenc", "hevc_nvenc", "av1_nvenc"}:
                mapping = {"veryslow": "p7", "slower": "p7", "slow": "p6", "medium": "p4", "fast": "p3", "faster": "p2", "veryfast": "p2", "ultrafast": "p1"}
                preset_val = mapping.get(options.preset, "p6")

            if self._codec_supports_preset(options.video_codec):
                cmd += ["-preset", preset_val]

        if not is_amf and options.crf is not None and self._codec_supports_crf(options.video_codec):
            cmd += ["-crf", str(options.crf)]
        elif options.video_codec in {"av1_amf", "h264_amf", "hevc_amf", "h264_nvenc", "hevc_nvenc", "av1_nvenc"} and not options.video_bitrate:
            cmd += ["-b:v", "20M"]

        if options.video_bitrate:
            cmd += ["-b:v", options.video_bitrate]
        if not is_amf and options.pixel_format:
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
            "av1_nvenc",
            "h264_qsv",
            "hevc_qsv",
            "av1_qsv",
            "prores_ks",
        }

    def _codec_supports_crf(self, codec: str) -> bool:
        return codec in {"libx264", "libx265", "libsvtav1", "libvpx-vp9"}

    def _write_image(self, stream, image: QImage):
        _write_image_to_stream(stream, image)

    def _report(self, callback: Optional[ProgressCallback], value: int, message: str):
        if callback:
            callback(max(0, min(100, value)), message)
