"""
GPU (OpenGL) export worker process.

`VisualizerViewport.render_to_image` performs Qt GUI operations (widget show,
repaint, `QApplication.processEvents`), which Qt only allows on the thread that
owns the QApplication. Inside the WebUI server the main thread belongs to
uvicorn, so GPU exports run in this dedicated child process instead: here the
process main thread *is* the GUI thread, which makes the GL pipeline safe and
isolates driver crashes from the server.
"""
from __future__ import annotations

import os
import sys
from typing import Any, Dict

# Headless-first: force the Qt offscreen platform on Linux unless the operator
# explicitly chose one (a set-but-unreachable DISPLAY must not abort the child).
if sys.platform.startswith("linux"):
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


def run_gpu_export_worker(
    track_path: str,
    options_dict: Dict[str, Any],
    ui_overrides: Dict[str, Any],
    feature_overrides: Dict[str, Any],
    title: str,
    artist: str,
    lyrics_path: str,
    progress_queue,
    cancel_event,
) -> None:
    """Entry point for the spawned GPU export process (pickled by reference).

    Runs non-daemon so it may fan out into the exporter's own daemonic segment
    workers; a SIGTERM handler converts parent-side terminate() into SystemExit
    so multiprocessing's atexit hook reaps those daemonic children cleanly.
    """
    import signal

    def _sigterm_handler(signum, frame):
        raise SystemExit(0)

    try:
        signal.signal(signal.SIGTERM, _sigterm_handler)
    except Exception:
        pass  # not the main thread / unsupported platform

    from app.config.settings import settings

    with settings.override(ui_overrides):
        try:
            from PySide6.QtWidgets import QApplication

            QApplication.instance() or QApplication([])

            from app.analysis.cache import FeatureCacheManager
            from app.core.music_library import Track
            from app.dynamics.context import build_dynamics_bundle
            from app.export.video_exporter import (
                VideoExporter,
                VideoExportCancelled,
                VideoExportOptions,
            )
            from app.visual.themes import apply_dna_overrides

            options = VideoExportOptions(**options_dict)

            cache = FeatureCacheManager().load(track_path)
            if cache is None:
                progress_queue.put(("error", "未能在导出进程中加载分析缓存"))
                return

            track = Track(track_path)
            exporter = VideoExporter()

            # Ship the DNA overrides through the shared options fields so the
            # sequential GPU path inside the exporter applies them (it builds
            # its own dynamics bundle + theme from these).
            options.ui_overrides = dict(ui_overrides)
            options.feature_overrides = dict(feature_overrides)
            options.title_override = title
            options.artist_override = artist
            options.lyrics_path = lyrics_path

            def _progress(pct: int, msg: str):
                progress_queue.put(("progress", (int(pct), msg)))

            output = exporter.export_track(
                track=track,
                feature_cache=cache,
                options=options,
                progress_callback=_progress,
                cancel_check=cancel_event.is_set,
            )
            progress_queue.put(("done", str(output)))
        except VideoExportCancelled:
            progress_queue.put(("cancelled", ""))
        except Exception as exc:
            progress_queue.put(("error", str(exc)))
