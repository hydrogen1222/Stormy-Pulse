import os
import sys
import numpy as np
from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QImage, QPainter, QColor, QFont

from app.analysis.extractor import FeatureExtractor
from app.dynamics.context import build_dynamics_bundle
from app.visual.renderer import VisualizerRenderer
from app.visual.scene import Scene
from app.analysis.features import (
    FrameFeatureSequence,
    EventFeatureSet,
    GlobalFeatureSet,
    FeatureCache,
    TrackAnalysisMetadata,
)


def make_archetype_bundle(structure_type: str, file_hash: str):
    n_frames = 300
    times = np.arange(n_frames) / 60.0
    fm = np.zeros((n_frames, FrameFeatureSequence.N_FEATURES))
    fm[:, FrameFeatureSequence.F_RMS] = 0.6
    fm[:, FrameFeatureSequence.F_BAND_BASS] = 0.5
    fm[:, FrameFeatureSequence.F_BAND_MID] = 0.4
    fm[:, FrameFeatureSequence.F_BAND_HIGH] = 0.3
    fm[:, FrameFeatureSequence.F_CENTROID] = 0.4
    fm[:, FrameFeatureSequence.F_FLATNESS] = 0.08

    seq = FrameFeatureSequence(times=times, frame_rate=60.0, features=fm)
    events = EventFeatureSet(
        beat_positions=np.arange(1.0, 5.0, 1.0),
        beat_strengths=np.full(4, 0.9),
        beat_confidence=0.9,
        onset_positions=np.arange(0.5, 5.0, 1.0),
        onset_strengths=np.full(5, 0.85),
    )
    meta = TrackAnalysisMetadata(
        file_path=f"arch_{structure_type}.flac",
        file_hash=file_hash,
        cache_version="v6",
        duration=5.0,
        sample_rate=44100,
        analysis_timestamp=0.0,
    )
    globals_set = GlobalFeatureSet.compute_defaults()
    globals_set.structure_type = structure_type

    cache = FeatureCache(
        metadata=meta,
        frame_seq=seq,
        events=events,
        windows=None,
        sections=None,
        semantics=None,
        globals_set=globals_set,
    )
    return build_dynamics_bundle(cache), cache


def main():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])

    base_dir = r"d:\Agent\Stormy-Pulse"
    out_dir = r"d:\Agent\Stormy-Pulse\artifacts\visual_review"
    os.makedirs(out_dir, exist_ok=True)

    items = []

    # 1. Four Synthetic Archetypes
    archetypes = ["pulse", "vortex", "reactor", "organic"]
    for arch in archetypes:
        bundle, cache = make_archetype_bundle(arch, f"hash_arch_{arch}_seed99")
        renderer = VisualizerRenderer()
        renderer.resize(1280, 720)
        renderer.scene.load_track_features(cache.globals)
        renderer.scene.set_dynamics_bundle(bundle)
        renderer.set_track_info(f"Archetype: {arch.upper()}", "Synthetic Test Generator", file_hash=f"hash_arch_{arch}_seed99")
        renderer.title_alpha = 1.0

        # Advance scene 1.0s past active beat
        for t in np.arange(0.0, 2.0, 1/60.0):
            renderer.scene.update(cache.get_frame_at_time(t), is_playing=True, width=1280, height=720, dt=1/60.0)

        renderer.title_alpha = 1.0
        img = renderer.render_to_image(1280, 720)
        file_name = f"archetype_{arch}.png"
        path = os.path.join(out_dir, file_name)
        img.save(path)

        dna = renderer.scene.theme
        items.append({
            "title": f"Archetype {arch.upper()}",
            "file_name": file_name,
            "path": path,
            "image": img,
            "structure": dna.structure_type,
            "palette": dna.palette_family,
            "timestamp": "2.0s",
        })
        print(f"[Review Script] Archetype {arch}: struct={dna.structure_type}, palette={dna.palette_family}")

    # 2. Three Real FLAC Tracks
    real_tracks = [
        ("岡村孝子 - 輝き_other.flac", 15.0),
        ("岡村孝子 - 白い夏_other.flac", 30.0),
        ("岡村孝子 - TODAY_other.flac", 45.0),
    ]

    extractor = FeatureExtractor()

    for rel_path, timestamp in real_tracks:
        full_path = os.path.join(base_dir, rel_path)
        if not os.path.exists(full_path):
            print(f"[ERROR] Real track not found: {full_path}")
            continue

        cache = extractor.extract(full_path)
        if cache is None:
            print(f"[ERROR] Failed to extract features for {full_path}")
            continue
        bundle = build_dynamics_bundle(cache)

        renderer = VisualizerRenderer()
        renderer.resize(1280, 720)
        renderer.scene.load_track_features(cache.globals)
        renderer.scene.set_dynamics_bundle(bundle)
        title = os.path.splitext(os.path.basename(rel_path))[0]
        renderer.set_track_info(title, "岡村孝子", file_hash=cache.metadata.file_hash)

        # Fast seek to target timestamp, then advance 0.5s to establish full active state
        renderer.scene.seek_interactive(timestamp, width=1280, height=720)
        for dt_step in range(30):
            t_curr = timestamp + dt_step * (1.0 / 60.0)
            renderer.scene.update(cache.get_frame_at_time(t_curr), is_playing=True, width=1280, height=720, dt=1/60.0)

        renderer.title_alpha = 1.0
        img = renderer.render_to_image(1280, 720)

        clean_name = title.replace(" ", "_").replace("-", "_")
        file_name = f"real_{clean_name}.png"
        path = os.path.join(out_dir, file_name)
        img.save(path)

        dna = renderer.scene.theme
        items.append({
            "title": title,
            "file_name": file_name,
            "path": path,
            "image": img,
            "structure": dna.structure_type,
            "palette": dna.palette_family,
            "timestamp": f"{timestamp:.1f}s",
        })
        print(f"[Review Script] Real Track '{title}': struct={dna.structure_type}, palette={dna.palette_family}, timestamp={timestamp}s")

    # 3. Build 7-Image Contact Sheet
    cell_w, cell_h = 640, 360
    cols = 3
    rows = int(np.ceil(len(items) / cols))
    sheet_w = cols * cell_w
    sheet_h = rows * cell_h + 60

    sheet = QImage(sheet_w, sheet_h, QImage.Format.Format_RGBA8888)
    sheet.fill(QColor(10, 15, 26))

    painter = QPainter(sheet)
    font_header = QFont("Sans-Serif", 16, QFont.Weight.Bold)
    font_sub = QFont("Sans-Serif", 10)

    painter.setFont(font_header)
    painter.setPen(QColor(240, 246, 255))
    painter.drawText(20, 40, "STORMY-PULSE V2 - VISUAL REVIEW CONTACT SHEET (7 SAMPLES)")

    for idx, item in enumerate(items):
        r = idx // cols
        c = idx % cols
        x = c * cell_w
        y = r * cell_h + 60

        scaled_img = item["image"].scaled(cell_w - 20, cell_h - 40)
        painter.drawImage(x + 10, y + 10, scaled_img)

        # Label overlay with actual runtime structure & palette family
        painter.setFont(font_sub)
        painter.setPen(QColor(255, 255, 255))
        label_text = f"{item['title']} | Struct: {item['structure'].upper()} | Pal: {item['palette']} | {item['timestamp']}"
        painter.drawText(x + 15, y + cell_h - 10, label_text)

    painter.end()

    sheet_path = os.path.join(out_dir, "contact_sheet.png")
    sheet.save(sheet_path)
    print(f"[Review Script] Contact Sheet saved to {sheet_path}")


if __name__ == "__main__":
    main()
