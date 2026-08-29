import os
import sys
import time
import json
import numpy as np
from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QImage, QPainter

from app.analysis.features import (
    FrameFeatureSequence,
    EventFeatureSet,
    GlobalFeatureSet,
    FeatureCache,
    TrackAnalysisMetadata,
)
from app.dynamics.context import build_dynamics_bundle
from app.visual.renderer import VisualizerRenderer
from app.visual_gpu.viewport import VisualizerViewport


def make_bench_bundle():
    n_frames = 600
    times = np.arange(n_frames) / 60.0
    fm = np.zeros((n_frames, FrameFeatureSequence.N_FEATURES))
    fm[:, FrameFeatureSequence.F_RMS] = 0.6
    fm[:, FrameFeatureSequence.F_BAND_BASS] = 0.5
    fm[:, FrameFeatureSequence.F_BAND_MID] = 0.4
    fm[:, FrameFeatureSequence.F_BAND_HIGH] = 0.3

    seq = FrameFeatureSequence(times=times, frame_rate=60.0, features=fm)
    events = EventFeatureSet(
        beat_positions=np.arange(1.0, 10.0, 1.0),
        beat_strengths=np.full(9, 0.9),
        beat_confidence=0.9,
        onset_positions=np.arange(0.5, 10.0, 1.0),
        onset_strengths=np.full(10, 0.85),
    )
    meta = TrackAnalysisMetadata(
        file_path="bench.flac",
        file_hash="bench_hash_profile_99",
        cache_version="v6",
        duration=10.0,
        sample_rate=44100,
        analysis_timestamp=0.0,
    )
    cache = FeatureCache(
        metadata=meta,
        frame_seq=seq,
        events=events,
        windows=None,
        sections=None,
        semantics=None,
        globals_set=GlobalFeatureSet.compute_defaults(),
    )
    return build_dynamics_bundle(cache), cache


def main():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])

    bundle, cache = make_bench_bundle()

    renderer = VisualizerRenderer()
    renderer.resize(1280, 720)
    renderer.scene.load_track_features(cache.globals)
    renderer.scene.set_dynamics_bundle(bundle)

    # Layer wall-time metrics
    layer_timings = {
        "background": [],
        "atmosphere": [],
        "harmonic": [],
        "structure": [],
        "core": [],
        "lattice": [],
        "particles": [],
        "hud": [],
    }

    def profile_layer(layer_key, draw_fn, *args):
        t0 = time.perf_counter()
        draw_fn(*args)
        dt = (time.perf_counter() - t0) * 1000.0
        layer_timings[layer_key].append(dt)

    cpu_frame_times = []
    w, h = 1280.0, 720.0
    cx, cy = w / 2.0, h / 2.0

    # 1. Profile CPU path advancing scene to next frame for each sample
    for idx in range(60):
        t_frame = idx * (1.0 / 60.0)
        renderer.scene.update(cache.get_frame_at_time(t_frame), is_playing=True, width=1280, height=720, dt=1/60.0)

        img = QImage(1280, 720, QImage.Format.Format_RGBA8888)
        painter = QPainter(img)

        t_start_frame = time.perf_counter()
        profile_layer("background", renderer._draw_background_layer, painter, w, h, cx, cy)
        profile_layer("atmosphere", renderer._draw_atmosphere_layer, painter, w, h, cx, cy)
        profile_layer("harmonic", renderer._draw_harmonic_shell_layer, painter, cx, cy, w, h)
        profile_layer("structure", renderer._draw_generative_structure, painter, cx, cy, w, h)
        profile_layer("core", renderer._draw_energy_core_layer, painter, cx, cy, w, h)
        profile_layer("lattice", renderer._draw_transient_lattice_layer, painter, cx, cy, w, h)
        profile_layer("particles", renderer._draw_particles_layer, painter, w, h)
        profile_layer("hud", renderer._draw_huds, painter, w, h)
        painter.end()

        dt_total = (time.perf_counter() - t_start_frame) * 1000.0
        cpu_frame_times.append(dt_total)

    # 2. Viewport Composite Profile
    viewport = VisualizerViewport()
    viewport.resize(1280, 720)
    viewport.set_scene(renderer.scene)

    viewport_times = []
    for idx in range(60):
        t_frame = idx * (1.0 / 60.0)
        renderer.scene.update(cache.get_frame_at_time(t_frame), is_playing=True, width=1280, height=720, dt=1/60.0)
        t0 = time.perf_counter()
        img = viewport.render_to_image(1280, 720)
        dt = (time.perf_counter() - t0) * 1000.0
        viewport_times.append(dt)

    layer_summary = {}
    for k, v in layer_timings.items():
        layer_summary[k] = {
            "median_ms": round(float(np.median(v)), 3),
            "p95_ms": round(float(np.percentile(v, 95)), 3),
        }

    report = {
        "environment": {
            "os": sys.platform,
            "resolution": "1280x720",
            "samples": 60,
            "note": "Offscreen QImage and Viewport Composite benchmark timings. Does NOT represent hardware VSync or GPU screen refresh.",
        },
        "cpu_offscreen": {
            "median_ms": round(float(np.median(cpu_frame_times)), 2),
            "p95_ms": round(float(np.percentile(cpu_frame_times, 95)), 2),
            "max_fps": round(1000.0 / float(np.median(cpu_frame_times)), 1),
        },
        "viewport_composite": {
            "median_ms": round(float(np.median(viewport_times)), 2),
            "p95_ms": round(float(np.percentile(viewport_times, 95)), 2),
            "max_fps": round(1000.0 / float(np.median(viewport_times)), 1),
        },
        "layer_breakdown": layer_summary,
    }

    out_dir = r"d:\Agent\Stormy-Pulse\artifacts\performance"
    os.makedirs(out_dir, exist_ok=True)
    json_path = os.path.join(out_dir, "profile.json")

    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2)

    print(f"[Profiler Script] Profile JSON saved to {json_path}")
    print(f"  CPU Offscreen: {report['cpu_offscreen']['median_ms']} ms (Max {report['cpu_offscreen']['max_fps']} FPS)")
    print(f"  Viewport Composite: {report['viewport_composite']['median_ms']} ms (Max {report['viewport_composite']['max_fps']} FPS)")


if __name__ == "__main__":
    main()
