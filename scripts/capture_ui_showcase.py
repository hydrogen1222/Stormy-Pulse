"""
Generate UI showcase screenshots for responsive and palette/background verification.
"""
import json
import os
import sys
import time
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("QT_QPA_OFFSCREEN_SIZE", "2560x1440")

ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = ROOT / "artifacts" / "ui_showcase"

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from PySide6.QtWidgets import QApplication  # noqa: E402

from app.ui.main_window import MainWindow  # noqa: E402


TARGET_FAMILIES = {
    "cool_lattice": "clinical_neon",
    "slate_depth": "slate_lab",
    "signal_balance": "nature_calm",
    "reactive_bold": "science_bold",
}


def _pump(app: QApplication, seconds: float = 0.2):
    end = time.time() + seconds
    while time.time() < end:
        app.processEvents()
        time.sleep(0.02)


def _wait_until(app: QApplication, cond, timeout_sec: float) -> bool:
    start = time.time()
    while time.time() - start < timeout_sec:
        app.processEvents()
        if cond():
            return True
        time.sleep(0.03)
    return False


def _wait_analysis(win: MainWindow, app: QApplication, timeout_sec: float = 900.0):
    ok = _wait_until(
        app,
        lambda: (
            win.visualization_sync.feature_cache is not None
            and win.visualizer.scene.theme is not None
            and (win._analysis_thread is None or not win._analysis_thread.isRunning())
        ),
        timeout_sec,
    )
    if not ok:
        raise TimeoutError("Timed out waiting for track analysis to finish.")


def _find_album_dir() -> Path:
    explicit = ROOT / "岡村孝子 - liberte 1987 - FLAC 分轨"
    if explicit.exists():
        return explicit
    for d in ROOT.iterdir():
        if d.is_dir() and "liberte" in d.name.lower() and "flac" in d.name.lower():
            return d
    raise FileNotFoundError("Album folder not found. Expected liberte FLAC folder in project root.")


def _pick_frame_time(win: MainWindow) -> float:
    cache = win.visualization_sync.feature_cache
    if cache is None:
        return 0.0
    beats = cache.events.beat_positions
    if len(beats) > 0:
        return float(beats[len(beats) // 2])
    return max(6.0, min(cache.duration * 0.45, cache.duration - 3.0))


def _prepare_visual_frame(win: MainWindow, app: QApplication):
    t = _pick_frame_time(win)
    frame = win.visualization_sync.update(t)
    if frame:
        width = win.visualizer.width()
        height = win.visualizer.height()
        win.visualizer.scene.update(frame, True, width, height, 0.016)
        win.visualizer.title_alpha = 1.0
        win.visualizer.update()
        _pump(app, 0.15)


def _load_track(win: MainWindow, app: QApplication, idx: int):
    win._load_track(idx)
    _wait_analysis(win, app)
    _prepare_visual_frame(win, app)

    theme = win.visualizer.scene.theme
    track = win.music_library.tracks[idx]

    bg_base = theme.get_color("background_base")[:3]
    bg_fog = theme.get_color("background_fog")[:3]
    bg_halo = theme.get_color("background_halo")[:3]

    return {
        "index": idx,
        "title": track.metadata.title,
        "artist": track.metadata.artist,
        "palette_family": theme.palette_family,
        "palette_blend_family": theme.palette_blend_family,
        "palette_blend_ratio": theme.palette_blend_ratio,
        "background_base": bg_base,
        "background_fog": bg_fog,
        "background_halo": bg_halo,
    }


def _capture(win: MainWindow, app: QApplication, size: tuple[int, int], path: Path):
    win.showNormal()
    win.playlist_panel.hide()
    win.resize(size[0] + 120, size[1] + 240)
    _pump(app, 0.3)

    # Nudge outer window so the visualizer area reaches target size.
    dw = size[0] - win.visualizer.width()
    dh = size[1] - win.visualizer.height()
    if abs(dw) > 2 or abs(dh) > 2:
        win.resize(win.width() + dw, win.height() + dh)
        _pump(app, 0.2)

    pix = win.visualizer.grab()
    path.parent.mkdir(parents=True, exist_ok=True)
    if not pix.save(str(path), "PNG"):
        raise RuntimeError(f"Failed to save screenshot: {path}")


def _font_snapshot(win: MainWindow):
    width = float(win.visualizer.width())
    height = float(win.visualizer.height())
    fonts = win.visualizer._build_typography(width, height)
    return {name: round(font.pointSizeF(), 1) for name, font in fonts.items()}


def _family_match(track_info: dict, family: str) -> bool:
    if track_info["palette_family"] == family:
        return True
    return (
        track_info["palette_blend_family"] == family
        and float(track_info["palette_blend_ratio"]) >= 0.16
    )


def main():
    album_dir = _find_album_dir()
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    app = QApplication(sys.argv)

    win = MainWindow()
    win.showNormal()
    win.resize(1400, 860)
    _pump(app, 0.4)

    # Force production showcase mode for this capture run.
    win.settings.data["show_track_title"] = True
    win.settings.data["show_left_hud"] = True
    win.settings.data["show_right_hud"] = True
    win.settings.data["show_dev_hud"] = False
    win.settings.data["hud_opacity"] = 0.95

    win._on_add_folder(str(album_dir))
    _wait_analysis(win, app)
    win.update_timer.stop()

    total = win.music_library.get_track_count()
    if total < 4:
        raise RuntimeError("Need at least four tracks for background showcase.")

    # Load all tracks once and collect theme mapping.
    all_track_infos = []
    for idx in range(total):
        all_track_infos.append(_load_track(win, app, idx))

    # Pick targets for required family categories.
    family_showcase = {}
    used_indices = set()
    for label, fam in TARGET_FAMILIES.items():
        exact = next(
            (
                info
                for info in all_track_infos
                if info["index"] not in used_indices and info["palette_family"] == fam
            ),
            None,
        )
        if exact:
            family_showcase[label] = exact
            used_indices.add(exact["index"])
            continue

        blended = next(
            (
                info
                for info in all_track_infos
                if info["index"] not in used_indices and _family_match(info, fam)
            ),
            None,
        )
        if blended:
            family_showcase[label] = blended
            used_indices.add(blended["index"])

    # If some target family missing in this album, fill with remaining unique-family tracks.
    unique_candidates = []
    seen_family = set(info["palette_family"] for info in family_showcase.values())
    for info in all_track_infos:
        if info["index"] in used_indices:
            continue
        if info["palette_family"] not in seen_family:
            unique_candidates.append(info)
            seen_family.add(info["palette_family"])
    for label in TARGET_FAMILIES.keys():
        if label in family_showcase:
            continue
        if unique_candidates:
            family_showcase[label] = unique_candidates.pop(0)

    # Ensure at least 4 screenshots for background comparison.
    if len(family_showcase) < 4:
        fallback_pool = [info for info in all_track_infos if info["index"] not in used_indices]
        for label in TARGET_FAMILIES.keys():
            if label in family_showcase:
                continue
            if fallback_pool:
                family_showcase[label] = fallback_pool.pop(0)

    if len(family_showcase) < 4:
        raise RuntimeError("Could not assemble four tracks for showcase.")

    # Core 3 layout screenshots.
    song_a = all_track_infos[0]
    song_b = all_track_infos[1]

    _load_track(win, app, song_a["index"])
    normal_path = OUT_DIR / "normal_song_a.png"
    _capture(win, app, (1400, 860), normal_path)
    normal_fonts = _font_snapshot(win)

    _load_track(win, app, song_b["index"])
    fullscreen_path = OUT_DIR / "fullscreen_song_b.png"
    _capture(win, app, (1920, 1080), fullscreen_path)
    fullscreen_fonts = _font_snapshot(win)

    _load_track(win, app, song_a["index"])
    small_path = OUT_DIR / "small_song_a.png"
    _capture(win, app, (1000, 700), small_path)
    small_fonts = _font_snapshot(win)

    # Four-song background family comparison screenshots.
    family_paths = {}
    for label, info in family_showcase.items():
        _load_track(win, app, info["index"])
        shot_path = OUT_DIR / f"family_{label}.png"
        _capture(win, app, (1500, 900), shot_path)
        family_paths[label] = str(shot_path)

    summary = {
        "album_dir": str(album_dir),
        "screenshots": {
            "normal": str(normal_path),
            "fullscreen": str(fullscreen_path),
            "small": str(small_path),
        },
        "songs": {
            "song_a": song_a,
            "song_b": song_b,
        },
        "typography_pt": {
            "normal": normal_fonts,
            "fullscreen": fullscreen_fonts,
            "small": small_fonts,
        },
        "background_showcase": {
            "targets": TARGET_FAMILIES,
            "picked": family_showcase,
            "screenshots": family_paths,
        },
    }

    summary_path = OUT_DIR / "showcase_summary.json"
    summary_path.write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(summary, indent=2, ensure_ascii=False))

    win.close()
    app.quit()


if __name__ == "__main__":
    main()
