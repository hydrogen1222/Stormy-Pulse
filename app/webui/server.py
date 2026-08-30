"""
FastAPI-based WebUI server for Stormy-Pulse Music Visualizer.

Real-time browser playback: the browser <audio> element owns the playback
clock (perfect A/V sync, native seek/volume), while the backend renders
deterministic visualization frames on demand for the current timestamp.
The audio file itself is served with HTTP Range support so seeking never
re-uploads the whole track.

Single-user by design: one global WebUISession guarded by locks.
"""
from __future__ import annotations

import argparse
import io
import os
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path
from typing import Any, Dict, Optional

# Headless-first: the WebUI never shows a window on purpose. Force the Qt
# offscreen platform on Linux unless the operator explicitly chose one —
# DISPLAY being set (e.g. SSH X11 forwarding) does NOT mean it is reachable,
# and an unusable xcb plugin aborts the whole process at QApplication creation.
if sys.platform.startswith("linux"):
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from fastapi import FastAPI, File, Header, HTTPException, UploadFile
from fastapi.responses import FileResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles

from app.webui.engine import WebUISession
from app.webui.hardware import (
    detect_available_encoders,
    get_default_encoder,
    get_encoder_dropdown_choices,
    get_system_info,
)
from app.export.video_exporter import VideoExportCancelled, VideoExportOptions

app = FastAPI(title="Stormy-Pulse WebUI", docs_url=None, redoc_url=None)

_session = WebUISession()  # single-user session (creates the Qt application)

# Guards: `_render_lock` serializes every Qt render/analysis on the session;
# `_state_lock` guards the small progress/state dicts polled by the client.
_render_lock = threading.RLock()
_state_lock = threading.Lock()

_state: Dict[str, Any] = {
    "phase": "idle",       # idle | analyzing | ready | error
    "progress": 0,
    "message": "",
    "error": "",
    "track": None,
    "clip_url": "",
    "export": {"phase": "idle", "progress": 0, "message": "", "file": "", "error": ""},
}

# Rolling log of export progress messages (including transient failure/retry
# notices that would otherwise be overwritten within a second).
_EXPORT_HISTORY = None  # lazy deque, bounded below

_PARAMS: Dict[str, Any] = {
    # canvas
    "aspect": "16:9",
    "frame_height": 720,
    # visual DNA overrides
    "structure": "auto",
    "palette_family": "auto",
    "hue_shift": 0.0,
    "energy": 0.5,
    "chaos": 0.3,
    "brightness": 0.5,
    # titles
    "custom_title": "",
    "custom_artist": "",
    "show_title": True,
    "show_artist": True,
    "title_scale": 1.0,
    "title_x": 0.0,
    "title_y": 0.0,
    "artist_scale": 1.0,
    "artist_x": 0.0,
    "artist_y": 0.0,
    # lyrics + hud
    "show_lyrics": False,
    "lyrics_scale": 1.0,
    "lyrics_x": 0.0,
    "lyrics_y": 0.0,
    "show_left_hud": True,
    "show_right_hud": True,
    "hud_scale": 1.0,
    "effect_scale": 1.0,
}

_AUDIO_MIME = {
    ".flac": "audio/flac", ".mp3": "audio/mpeg", ".wav": "audio/wav",
    ".ogg": "audio/ogg", ".m4a": "audio/mp4", ".opus": "audio/ogg",
}

_EXPORT_DIR = Path(tempfile.gettempdir()) / "stormy_pulse_exports"

# Analysis/export jobs run one at a time; these flags are checked before starting.
_analysis_thread: Optional[threading.Thread] = None
_export_thread: Optional[threading.Thread] = None
_export_cancel: Optional[threading.Event] = None
_gpu_render_probe: Optional[bool] = None
_gpu_probe_detail: str = ""


# ---------------------------------------------------------------------------
# Param mapping helpers
# ---------------------------------------------------------------------------
def _ui_settings_from_params(p: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "visual_canvas_ratio": p["aspect"],
        "custom_track_title": p["custom_title"],
        "custom_track_artist": p["custom_artist"],
        "show_track_title": p["show_title"],
        "show_track_artist": p["show_artist"],
        "font_scale_title": p["title_scale"],
        "module_scale_title": p["title_scale"],
        "layout_title_x": p["title_x"],
        "layout_title_y": p["title_y"],
        "font_scale_artist": p["artist_scale"],
        "module_scale_artist": p["artist_scale"],
        "layout_artist_x": p["artist_x"],
        "layout_artist_y": p["artist_y"],
        "show_lyrics": p["show_lyrics"],
        "font_scale_lyrics": p["lyrics_scale"],
        "module_scale_lyrics": p["lyrics_scale"],
        "layout_lyrics_x": p["lyrics_x"],
        "layout_lyrics_y": p["lyrics_y"],
        "show_left_hud": p["show_left_hud"],
        "show_right_hud": p["show_right_hud"],
        "hud_scale": p["hud_scale"],
        "font_scale_hud": p["hud_scale"],
        "show_fps": False,
        "module_scale_effect": p["effect_scale"],
    }


def _visual_from_params(p: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "structure": p["structure"],
        "palette_family": p["palette_family"],
        "hue_shift": p["hue_shift"],
        "energy": p["energy"],
        "chaos": p["chaos"],
        "brightness": p["brightness"],
    }


def _frame_size(aspect: str, height: int, w_override: int = 0, h_override: int = 0) -> tuple[int, int]:
    if w_override > 0 and h_override > 0:
        w, h = w_override, h_override
    elif aspect == "9:16":
        h = height
        w = int(round(height * 9.0 / 16.0))
    else:
        h = height
        w = int(round(height * 16.0 / 9.0))
    w = max(320, min(1920, w))
    h = max(180, min(1920, h))
    if w % 2:
        w += 1
    if h % 2:
        h += 1
    return w, h


def _set_state(**kwargs: Any) -> None:
    with _state_lock:
        _state.update(kwargs)


_PROGRESS_PREFIXES = ("并行渲染中", "正在渲染帧", "正在取消导出")


def _record_export_message(msg: str) -> None:
    import collections

    global _EXPORT_HISTORY
    if _EXPORT_HISTORY is None:
        _EXPORT_HISTORY = collections.deque(maxlen=40)
    _EXPORT_HISTORY.append(f"[{time.strftime('%H:%M:%S')}] {msg}")


def _set_export_state(**kwargs: Any) -> None:
    with _state_lock:
        msg = kwargs.get("message")
        if msg and not str(msg).startswith(_PROGRESS_PREFIXES):
            # Keep transient failure/retry/phase notices; periodic per-frame
            # progress lines would drown them out within a second.
            _record_export_message(str(msg))
        _state["export"].update(kwargs)


def _export_running() -> bool:
    with _state_lock:
        return _state["export"].get("phase") == "running"


# ---------------------------------------------------------------------------
# Analysis job
# ---------------------------------------------------------------------------
def _run_analysis(audio_path: str, lrc_path: Optional[str]) -> None:
    try:
        def _progress(pct: int, msg: str):
            with _state_lock:
                _state["progress"] = int(pct)
                _state["message"] = msg

        with _render_lock:
            info = _session.load_audio(audio_path, lrc_path, progress_cb=_progress)

        # Seed the dynamics sliders with the analyzed DNA values.
        with _state_lock:
            _PARAMS["energy"] = info["energy"]
            _PARAMS["chaos"] = info["chaos"]
            _PARAMS["brightness"] = info["brightness"]
            _state["track"] = info
            _state["phase"] = "ready"
            _state["progress"] = 100
            _state["message"] = "分析完成"
    except Exception as exc:
        with _state_lock:
            _state["phase"] = "error"
            _state["error"] = str(exc)
            _state["message"] = f"分析失败: {exc}"


def _start_analysis(audio_path: str, lrc_path: Optional[str]) -> bool:
    global _analysis_thread
    with _state_lock:
        if _state["phase"] == "analyzing":
            return False
        _state.update(phase="analyzing", progress=0, message="准备分析...", error="", track=None)
    _analysis_thread = threading.Thread(
        target=_run_analysis, args=(audio_path, lrc_path), daemon=True
    )
    _analysis_thread.start()
    return True


# ---------------------------------------------------------------------------
# Export / clip jobs
# ---------------------------------------------------------------------------
def _run_export(
    options: VideoExportOptions,
    ui_settings: Dict[str, Any],
    visual: Dict[str, Any],
    cancel_event: threading.Event,
) -> None:
    if options.use_gpu_renderer:
        _run_gpu_export(options, ui_settings, visual, cancel_event)
        return
    try:
        def _progress(pct: int, msg: str):
            _set_export_state(progress=int(pct), message=msg)

        with _render_lock:
            _session._ensure_theme(visual)  # noqa: SLF001 - keep preview theme in sync

        out_path = _session.export_video(
            options=options,
            custom_settings=ui_settings,
            visual_overrides=visual,
            progress_cb=_progress,
            cancel_check=cancel_event.is_set,
        )
        _set_export_state(phase="done", progress=100, message="导出完成", file=str(out_path))
    except VideoExportCancelled:
        try:
            Path(options.output_path).unlink(missing_ok=True)
        except Exception:
            pass
        _set_export_state(phase="cancelled", message="已取消导出", progress=0)
    except Exception as exc:
        _set_export_state(phase="error", error=str(exc), message=f"导出失败: {exc}")


def _run_gpu_export(
    options: VideoExportOptions,
    ui_settings: Dict[str, Any],
    visual: Dict[str, Any],
    cancel_event: threading.Event,
) -> None:
    """GPU (OpenGL) frame rendering must own a Qt GUI thread; the server's main
    thread is uvicorn's event loop, so the whole export runs in a child process
    whose main thread is the GUI thread. Progress streams back over a queue and
    cancellation is forwarded through a multiprocessing Event."""
    import dataclasses
    import multiprocessing as mp

    from app.webui.export_worker import run_gpu_export_worker

    ctx = mp.get_context("spawn")
    progress_queue = ctx.Queue()
    child_cancel = ctx.Event()

    track = _session.track
    track_path = track.file_path

    def _first_non_empty(*values: Any) -> str:
        for value in values:
            if value and str(value).strip():
                return str(value).strip()
        return ""

    # GPU export bypasses WebUISession.export_video(), so carry the effective
    # title/artist/lyrics overrides into the child explicitly; otherwise custom
    # WebUI title/artist and uploaded .lrc would be silently dropped.
    title_override = _first_non_empty(
        options.title_override,
        ui_settings.get("custom_track_title"),
        track.metadata.title if track else "",
    )
    artist_override = _first_non_empty(
        options.artist_override,
        ui_settings.get("custom_track_artist"),
        track.metadata.artist if track else "",
    )
    lyrics_path = options.lyrics_path or _session.lyrics_path or ""

    proc = ctx.Process(
        target=run_gpu_export_worker,
        args=(
            track_path,
            dataclasses.asdict(options),
            ui_settings,
            visual,
            title_override,
            artist_override,
            lyrics_path,
            progress_queue,
            child_cancel,
        ),
        # Non-daemon: this child fans out into N daemonic GPU segment workers,
        # and daemonic processes are not allowed to have children. The finally
        # block below terminates it explicitly, and its own daemonic children
        # are cleaned up by multiprocessing's atexit hook when it exits.
        daemon=False,
    )
    proc.start()

    def _watch_cancel():
        while proc.is_alive():
            if cancel_event.is_set():
                child_cancel.set()
            time.sleep(0.2)

    cancel_thread = threading.Thread(target=_watch_cancel, daemon=True)
    cancel_thread.start()

    last_message = "GPU 渲染导出中..."
    try:
        while True:
            try:
                kind, payload = progress_queue.get(timeout=0.3)
            except Exception:
                kind, payload = None, None

            if kind == "progress":
                pct, msg = payload
                last_message = msg
                _set_export_state(progress=int(pct), message=msg)
            elif kind == "done":
                _set_export_state(phase="done", progress=100, message="导出完成", file=str(payload))
                return
            elif kind == "cancelled":
                try:
                    Path(options.output_path).unlink(missing_ok=True)
                except Exception:
                    pass
                _set_export_state(phase="cancelled", message="已取消导出", progress=0)
                return
            elif kind == "error":
                _set_export_state(phase="error", error=str(payload), message=f"导出失败: {payload}")
                return
            elif proc.exitcode not in (None, 0):
                raise RuntimeError(f"GPU 导出进程异常退出 (code={proc.exitcode}): {last_message}")
            elif kind is None and not proc.is_alive():
                raise RuntimeError(f"GPU 导出进程提前退出: {last_message}")

            if cancel_event.is_set() and child_cancel.is_set():
                _set_export_state(message="正在取消导出...")
            proc.join(timeout=0.05)
    except VideoExportCancelled:
        _set_export_state(phase="cancelled", message="已取消导出", progress=0)
    except Exception as exc:
        _set_export_state(phase="error", error=str(exc), message=f"导出失败: {exc}")
    finally:
        if proc.is_alive():
            proc.terminate()
        try:
            proc.join(timeout=2)
        except Exception:
            pass
        try:
            if _state_lock and _state["export"].get("phase") == "running":
                _set_export_state(phase="error", error="GPU 导出进程提前退出", message="导出失败")
        except Exception:
            pass


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------
@app.get("/")
def index() -> FileResponse:
    return FileResponse(Path(__file__).parent / "static" / "index.html")


@app.get("/api/system")
def api_system() -> Dict[str, Any]:
    choices = get_encoder_dropdown_choices()
    return {
        "system": get_system_info(),
        "encoders": detect_available_encoders(),
        "encoder_choices": choices,
        "default_encoder": get_default_encoder(choices),
    }


@app.get("/api/state")
def api_state() -> Dict[str, Any]:
    with _state_lock:
        snap = dict(_state)
        snap["export"] = dict(_state["export"])
        snap["params"] = dict(_PARAMS)
        snap["export_history"] = list(_EXPORT_HISTORY) if _EXPORT_HISTORY else []
    # GIL-atomic flag reads; do NOT take the render lock here because the
    # state poller must stay responsive while a long export is running.
    snap["has_audio"] = bool(_session.track and _session.feature_cache)
    snap["audio_ready"] = bool(_session.track)
    return snap


@app.post("/api/upload")
async def api_upload(audio: UploadFile = File(...), lrc: Optional[UploadFile] = File(None)) -> Dict[str, Any]:
    tmp_dir = Path(tempfile.gettempdir()) / "stormy_pulse_uploads"
    # Per-upload subfolder keeps the original filename intact (it doubles as the
    # fallback track title) without collisions between uploads.
    upload_dir = tmp_dir / f"u{int(time.time() * 1000)}"
    upload_dir.mkdir(parents=True, exist_ok=True)

    def _temp_name(upload: UploadFile, default_suffix: str) -> Path:
        original = Path(upload.filename or "upload")
        suffix = (original.suffix or default_suffix).lower()
        stem = "".join(ch for ch in original.stem if ch not in '<>:"/\\|?*').strip()[:80] or "upload"
        return upload_dir / f"{stem}{suffix}"

    audio_tmp = _temp_name(audio, ".bin")
    with open(audio_tmp, "wb") as f:
        while chunk := await audio.read(1 << 20):
            f.write(chunk)

    lrc_tmp = None
    if lrc is not None and lrc.filename:
        lrc_tmp = _temp_name(lrc, ".lrc")
        with open(lrc_tmp, "wb") as f:
            while chunk := await lrc.read(1 << 20):
                f.write(chunk)

    started = _start_analysis(str(audio_tmp), str(lrc_tmp) if lrc_tmp else None)
    if not started:
        raise HTTPException(status_code=409, detail="已有分析任务在进行中")
    return {"started": True}


_PARAM_FLOAT_KEYS = frozenset({
    "hue_shift", "energy", "chaos", "brightness",
    "title_scale", "title_x", "title_y", "artist_scale", "artist_x", "artist_y",
    "lyrics_scale", "lyrics_x", "lyrics_y", "hud_scale", "effect_scale",
})
_PARAM_INT_KEYS = frozenset({"frame_height"})


@app.post("/api/params")
async def api_params(update: Dict[str, Any]) -> Dict[str, Any]:
    allowed = set(_PARAMS.keys())
    with _state_lock:
        for key, value in update.items():
            if key in allowed and value is not None:
                # Defensive coercion: API clients may send numeric params as strings.
                try:
                    if key in _PARAM_FLOAT_KEYS:
                        value = float(value)
                    elif key in _PARAM_INT_KEYS:
                        value = int(float(value))
                except (TypeError, ValueError):
                    continue
                if key == "aspect" and value not in ("16:9", "9:16"):
                    continue
                _PARAMS[key] = value
        return {"params": dict(_PARAMS)}


@app.get("/api/frame")
def api_frame(t: float = 0.0, w: int = 0, h: int = 0, mode: str = "still", playing: int = 1):
    with _state_lock:
        if _state["phase"] == "analyzing":
            raise HTTPException(status_code=503, detail="正在分析音频，请稍候")
        params = dict(_PARAMS)
    if _export_running():
        # The offline export pipeline drives the process-global settings
        # object; live rendering must stay paused until it finishes.
        raise HTTPException(status_code=503, detail="正在后台导出视频，实时预览已暂停")

    if not (_session.track and _session.feature_cache):
        raise HTTPException(status_code=409, detail="尚未加载音频，请先上传")

    width, height = _frame_size(params["aspect"], params["frame_height"], w, h)
    t = max(0.0, min(float(t), _session.feature_cache.duration))

    with _render_lock:
        img = _session.render_frame(
            t, width, height,
            custom_settings=_ui_settings_from_params(params),
            visual_overrides=_visual_from_params(params),
            mode="live" if mode == "live" else "still",
            playing=bool(playing),
        )

    buf = io.BytesIO()
    img.save(buf, "JPEG", quality=88)
    return Response(
        content=buf.getvalue(),
        media_type="image/jpeg",
        headers={"Cache-Control": "no-store", "X-Frame-Time": f"{t:.3f}"},
    )


_AUDIO_MIME = {
    ".flac": "audio/flac", ".mp3": "audio/mpeg", ".wav": "audio/wav",
    ".ogg": "audio/ogg", ".m4a": "audio/mp4", ".opus": "audio/ogg",
}

# Browsers play these containers/codecs reliably everywhere; anything else
# (ogg/opus on Safari, ALAC in m4a, exotic codecs) gets an AAC sidecar copy.
_NATIVE_AUDIO_EXTS = {".mp3", ".wav", ".flac"}


def _ensure_playable_audio(force_recode: bool = False, allow_transcode: bool = True) -> Path:
    """Return a browser-playable audio file path for the current track.

    Non-native containers are transcoded once with ffmpeg into an AAC/M4A
    sidecar next to the analysis copy; browsers always play that.
    ``allow_transcode=False`` only inspects/validates the current track and never
    starts ffmpeg, so callers can do the cheap part under ``_render_lock`` and
    run the actual transcode outside the lock.
    """
    track = _session.track
    if track is None:
        raise HTTPException(status_code=409, detail="尚未加载音频，请先上传")

    src = Path(track.file_path)
    if not src.is_file():
        raise HTTPException(status_code=409, detail="音频文件已被清理，请重新上传")

    if not force_recode and src.suffix.lower() in _NATIVE_AUDIO_EXTS:
        return src

    if not allow_transcode:
        return src

    sidecar = src.parent / f"{src.stem}_web.m4a"
    if not sidecar.is_file():
        import shutil
        import subprocess

        if shutil.which("ffmpeg") is None:
            return src  # no ffmpeg available: serve as-is and let the browser try
        try:
            proc = subprocess.run(
                [
                    "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
                    "-i", str(src),
                    "-c:a", "aac", "-b:a", "256k",
                    str(sidecar),
                ],
                capture_output=True,
                timeout=180,
            )
        except Exception:
            return src  # ffmpeg missing/hung/failed: fall back to the original file
        if proc.returncode != 0 or not sidecar.is_file():
            return src  # transcode failed: fall back to the original file

    return sidecar


@app.get("/api/audio")
def api_audio(range_header: Optional[str] = Header(None, alias="Range"), recode: int = 0):
    with _render_lock:
        # Only validate/resolve the source under the lock.  Transcoding (if
        # needed) happens below without the render lock so live frames keep
        # flowing while ffmpeg works.
        src_path = _ensure_playable_audio(force_recode=False, allow_transcode=False)
    if recode or src_path.suffix.lower() not in _NATIVE_AUDIO_EXTS:
        path = _ensure_playable_audio(force_recode=bool(recode))
    else:
        path = src_path
    size = path.stat().st_size
    content_type = _AUDIO_MIME.get(path.suffix.lower(), "audio/mp4" if path.suffix == ".m4a" else "application/octet-stream")

    range_start, range_end = 0, size - 1
    status_code = 200
    if range_header and range_header.startswith("bytes="):
        try:
            spec = range_header.split("=", 1)[1]
            start_str, end_str = (spec.split("-", 1) + [""])[:2]
            if start_str:
                range_start = int(start_str)
                range_end = int(end_str) if end_str else size - 1
            elif end_str:  # suffix range: last N bytes
                range_start = max(0, size - int(end_str))
            # Defensive clamp: malformed/negative ranges must not produce a
            # negative length or read past the file.
            range_start = max(0, min(range_start, size - 1))
            range_end = max(0, min(range_end, size - 1))
            if range_end < range_start:
                range_start, range_end = 0, size - 1
                status_code = 200
            else:
                status_code = 206
        except ValueError:
            range_start, range_end = 0, size - 1
            status_code = 200

    length = range_end - range_start + 1

    def _iter():
        with open(path, "rb") as f:
            f.seek(range_start)
            remaining = length
            while remaining > 0:
                chunk = f.read(min(1 << 18, remaining))
                if not chunk:
                    break
                remaining -= len(chunk)
                yield chunk

    headers = {
        "Accept-Ranges": "bytes",
        "Content-Length": str(length),
        "Cache-Control": "no-store",
    }
    if status_code == 206:
        headers["Content-Range"] = f"bytes {range_start}-{range_end}/{size}"
    return StreamingResponse(_iter(), status_code=status_code, media_type=content_type, headers=headers)


@app.post("/api/clip")
def api_clip(body: Dict[str, Any]) -> Dict[str, Any]:
    if _export_running():
        raise HTTPException(status_code=503, detail="正在后台导出视频，请稍后再试")
    if not (_session.track and _session.feature_cache):
        raise HTTPException(status_code=409, detail="尚未加载音频，请先上传")

    with _state_lock:
        params = dict(_PARAMS)
    duration = max(1.0, min(float(body.get("duration", 5.0)), 15.0))
    fps = int(body.get("fps", 30))
    start = float(body.get("start", 0.0))

    with _render_lock:
        clip_w, clip_h = _frame_size(params["aspect"], min(int(params["frame_height"]), 540))
        clip_path = _session.generate_preview_clip(
            start_time=start,
            duration=duration,
            width=clip_w,
            height=clip_h,
            fps=fps,
            custom_settings=_ui_settings_from_params(params),
            visual_overrides=_visual_from_params(params),
        )
    url = f"/api/clip/file?path={clip_path}"
    _set_state(clip_url=url)
    return {"url": url}


@app.get("/api/clip/file")
def api_clip_file(path: str):
    p = Path(path)
    if not (p.is_file() and p.suffix.lower() == ".mp4" and "stormy_pulse_webui" in str(p.parent)):
        raise HTTPException(status_code=404, detail="片段不存在")
    return FileResponse(p, media_type="video/mp4", filename=p.name)


@app.post("/api/export")
def api_export(body: Dict[str, Any]) -> Dict[str, Any]:
    global _export_thread, _export_cancel
    if not (_session.track and _session.feature_cache):
        raise HTTPException(status_code=409, detail="尚未加载音频，请先上传")
    with _state_lock:
        if _state["export"]["phase"] in ("running",):
            raise HTTPException(status_code=409, detail="已有导出任务在进行中")
        params = dict(_PARAMS)

    width = int(body.get("width", 1920))
    height = int(body.get("height", 1080))
    if width % 2 or height % 2:
        raise HTTPException(status_code=400, detail="分辨率宽高必须为偶数")
    if width * 9 != height * 16 and width * 16 != height * 9:
        raise HTTPException(status_code=400, detail="导出分辨率必须为 16:9 或 9:16")

    use_gpu_renderer = bool(body.get("use_gpu_renderer", False))

    _EXPORT_DIR.mkdir(parents=True, exist_ok=True)
    stem = Path(_session.track.file_path).stem
    out_file = _EXPORT_DIR / f"{stem}_visualizer_{int(time.time())}.mp4"

    # 9:16 export should render with the matching canvas ratio.
    ui_settings = _ui_settings_from_params(params)
    ui_settings["visual_canvas_ratio"] = "9:16" if width < height else "16:9"

    options = VideoExportOptions(
        output_path=str(out_file),
        width=width,
        height=height,
        fps=int(body.get("fps", 60)),
        video_codec=str(body.get("video_codec", "libx264")),
        preset=str(body.get("preset", "quality")),
        video_bitrate=str(body.get("video_bitrate", "16M")),
        audio_bitrate=str(body.get("audio_bitrate", "320k")),
        cpu_render_workers=int(body.get("cpu_render_workers", 4)),
        use_gpu_renderer=use_gpu_renderer,
        # Many-worker GPU exports: skip the O(N^2) exact per-segment replay.
        fast_segment_start=use_gpu_renderer,
    )

    cancel_event = threading.Event()
    _export_cancel = cancel_event

    _set_export_state(phase="running", progress=0, message="准备导出...", file="", error="")
    _export_thread = threading.Thread(
        target=_run_export,
        args=(options, ui_settings, _visual_from_params(params), cancel_event),
        daemon=True,
    )
    _export_thread.start()
    return {"started": True}


@app.post("/api/export/cancel")
def api_export_cancel() -> Dict[str, Any]:
    """Request cancellation of the running export (cooperative, checked per frame)."""
    with _state_lock:
        running = _state["export"].get("phase") == "running"
    if _export_cancel is not None:
        _export_cancel.set()
    if running:
        _set_export_state(message="正在取消导出...")
        return {"cancelling": True}
    return {"cancelling": False}


def _probe_gpu_render() -> "tuple[bool, str]":
    """Probe OpenGL frame-render availability in an isolated child process.

    Creating a GL context can hard-crash on machines without proper drivers;
    a subprocess probe keeps the server alive to report "unavailable".
    Returns (ok, detail) where detail explains the failure for the UI.

    Second attempt: when an NVIDIA glvnd vendor JSON exists, retry with
    __EGL_VENDOR_LIBRARY_FILENAMES pinned to it — glvnd sometimes dispatches
    to Mesa (which cannot create a headless context on an NVIDIA-only box)
    instead of the NVIDIA vendor library. When that retry succeeds, the env
    is applied process-wide so GPU export children inherit it.
    """
    code = (
        "import sys, traceback\n"
        "from PySide6.QtWidgets import QApplication\n"
        "from app.visual_gpu import VisualizerViewport\n"
        "try:\n"
        "    app = QApplication.instance() or QApplication([])\n"
        "    v = VisualizerViewport()\n"
        "    img = v.render_to_image(64, 64, 0.016)\n"
        "    assert not img.isNull()\n"
        "    print('GPU_OK')\n"
        "except Exception:\n"
        "    traceback.print_exc()\n"
        "    sys.exit(3)\n"
    )

    def _run_child(extra_env: Optional[Dict[str, str]] = None):
        env = None
        if extra_env:
            env = dict(os.environ)
            env.update(extra_env)
        return subprocess.run(
            [sys.executable, "-c", code],
            capture_output=True,
            text=True,
            timeout=90,
            cwd=str(Path(__file__).resolve().parents[2]),
            env=env,
        )

    def _detail(proc) -> str:
        detail = (proc.stderr or proc.stdout or "").strip().splitlines()
        tail = " | ".join(line.strip() for line in detail[-4:] if line.strip())
        return tail or f"探测失败 (exit={proc.returncode})"

    try:
        proc = _run_child()
    except Exception as exc:
        return False, f"探测子进程未能运行: {exc}"

    if proc.returncode == 0 and "GPU_OK" in proc.stdout:
        return True, "GPU_OK"

    # Retry: pin glvnd to the NVIDIA vendor JSON when it exists.
    nvidia_json = ""
    if sys.platform.startswith("linux"):
        for candidate in (
            "/usr/share/glvnd/egl_vendor.d/10_nvidia.json",
            "/etc/glvnd/egl_vendor.d/10_nvidia.json",
        ):
            if os.path.isfile(candidate):
                nvidia_json = candidate
                break
    if nvidia_json:
        try:
            proc2 = _run_child({"__EGL_VENDOR_LIBRARY_FILENAMES": nvidia_json})
        except Exception:
            proc2 = None
        if proc2 is not None and proc2.returncode == 0 and "GPU_OK" in proc2.stdout:
            # Apply the workaround for the whole server so spawned GPU export
            # children inherit it.
            os.environ["__EGL_VENDOR_LIBRARY_FILENAMES"] = nvidia_json
            return True, f"GPU_OK (via {nvidia_json})"
        if proc2 is not None:
            proc = proc2

    tail = _detail(proc)
    hint = ""
    if sys.platform.startswith("linux"):
        import glob

        if not (glob.glob("/usr/lib64/libnvidia-eglcore*") or glob.glob("/usr/lib/x86_64-linux-gnu/libnvidia-eglcore*")):
            hint = "；未找到 libnvidia-eglcore（NVIDIA 驱动可能缺少 OpenGL/EGL 组件）"
        elif nvidia_json:
            hint = (
                "；NVIDIA EGL 的默认 Display 需要一个 X 服务器引导，"
                "无显示器机器可启动无头 X 后以 DISPLAY=:0 运行："
                "sudo Xorg :0 -sharevts -noreset（配置 AllowEmptyInitialConfiguration）"
            )
        else:
            hint = "；未找到 glvnd NVIDIA 厂商注册文件（10_nvidia.json）"
    return False, f"{tail}{hint}"


@app.get("/api/gpu")
def api_gpu() -> Dict[str, Any]:
    global _gpu_render_probe, _gpu_probe_detail
    if _gpu_render_probe is None:
        _gpu_render_probe, _gpu_probe_detail = _probe_gpu_render()
    return {
        "gpu_render_available": _gpu_render_probe,
        "probe_detail": _gpu_probe_detail,
    }


def run_gpu_check() -> None:
    """Standalone diagnostic: print GPU frame-render probe result to stdout."""
    ok, detail = _probe_gpu_render()
    if ok:
        print("✅ GPU (OpenGL) 帧渲染可用")
    else:
        print("❌ GPU (OpenGL) 帧渲染不可用")
        print(f"原因: {detail}")


@app.get("/api/export/file")
def api_export_file():
    with _state_lock:
        file_path = _state["export"].get("file", "")
        phase = _state["export"].get("phase", "")
    if phase != "done" or not file_path:
        raise HTTPException(status_code=404, detail="尚无已完成的导出文件")
    p = Path(file_path)
    if not p.is_file():
        raise HTTPException(status_code=404, detail="导出文件已不存在")
    return FileResponse(p, media_type="video/mp4", filename=p.name)


# Static assets (app.js / style.css)
_static_dir = Path(__file__).parent / "static"
app.mount("/static", StaticFiles(directory=str(_static_dir)), name="static")


def _primary_lan_ip() -> str:
    """Best-effort primary LAN address for the startup banner."""
    import socket

    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("8.8.8.8", 80))  # no traffic is sent; just picks a route
        return s.getsockname()[0]
    except Exception:
        return "127.0.0.1"
    finally:
        s.close()


def main():
    """CLI entry point for the WebUI server."""
    parser = argparse.ArgumentParser(description="Stormy-Pulse Music Visualizer WebUI Server")
    parser.add_argument("--host", type=str, default="0.0.0.0", help="Host to listen on (default: 0.0.0.0, all interfaces)")
    parser.add_argument("--port", type=int, default=7860, help="Port to listen on (default: 7860)")
    parser.add_argument("--check-gpu", action="store_true", help="Probe OpenGL frame-render availability, print the reason, and exit")
    args = parser.parse_args()

    if args.check_gpu:
        run_gpu_check()
        return

    import uvicorn

    lan_ip = _primary_lan_ip()
    print("\n" + "=" * 55)
    print("🎵 Stormy-Pulse WebUI Server starting...")
    print(f"🌐 Local access: http://localhost:{args.port}")
    print(f"🌐 LAN access:   http://{lan_ip}:{args.port}  (listening on {args.host})")
    print("=" * 55 + "\n")
    uvicorn.run(app, host=args.host, port=args.port, log_level="warning")


if __name__ == "__main__":
    main()
