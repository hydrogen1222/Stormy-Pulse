"""
Main window for the music visualizer.
"""
import os
import time
from pathlib import Path
from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QGridLayout,
    QLabel,
    QFrame,
    QFileDialog,
    QStackedWidget,
)
from PySide6.QtCore import Qt, QTimer, Signal, QThread, QObject
from PySide6.QtGui import QFont, QPixmap

from ..core import AudioPlayer, MusicLibrary
from ..core.lyrics import parse_lrc_file
from ..analysis import VisualizationSync
from ..export import VideoExportCancelled, VideoExportError, VideoExportOptions, VideoExporter
from ..visual import VisualizerRenderer
try:
    from ..visual_gpu import VisualizerViewport
except Exception as exc:
    VisualizerViewport = None
    print(f"[MainWindow] GPU renderer unavailable: {exc}")
from .player_controls import PlayerControls
from .playlist_panel import PlaylistPanel
from ..config.settings import settings


class AnalysisWorker(QObject):
    """Worker for background feature extraction."""
    finished = Signal(object)
    progress = Signal(int, str)
    error = Signal(str)

    def __init__(self, sync_manager, file_path):
        super().__init__()
        self.sync_manager = sync_manager
        self.file_path = file_path

    def run(self):
        """Run extraction in background thread."""
        try:
            # We use VisualizationSync.load_track which handles both extraction and caching
            success = self.sync_manager.load_track(
                self.file_path, 
                lambda c, t, m: self.progress.emit(int(c/t*100) if t > 0 else 0, m)
            )
            
            if success:
                features = self.sync_manager.feature_cache
                self.finished.emit(features)
            else:
                self.error.emit("特征提取失败")
        except Exception as e:
            self.error.emit(str(e))


class MainWindow(QWidget):
    """Main application window."""

    def __init__(self):
        super().__init__()
        self.setWindowTitle("音乐可视化播放器")
        self.setMinimumSize(1080, 720)
        self.setStyleSheet("background: #0a1320;")

        # Core components
        self.settings = settings
        self.audio_player = AudioPlayer()
        self.music_library = MusicLibrary()
        self.visualization_sync = VisualizationSync()
        
        # Threading for analysis
        self._analysis_thread = None
        self._analysis_worker = None
        self._is_loading_track = False
        self._gpu_available = VisualizerViewport is not None
        self._render_backend = "cpu"

        # Debug tracking
        self._last_update_time = time.time()
        self._update_count = 0
        self._position_callback_count = 0

        # UI components
        self._setup_ui()

        # Connect signals
        self._connect_signals()

        # Start visualization
        self.visualizer.start()

        # Update timer - this drives scene updates
        self.update_timer = QTimer()
        self.update_timer.setTimerType(Qt.TimerType.PreciseTimer)
        self.update_timer.timeout.connect(self._on_update)
        
        target_fps = self.settings.get("fps", 60)
        interval = self._configure_update_timer(target_fps)
        self.visualizer.set_target_fps(target_fps)
        
        print(f"[MainWindow] Update timer started ({interval}ms interval for {target_fps} FPS)")

    def _setup_ui(self):
        """Setup the UI layout."""
        main_layout = QHBoxLayout(self)
        main_layout.setContentsMargins(18, 18, 18, 18)
        main_layout.setSpacing(16)

        # Left panel - Playlist
        self.playlist_panel = PlaylistPanel()
        self.playlist_panel.setFixedWidth(300)
        main_layout.addWidget(self.playlist_panel)

        # Right panel - Main content
        right_panel = QVBoxLayout()
        right_panel.setSpacing(12)

        # Visualization area
        self.cpu_visualizer = VisualizerRenderer()
        self.gpu_visualizer = VisualizerViewport() if self._gpu_available else None
        self.visualizer_stack = QStackedWidget()
        self.visualizer_stack.setMinimumHeight(420)
        self.visualizer_stack.addWidget(self.cpu_visualizer)
        if self.gpu_visualizer is not None:
            self.visualizer_stack.addWidget(self.gpu_visualizer)
        self._apply_visualizer_style(self.cpu_visualizer)
        if self.gpu_visualizer is not None:
            self._apply_visualizer_style(self.gpu_visualizer)
        self.visualizer = self.cpu_visualizer
        right_panel.addWidget(self.visualizer_stack, 1)

        # Track info
        self.track_info = QFrame()
        self.track_info.setObjectName("trackInfo")
        self.track_info.setStyleSheet("""
            #trackInfo {
                background: rgba(22, 22, 42, 180);
                border: 1px solid rgba(80, 80, 120, 100);
                border-radius: 12px;
            }
        """)
        # We handle padding with layout margins instead of CSS padding
        track_layout = QGridLayout(self.track_info)
        track_layout.setContentsMargins(12, 12, 12, 12)
        track_layout.setSpacing(8)

        # Cover art
        self.cover_label = QLabel()
        self.cover_label.setFixedSize(80, 80)
        self.cover_label.setStyleSheet("""
            background: #1a1a2e;
            border-radius: 4px;
        """)
        self.cover_label.setText("🎵")
        self.cover_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.cover_label.setFont(QFont("", 24))
        track_layout.addWidget(self.cover_label, 0, 0, 2, 1)

        # Track title
        self.title_label = QLabel("未加载音乐")
        self.title_label.setFont(QFont("Microsoft YaHei", 14, QFont.Weight.Bold))
        self.title_label.setStyleSheet("color: white;")
        track_layout.addWidget(self.title_label, 0, 1)

        # Artist/Album
        self.artist_label = QLabel("请选择音乐文件播放")
        self.artist_label.setFont(QFont("Microsoft YaHei", 11))
        self.artist_label.setStyleSheet("color: #8888aa;")
        track_layout.addWidget(self.artist_label, 1, 1)
        
        # Edit Info Button
        from PySide6.QtWidgets import QPushButton
        self.edit_btn = QPushButton("编辑")
        self.edit_btn.setFixedSize(50, 26)
        self.edit_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.edit_btn.setStyleSheet("""
            QPushButton {
                background-color: #4a4a6a;
                color: #ffffff;
                border: 1px solid #7a7a9a;
                border-radius: 4px;
                font-family: "Microsoft YaHei";
                font-size: 12px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #5a5a8a;
                border: 1px solid #aaaaaa;
            }
            QPushButton:pressed {
                background-color: #2a2a4a;
            }
        """)
        self.edit_btn.clicked.connect(self._on_edit_info)

        self.lyrics_btn = QPushButton("LRC")
        self.lyrics_btn.setFixedSize(50, 26)
        self.lyrics_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.lyrics_btn.setToolTip("Load an external .lrc lyrics file")
        self.lyrics_btn.setStyleSheet("""
            QPushButton {
                background-color: #304058;
                color: #ffffff;
                border: 1px solid #6680a8;
                border-radius: 4px;
                font-family: "Microsoft YaHei";
                font-size: 12px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #3a5274;
                border: 1px solid #9bb8e0;
            }
            QPushButton:pressed {
                background-color: #203048;
            }
        """)
        self.lyrics_btn.clicked.connect(self._on_load_lyrics)

        action_box = QVBoxLayout()
        action_box.setContentsMargins(0, 0, 0, 0)
        action_box.setSpacing(6)
        action_box.addWidget(self.edit_btn)
        action_box.addWidget(self.lyrics_btn)
        track_layout.addLayout(action_box, 0, 2, 2, 1, Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)

        # Analysis status
        self.status_label = QLabel("状态: 等待加载音乐")
        self.status_label.setFont(QFont("Consolas", 9))
        self.status_label.setStyleSheet("color: #666688;")
        track_layout.addWidget(self.status_label, 2, 1)

        right_panel.addWidget(self.track_info)

        # Player controls
        self.player_controls = PlayerControls()
        self.player_controls.set_enabled(False)
        right_panel.addWidget(self.player_controls)
        self._set_render_backend("cpu", persist=True)

        main_layout.addLayout(right_panel, 1)

        print(f"[MainWindow] UI setup complete. Visualizer widget: {self.visualizer}")
        print(f"[MainWindow] Visualizer size: {self.visualizer.width()}x{self.visualizer.height()}")

    def _apply_visualizer_style(self, widget):
        widget.setMinimumHeight(420)
        widget.setStyleSheet("""
            background: qlineargradient(
                x1: 0, y1: 0, x2: 1, y2: 1,
                stop: 0 rgba(9, 18, 30, 255),
                stop: 0.55 rgba(13, 27, 44, 255),
                stop: 1 rgba(10, 24, 40, 255)
            );
            border: 1px solid rgba(92, 148, 204, 84);
            border-radius: 14px;
        """)

    def _set_render_backend(self, backend: str, persist: bool = True):
        """Switch the live visualizer while preserving scene and playback state."""
        requested = "gpu" if str(backend).lower() == "gpu" else "cpu"
        if requested == "gpu" and not self._gpu_available:
            requested = "cpu"

        old_visualizer = self.visualizer
        new_visualizer = self.gpu_visualizer if requested == "gpu" else self.cpu_visualizer
        if new_visualizer is None:
            new_visualizer = self.cpu_visualizer
            requested = "cpu"

        if new_visualizer is not old_visualizer:
            scene = old_visualizer.scene
            if hasattr(new_visualizer, "set_scene"):
                new_visualizer.set_scene(scene)
            else:
                new_visualizer.scene = scene
                new_visualizer._layout_state = {}
                new_visualizer._layout_cache_key = None

            current_track = self.music_library.get_current_track()
            title = getattr(old_visualizer, "track_title", "") or (
                current_track.metadata.title if current_track else ""
            )
            artist = getattr(old_visualizer, "track_artist", "") or (
                current_track.metadata.artist if current_track else ""
            )
            lyrics = getattr(old_visualizer, "track_lyrics", None)
            if lyrics is None and current_track:
                lyrics = current_track.load_lyrics()

            if hasattr(new_visualizer, "set_track_info"):
                new_visualizer.set_track_info(title, artist)
            if hasattr(new_visualizer, "set_lyrics"):
                new_visualizer.set_lyrics(lyrics)
            if hasattr(new_visualizer, "set_playback_position"):
                new_visualizer.set_playback_position(getattr(old_visualizer, "playback_position", 0.0))
            new_visualizer.set_target_fps(self.settings.get("fps", 60))
            self.visualizer = new_visualizer
            self.visualizer_stack.setCurrentWidget(new_visualizer)

        self._render_backend = requested
        self.player_controls.set_render_backend(requested, self._gpu_available)
        if persist:
            self.settings.set("render_backend", requested)
        self.visualizer.update()
        print(f"[MainWindow] Render backend: {requested.upper()}")

    def _connect_signals(self):
        """Connect signals."""
        # Playlist signals
        self.playlist_panel.add_files_requested.connect(self._on_add_files)
        self.playlist_panel.add_folder_requested.connect(self._on_add_folder)
        self.playlist_panel.track_selected.connect(self._on_track_selected)

        # Player control signals
        self.player_controls.play_clicked.connect(self._on_play)
        self.player_controls.pause_clicked.connect(self._on_pause)
        self.player_controls.stop_clicked.connect(self._on_stop)
        self.player_controls.previous_clicked.connect(self._on_previous)
        self.player_controls.next_clicked.connect(self._on_next)
        self.player_controls.seek_requested.connect(self._on_seek)
        self.player_controls.volume_changed.connect(self._on_volume_changed)
        self.player_controls.settings_clicked.connect(self._on_settings_clicked)
        self.player_controls.export_clicked.connect(self._on_export_video_clicked)
        self.player_controls.render_backend_changed.connect(self._set_render_backend)

        # Audio player signals
        self.audio_player.position_changed.connect(self._on_position_changed)
        self.audio_player.duration_changed.connect(self._on_duration_changed)
        self.audio_player.end_of_track.connect(self._on_end_of_track)
        self.audio_player.playback_state_changed.connect(self._on_playback_state_changed)

        print("[MainWindow] All signals connected")

    def _configure_update_timer(self, fps: int) -> int:
        """Apply the requested update cadence to the render timer."""
        if fps <= 0:
            self.update_timer.start(0)
            return 0

        interval = max(1, int(round(1000.0 / fps)))
        self.update_timer.start(interval)
        return interval

    def _on_add_files(self):
        """Handle add files."""
        files, _ = QFileDialog.getOpenFileNames(
            self,
            "选择音乐文件",
            "",
            "音频文件 (*.mp3 *.flac *.wav *.m4a *.ogg);;所有文件 (*.*)",
        )

        print(f"[MainWindow] Files selected: {len(files)}")

        for file_path in files:
            track = self.music_library.add_track(file_path)
            if track:
                self.playlist_panel.add_track(
                    track.metadata.title,
                    track.metadata.artist,
                    track.metadata.album,
                    track.metadata.duration,
                )
                print(f"[MainWindow] Added track: {track.metadata.title}")

        if files:
            # We don't call _load_track(0) here because playlist_panel will 
            # trigger currentRowChanged(0) when the first item is added, 
            # which leads to _on_track_selected(0) -> _load_track(0).
            # If no selection happens, we can force it.
            if self.playlist_panel.get_current_row() < 0:
                self._load_track(0)

    def _on_add_folder(self, folder: str):
        """Handle add folder."""
        count = self.music_library.add_directory(folder)
        print(f"[MainWindow] Folder added: {folder}, found {count} tracks")

        for track in self.music_library.tracks[-count:]:
            self.playlist_panel.add_track(
                track.metadata.title,
                track.metadata.artist,
                track.metadata.album,
                track.metadata.duration,
            )

        if count > 0 and not self.audio_player.current_track:
            self.music_library.set_current_index(len(self.music_library.tracks) - count)
            self._load_track(len(self.music_library.tracks) - count)

    def _on_track_selected(self, index: int):
        """Handle track selection."""
        print(f"[MainWindow] Track selected: index={index}")
        self._load_track(index)

    def _load_track(self, index: int):
        """Load a track by index with complete reset."""
        if self._is_loading_track:
            return
        if not 0 <= index < self.music_library.get_track_count():
            return

        self._is_loading_track = True
        try:
            track = self.music_library.tracks[index]
            self.music_library.set_current_index(index)
            self.playlist_panel.set_current_row(index)

            print(f"\n[SwitchTrack] --- START: {track.metadata.title} ---")
            print(f"[SwitchTrack] Path: {track.metadata.file_path}")
            
            # Reset visual and sync states
            self.visualization_sync.reset()
            self.visualizer.reset()
            
            # Set track info for HUD
            if hasattr(self.visualizer, 'set_track_info'):
                self.visualizer.set_track_info(track.metadata.title, track.metadata.artist)
            if hasattr(self.visualizer, "set_lyrics"):
                self.visualizer.set_lyrics(track.load_lyrics())

            # Update UI info
            self.title_label.setText(track.metadata.title)
            self.artist_label.setText(f"{track.metadata.artist} - {track.metadata.album}")
            
            # Check cache explicitly for logging
            cache_path = self.visualization_sync.cache_manager.get_cache_path(track.metadata.file_path)
            has_cache = cache_path.exists()
            print(f"[SwitchTrack] Cache: {'HIT' if has_cache else 'MISS'}")
            if has_cache:
                print(f"[SwitchTrack] CacheKey: {cache_path.name}")
                
            self.status_label.setText(f"状态: {'加载中...' if has_cache else '正在分析... ' + track.metadata.title}")

            # Load cover
            if track.metadata.cover_art:
                try:
                    pixmap = QPixmap()
                    pixmap.loadFromData(track.metadata.cover_art)
                    self.cover_label.setPixmap(
                        pixmap.scaled(80, 80, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
                    )
                except Exception as e:
                    print(f"[SwitchTrack] Cover error: {e}")
                    self.cover_label.setText("🎵")
            else:
                self.cover_label.setText("🎵")

            # Prepare player
            self.audio_player.load_track(track)
            self.player_controls.set_enabled(True)
            self.player_controls.set_duration(track.metadata.duration)

            # Background analysis
            try:
                if self._analysis_thread and self._analysis_thread.isRunning():
                    self._analysis_thread.terminate()
                    self._analysis_thread.wait()
            except RuntimeError:
                pass # Thread was already deleted

            self._analysis_thread = QThread()
            self._analysis_worker = AnalysisWorker(self.visualization_sync, track.metadata.file_path)
            self._analysis_worker.moveToThread(self._analysis_thread)

            # Cleanup references to avoid RuntimeError
            def cleanup():
                self._analysis_thread = None
                self._analysis_worker = None

            self._analysis_thread.started.connect(self._analysis_worker.run)
            self._analysis_worker.finished.connect(self._on_analysis_finished)
            self._analysis_worker.progress.connect(self._on_analysis_progress)
            self._analysis_worker.error.connect(self._on_analysis_error)

            self._analysis_worker.finished.connect(self._analysis_thread.quit)
            self._analysis_worker.finished.connect(self._analysis_worker.deleteLater)
            self._analysis_thread.finished.connect(self._analysis_thread.deleteLater)
            self._analysis_thread.finished.connect(cleanup)

            self._analysis_thread.start()
        finally:
            self._is_loading_track = False
    def _on_analysis_progress(self, percent, message):
        """Update analysis progress in UI."""
        self.status_label.setText(f"分析中... {percent}% ({message})")

    def _on_analysis_finished(self, features):
        """Handle analysis completion and sync visualization."""
        if features:
            f = features.globals
            s = features.semantics
            sec = features.sections
            print("\n" + "="*60)
            print(f"[Level 1-5 Analysis Success] Cache Version: {features.metadata.cache_version}")
            print(f"[Metadata] Path: {features.metadata.file_path}")
            print(f"[Events] Beats detected: {len(features.events.beat_positions)} | Onsets detected: {len(features.events.onset_positions)}")
            print(f"[L3 Windows] Length of 2s trend array: {len(features.windows.stats_2s['energy_trend'])}")
            print(f"[L4 Sections] Detected {len(sec.boundaries)-1} macro sections. Climax candidates: {len(sec.climax_candidates)}")
            print(f"[L5 Global] Tempo: {f.tempo:.1f} BPM | Dynamic Range: {f.dynamic_range:.2f}")
            print(f"[L5 Spectrum] Bass: {f.bass_ratio:.2f} | Mid: {f.mid_ratio:.2f} | High: {f.high_ratio:.2f} | Brightness: {f.brightness:.2f}")
            print(f"[L5 Semantics] Impact: {s.impact:.2f} | Pressure: {s.pressure:.2f} | Sparkle: {s.sparkle:.2f}")
            print(f"[L5 Semantics] Density: {s.density:.2f} | Tension: {s.tension:.2f} | Flow: {s.flow:.2f}")
            print(f"[DNA Priors] Palette: {f.palette_prior} | Structure: {f.structure_prior} | Motion: {f.motion_prior}")
            print("="*60 + "\n")
            
            # Reset sync with new cache
            self.visualization_sync.feature_cache = features
            
            # This triggers theme creation
            self.visualizer.scene.load_track_features(f)
            
            dna = self.visualizer.scene.theme
            print(f"[VisualDNA Binding] Structure: {dna.structure_type} | Detail: {dna.detail_style}")
            print(
                f"[VisualDNA Binding] PaletteFamily: {dna.palette_family}"
                + (
                    f" + {dna.palette_blend_family}({dna.palette_blend_ratio:.2f})"
                    if dna.palette_blend_ratio > 0
                    else ""
                )
                + f" | LegacyPaletteType: {dna.palette_type} | BaseHue: {dna.hue_base:.1f}"
            )
            bg_base = dna.get_color("background_base")
            bg_fog = dna.get_color("background_fog")
            bg_halo = dna.get_color("background_halo")
            print(
                "[VisualDNA Background] "
                f"base={bg_base[:3]} fog={bg_fog[:3]} halo={bg_halo[:3]}"
            )
            
            self.status_label.setText("分析完成")
        else:
            self.status_label.setText("分析失败: 无有效特征")

    def _on_analysis_error(self, error_msg):
        """Handle analysis error."""
        print(f"[MainWindow] Analysis error: {error_msg}")
        self.status_label.setText(f"分析失败: {error_msg}")

    def _on_load_lyrics(self):
        """Manually attach an external LRC file to the current track."""
        from PySide6.QtWidgets import QMessageBox

        track = self.audio_player.current_track or self.music_library.get_current_track()
        if not track:
            QMessageBox.warning(self, "No track", "Please load a track before adding lyrics.")
            return

        path, _ = QFileDialog.getOpenFileName(
            self,
            "Load LRC lyrics",
            str(Path(track.metadata.file_path).parent),
            "LRC lyrics (*.lrc);;All files (*.*)",
        )
        if not path:
            return

        lyrics = parse_lrc_file(path)
        if not lyrics or not lyrics.cues:
            QMessageBox.warning(self, "Invalid lyrics", "The selected file does not contain valid timed LRC lyrics.")
            return

        track.lyrics = lyrics
        track.lyrics_path = path
        self.settings.set("show_lyrics", True)
        for visualizer in (self.cpu_visualizer, self.gpu_visualizer):
            if visualizer is not None and hasattr(visualizer, "set_lyrics"):
                visualizer.set_lyrics(lyrics)
        self.status_label.setText(f"LRC loaded: {Path(path).name}")
        self.visualizer.update()

    def _on_edit_info(self):
        """Handle track metadata edit."""
        print("[MainWindow] Edit button clicked")
        if not self.audio_player.current_track:
            print("[MainWindow] No track currently loaded to edit")
            return
            
        from PySide6.QtWidgets import QDialog, QVBoxLayout, QLineEdit, QFormLayout, QDialogButtonBox
        
        track = self.audio_player.current_track
        print(f"[MainWindow] Editing track: {track.metadata.file_path}")
        
        dialog = QDialog(self)
        dialog.setWindowTitle("编辑歌曲信息")
        dialog.setStyleSheet("background: #16162a; color: white;")
        dialog.setFixedWidth(300)
        
        layout = QVBoxLayout(dialog)
        form = QFormLayout()
        
        title_edit = QLineEdit(track.metadata.title)
        artist_edit = QLineEdit(track.metadata.artist)
        
        form.addRow("歌曲名:", title_edit)
        form.addRow("艺术家:", artist_edit)
        layout.addLayout(form)
        
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        layout.addWidget(buttons)
        
        if dialog.exec():
            new_title = title_edit.text()
            new_artist = artist_edit.text()
            
            # Update track
            track.metadata.title = new_title
            track.metadata.artist = new_artist
            
            # Save override
            overrides = self.settings.get("metadata_overrides", {})
            overrides[track.metadata.file_path] = {
                "title": new_title,
                "artist": new_artist
            }
            self.settings.set("metadata_overrides", overrides)
            
            # Update UI
            self.title_label.setText(new_title)
            self.artist_label.setText(f"{new_artist} - {track.metadata.album}")
            
            if hasattr(self.visualizer, 'set_track_info'):
                self.visualizer.set_track_info(new_title, new_artist)
                
            # Update playlist item (rough approach)
            self.playlist_panel.update_current_track_info(new_title, new_artist)

    def _on_play(self):
        """Handle play."""
        print("[MainWindow] Play clicked")
        if self.audio_player.current_track:
            self.audio_player.play()
            self.player_controls.set_playing(True)
            print(f"[MainWindow] Playing: {self.audio_player.is_playing()}")
        else:
            print("[MainWindow] No track loaded, cannot play")

    def _on_pause(self):
        """Handle pause."""
        print("[MainWindow] Pause clicked")
        self.audio_player.pause()
        self.player_controls.set_playing(False)
        print(f"[MainWindow] Playing: {self.audio_player.is_playing()}")

    def _on_stop(self):
        """Handle stop."""
        print("[MainWindow] Stop clicked")
        self.audio_player.stop()
        self.player_controls.set_playing(False)
        self.player_controls.set_position(0)
        self.visualization_sync.seek_to(0)

    def _on_previous(self):
        """Handle previous."""
        print("[MainWindow] Previous clicked")
        track = self.music_library.previous_track()
        if track:
            self._load_track(self.music_library.current_index)

    def _on_next(self):
        """Handle next."""
        print("[MainWindow] Next clicked")
        track = self.music_library.next_track()
        if track:
            self._load_track(self.music_library.current_index)

    def _on_seek(self, position: float):
        """Handle seek."""
        print(f"[MainWindow] Seek to {position:.2f}s")
        self.audio_player.seek(int(position * 1000))
        self.visualization_sync.seek_to(position)

    def _on_volume_changed(self, volume: float):
        """Handle volume change."""
        self.audio_player.set_volume(volume)

    def _on_position_changed(self, position_ms: int):
        """Handle position change."""
        self._position_callback_count += 1
        position = position_ms / 1000.0
        self.player_controls.set_position(position)
        self.visualization_sync.seek_to(position)
        if hasattr(self.visualizer, "set_playback_position"):
            self.visualizer.set_playback_position(position)

        # Debug print every second
        if self._position_callback_count % 60 == 0:
            print(f"[MainWindow] position_changed: {position:.2f}s (callback #{self._position_callback_count})")

    def _on_duration_changed(self, duration_ms: int):
        """Handle duration change."""
        duration = duration_ms / 1000.0
        print(f"[MainWindow] Duration changed: {duration:.2f}s")
        self.player_controls.set_duration(duration)

    def _on_playback_state_changed(self, is_playing: bool):
        """Handle playback state change from Qt."""
        print(f"[MainWindow] playbackStateChanged signal: is_playing={is_playing}")
        print(f"[MainWindow] Qt player state: {self.audio_player._player.playbackState()}")

    def _on_end_of_track(self):
        """Handle end of track."""
        print("[MainWindow] End of track")
        self.player_controls.set_playing(False)
        self._on_next()

    def _on_settings_clicked(self):
        """Show settings dialog."""
        from PySide6.QtWidgets import QDialog, QVBoxLayout, QComboBox, QFormLayout, QDialogButtonBox, QCheckBox, QGroupBox, QFontComboBox, QDoubleSpinBox, QPushButton, QTabWidget, QScrollArea
        
        dialog = QDialog(self)
        dialog.setWindowTitle("引擎设置")
        dialog.resize(560, 520)
        dialog.setStyleSheet("background: #16162a; color: white;")
        
        layout = QVBoxLayout(dialog)
        tabs = QTabWidget()
        tabs.setStyleSheet("""
            QTabWidget::pane { border: 1px solid #3b4164; border-radius: 8px; }
            QTabBar::tab { background: #252942; color: #c8d1ff; padding: 7px 14px; border-top-left-radius: 6px; border-top-right-radius: 6px; }
            QTabBar::tab:selected { background: #3a4168; color: #ffffff; }
        """)
        layout.addWidget(tabs, 1)

        basic_page = QWidget()
        basic_layout = QVBoxLayout(basic_page)
        basic_layout.setContentsMargins(10, 10, 10, 10)
        basic_layout.setSpacing(10)

        hud_page = QWidget()
        hud_page_layout = QVBoxLayout(hud_page)
        hud_page_layout.setContentsMargins(10, 10, 10, 10)
        hud_page_layout.setSpacing(10)

        font_page = QWidget()
        font_page_layout = QVBoxLayout(font_page)
        font_page_layout.setContentsMargins(10, 10, 10, 10)
        font_page_layout.setSpacing(10)

        tune_page = QWidget()
        tune_page_layout = QVBoxLayout(tune_page)
        tune_page_layout.setContentsMargins(10, 10, 10, 10)
        tune_page_layout.setSpacing(10)
        tune_scroll = QScrollArea()
        tune_scroll.setWidgetResizable(True)
        tune_scroll.setFrameShape(QFrame.Shape.NoFrame)
        tune_scroll.setWidget(tune_page)

        tabs.addTab(basic_page, "Basic")
        tabs.addTab(hud_page, "HUD")
        tabs.addTab(font_page, "Fonts")
        tabs.addTab(tune_scroll, "Layout")
        
        # --- Performance Group ---
        perf_group = QGroupBox("性能与显示")
        perf_group.setStyleSheet("color: #aaaacc;")
        perf_layout = QFormLayout(perf_group)
        
        fps_combo = QComboBox()
        fps_options = ["60", "120", "144", "165", "No Limit"]
        fps_combo.addItems(fps_options)
        
        current_fps = self.settings.get("fps", 60)
        if current_fps == 0:
            fps_combo.setCurrentText("No Limit")
        else:
            fps_combo.setCurrentText(str(current_fps))
        
        perf_layout.addRow("目标帧率:", fps_combo)
        
        cb_fps = QCheckBox("显示 FPS 计数")
        cb_fps.setChecked(self.settings.get("show_fps", True))
        perf_layout.addRow("", cb_fps)

        canvas_ratio_combo = QComboBox()
        canvas_ratio_combo.addItems(["16:9", "9:16"])
        canvas_ratio_combo.setCurrentText(self.settings.get("visual_canvas_ratio", "16:9"))
        perf_layout.addRow("画布比例:", canvas_ratio_combo)
        
        render_backend_combo = QComboBox()
        render_backend_combo.addItem("CPU", "cpu")
        render_backend_combo.addItem("GPU", "gpu")
        if not self._gpu_available:
            render_backend_combo.setItemData(1, 0, Qt.ItemDataRole.UserRole - 1)
            render_backend_combo.setToolTip("GPU renderer is unavailable in this environment")
        render_backend_combo.setCurrentIndex(1 if self._render_backend == "gpu" and self._gpu_available else 0)
        perf_layout.addRow("Render:", render_backend_combo)

        basic_layout.addWidget(perf_group)
        basic_layout.addStretch()
        
        # --- HUD Group ---
        hud_group = QGroupBox("界面元素 (HUD)")
        hud_group.setStyleSheet("color: #aaaacc;")
        hud_layout = QFormLayout(hud_group)
        
        cb_top_title = QCheckBox("显示顶部歌曲名")
        cb_top_title.setChecked(self.settings.get("show_track_title", True))
        hud_layout.addRow("", cb_top_title)
        
        cb_left_hud = QCheckBox("显示左下角面板")
        cb_left_hud.setChecked(self.settings.get("show_left_hud", True))
        hud_layout.addRow("", cb_left_hud)
        
        cb_right_hud = QCheckBox("显示右下角监控")
        cb_right_hud.setChecked(self.settings.get("show_right_hud", True))
        hud_layout.addRow("", cb_right_hud)

        cb_lyrics = QCheckBox("显示右侧歌词")
        cb_lyrics.setChecked(self.settings.get("show_lyrics", False))
        hud_layout.addRow("", cb_lyrics)
        
        cb_dev_hud = QCheckBox("开发者模式 (DNA详情)")
        cb_dev_hud.setChecked(self.settings.get("show_dev_hud", False))
        hud_layout.addRow("", cb_dev_hud)

        hud_page_layout.addWidget(hud_group)
        hud_page_layout.addStretch()

        font_group = QGroupBox("字体")
        font_group.setStyleSheet("color: #aaaacc;")
        font_layout = QFormLayout(font_group)

        title_font_combo = QFontComboBox()
        title_font_combo.setCurrentFont(QFont(self.settings.get("title_font_family", "") or "Segoe UI"))
        font_layout.addRow("歌曲名:", title_font_combo)

        artist_font_combo = QFontComboBox()
        artist_font_combo.setCurrentFont(QFont(self.settings.get("artist_font_family", "") or "Segoe UI"))
        font_layout.addRow("艺术家:", artist_font_combo)

        lyric_original_font_combo = QFontComboBox()
        lyric_original_font_combo.setCurrentFont(
            QFont(
                self.settings.get("lyric_original_font_family", "")
                or self.settings.get("lyric_font_family", "")
                or "Microsoft YaHei UI"
            )
        )
        font_layout.addRow("原文歌词:", lyric_original_font_combo)

        lyric_translation_font_combo = QFontComboBox()
        lyric_translation_font_combo.setCurrentFont(
            QFont(
                self.settings.get("lyric_translation_font_family", "")
                or self.settings.get("lyric_font_family", "")
                or "Microsoft YaHei UI"
            )
        )
        font_layout.addRow("译文歌词:", lyric_translation_font_combo)

        font_page_layout.addWidget(font_group)
        font_page_layout.addStretch()

        tune_group = QGroupBox("Typography & Layout")
        tune_group.setStyleSheet("color: #aaaacc;")
        tune_layout = QFormLayout(tune_group)

        def _make_offset_spin(value: float) -> QDoubleSpinBox:
            spin = QDoubleSpinBox()
            spin.setRange(-50.0, 50.0)
            spin.setSingleStep(0.5)
            spin.setDecimals(1)
            spin.setSuffix("%")
            spin.setValue(float(value))
            return spin

        def _make_scale_spin(value: float) -> QDoubleSpinBox:
            spin = QDoubleSpinBox()
            spin.setRange(0.5, 2.2)
            spin.setSingleStep(0.05)
            spin.setDecimals(2)
            spin.setValue(float(value))
            return spin

        def _make_module_scale_spin(value: float) -> QDoubleSpinBox:
            spin = QDoubleSpinBox()
            spin.setRange(0.65, 1.85)
            spin.setSingleStep(0.05)
            spin.setDecimals(2)
            spin.setValue(float(value))
            return spin

        def _pair_widget(x_spin: QDoubleSpinBox, y_spin: QDoubleSpinBox) -> QWidget:
            row = QWidget()
            row_layout = QHBoxLayout(row)
            row_layout.setContentsMargins(0, 0, 0, 0)
            row_layout.setSpacing(6)
            row_layout.addWidget(QLabel("X"))
            row_layout.addWidget(x_spin)
            row_layout.addWidget(QLabel("Y"))
            row_layout.addWidget(y_spin)
            return row

        title_x_spin = _make_offset_spin(self.settings.get("layout_title_x", 0.0))
        title_y_spin = _make_offset_spin(self.settings.get("layout_title_y", 0.0))
        artist_x_spin = _make_offset_spin(self.settings.get("layout_artist_x", 0.0))
        artist_y_spin = _make_offset_spin(self.settings.get("layout_artist_y", 0.0))
        lyrics_x_spin = _make_offset_spin(self.settings.get("layout_lyrics_x", 0.0))
        lyrics_y_spin = _make_offset_spin(self.settings.get("layout_lyrics_y", 0.0))
        left_hud_x_spin = _make_offset_spin(self.settings.get("layout_left_hud_x", 0.0))
        left_hud_y_spin = _make_offset_spin(self.settings.get("layout_left_hud_y", 0.0))
        right_hud_x_spin = _make_offset_spin(self.settings.get("layout_right_hud_x", 0.0))
        right_hud_y_spin = _make_offset_spin(self.settings.get("layout_right_hud_y", 0.0))
        title_scale_spin = _make_scale_spin(self.settings.get("font_scale_title", 1.0))
        artist_scale_spin = _make_scale_spin(self.settings.get("font_scale_artist", 1.0))
        lyrics_scale_spin = _make_scale_spin(self.settings.get("font_scale_lyrics", 1.0))
        hud_scale_spin = _make_scale_spin(self.settings.get("font_scale_hud", 1.0))
        left_hud_font_scale_spin = _make_scale_spin(self.settings.get("font_scale_left_hud", 1.0))
        right_hud_font_scale_spin = _make_scale_spin(self.settings.get("font_scale_right_hud", 1.0))
        title_module_scale_spin = _make_module_scale_spin(self.settings.get("module_scale_title", 1.0))
        lyrics_module_scale_spin = _make_module_scale_spin(self.settings.get("module_scale_lyrics", 1.0))
        left_hud_module_scale_spin = _make_module_scale_spin(self.settings.get("module_scale_left_hud", 1.0))
        right_hud_module_scale_spin = _make_module_scale_spin(self.settings.get("module_scale_right_hud", 1.0))
        effect_module_scale_spin = _make_module_scale_spin(self.settings.get("module_scale_effect", 1.0))

        tune_layout.addRow("Song Offset:", _pair_widget(title_x_spin, title_y_spin))
        tune_layout.addRow("Artist Offset:", _pair_widget(artist_x_spin, artist_y_spin))
        tune_layout.addRow("Lyrics Offset:", _pair_widget(lyrics_x_spin, lyrics_y_spin))
        tune_layout.addRow("Left HUD Offset:", _pair_widget(left_hud_x_spin, left_hud_y_spin))
        tune_layout.addRow("Right HUD Offset:", _pair_widget(right_hud_x_spin, right_hud_y_spin))
        tune_layout.addRow("Song Font Scale:", title_scale_spin)
        tune_layout.addRow("Artist Font Scale:", artist_scale_spin)
        tune_layout.addRow("Lyrics Font Scale:", lyrics_scale_spin)
        tune_layout.addRow("HUD Font Scale (Global):", hud_scale_spin)
        tune_layout.addRow("Left HUD Font Scale:", left_hud_font_scale_spin)
        tune_layout.addRow("Right HUD Font Scale:", right_hud_font_scale_spin)
        tune_layout.addRow("Title Block Size:", title_module_scale_spin)
        tune_layout.addRow("Lyrics Block Size:", lyrics_module_scale_spin)
        tune_layout.addRow("Left HUD Block Size:", left_hud_module_scale_spin)
        tune_layout.addRow("Right HUD Block Size:", right_hud_module_scale_spin)
        tune_layout.addRow("Effect Core Size:", effect_module_scale_spin)

        reset_layout_btn = QPushButton("Reset Typography/Layout")
        reset_layout_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        reset_layout_btn.setStyleSheet(
            "QPushButton { background-color: #31314f; color: #d6dcff; border: 1px solid #4f5a78; border-radius: 6px; padding: 6px 10px; }"
            "QPushButton:hover { background-color: #3b4164; }"
            "QPushButton:pressed { background-color: #252942; }"
        )

        def _reset_typography_layout():
            for spin in (
                title_x_spin,
                title_y_spin,
                artist_x_spin,
                artist_y_spin,
                lyrics_x_spin,
                lyrics_y_spin,
                left_hud_x_spin,
                left_hud_y_spin,
                right_hud_x_spin,
                right_hud_y_spin,
            ):
                spin.setValue(0.0)
            for spin in (
                title_scale_spin,
                artist_scale_spin,
                lyrics_scale_spin,
                hud_scale_spin,
                left_hud_font_scale_spin,
                right_hud_font_scale_spin,
                title_module_scale_spin,
                lyrics_module_scale_spin,
                left_hud_module_scale_spin,
                right_hud_module_scale_spin,
                effect_module_scale_spin,
            ):
                spin.setValue(1.0)

        reset_layout_btn.clicked.connect(_reset_typography_layout)
        tune_layout.addRow("", reset_layout_btn)

        tune_page_layout.addWidget(tune_group)
        tune_page_layout.addStretch()

        settings_snapshot = dict(self.settings.data)
        backend_snapshot = self._render_backend
        applying_settings = {"value": False}

        def _selected_fps() -> int:
            selected = fps_combo.currentText()
            return 0 if selected == "No Limit" else int(selected)

        def _collect_settings() -> dict:
            selected_backend = render_backend_combo.currentData() or "cpu"
            return {
                "fps": _selected_fps(),
                "visual_canvas_ratio": canvas_ratio_combo.currentText(),
                "render_backend": selected_backend,
                "show_fps": cb_fps.isChecked(),
                "show_track_title": cb_top_title.isChecked(),
                "show_left_hud": cb_left_hud.isChecked(),
                "show_right_hud": cb_right_hud.isChecked(),
                "show_lyrics": cb_lyrics.isChecked(),
                "show_dev_hud": cb_dev_hud.isChecked(),
                "title_font_family": title_font_combo.currentFont().family(),
                "artist_font_family": artist_font_combo.currentFont().family(),
                "lyric_font_family": lyric_original_font_combo.currentFont().family(),
                "lyric_original_font_family": lyric_original_font_combo.currentFont().family(),
                "lyric_translation_font_family": lyric_translation_font_combo.currentFont().family(),
                "layout_title_x": float(title_x_spin.value()),
                "layout_title_y": float(title_y_spin.value()),
                "layout_artist_x": float(artist_x_spin.value()),
                "layout_artist_y": float(artist_y_spin.value()),
                "layout_lyrics_x": float(lyrics_x_spin.value()),
                "layout_lyrics_y": float(lyrics_y_spin.value()),
                "layout_left_hud_x": float(left_hud_x_spin.value()),
                "layout_left_hud_y": float(left_hud_y_spin.value()),
                "layout_right_hud_x": float(right_hud_x_spin.value()),
                "layout_right_hud_y": float(right_hud_y_spin.value()),
                "font_scale_title": float(title_scale_spin.value()),
                "font_scale_artist": float(artist_scale_spin.value()),
                "font_scale_lyrics": float(lyrics_scale_spin.value()),
                "font_scale_hud": float(hud_scale_spin.value()),
                "font_scale_left_hud": float(left_hud_font_scale_spin.value()),
                "font_scale_right_hud": float(right_hud_font_scale_spin.value()),
                "module_scale_title": float(title_module_scale_spin.value()),
                "module_scale_lyrics": float(lyrics_module_scale_spin.value()),
                "module_scale_left_hud": float(left_hud_module_scale_spin.value()),
                "module_scale_right_hud": float(right_hud_module_scale_spin.value()),
                "module_scale_effect": float(effect_module_scale_spin.value()),
            }

        def _refresh_visualizer_after_settings(new_values: dict):
            interval = self._configure_update_timer(int(new_values["fps"]))
            self.visualizer.set_target_fps(int(new_values["fps"]))
            self._set_render_backend(str(new_values["render_backend"]), persist=False)
            current_track = self.music_library.get_current_track()
            if new_values["show_lyrics"] and current_track and hasattr(self.visualizer, "set_lyrics"):
                self.visualizer.set_lyrics(current_track.load_lyrics())
            self.visualizer._layout_cache_key = None if hasattr(self.visualizer, "_layout_cache_key") else None
            self.visualizer.update()
            return interval

        def _apply_live_settings():
            if applying_settings["value"]:
                return
            new_values = _collect_settings()
            self.settings.data.update(new_values)
            self.settings.save()
            _refresh_visualizer_after_settings(new_values)

        def _restore_settings_snapshot():
            self.settings.data.clear()
            self.settings.data.update(settings_snapshot)
            self.settings.save()
            self._configure_update_timer(int(self.settings.get("fps", 60)))
            self._set_render_backend(backend_snapshot, persist=False)
            current_track = self.music_library.get_current_track()
            if self.settings.get("show_lyrics", False) and current_track and hasattr(self.visualizer, "set_lyrics"):
                self.visualizer.set_lyrics(current_track.load_lyrics())
            self.visualizer.update()

        live_widgets = [
            fps_combo,
            canvas_ratio_combo,
            render_backend_combo,
            cb_fps,
            cb_top_title,
            cb_left_hud,
            cb_right_hud,
            cb_lyrics,
            cb_dev_hud,
            title_font_combo,
            artist_font_combo,
            lyric_original_font_combo,
            lyric_translation_font_combo,
            title_x_spin,
            title_y_spin,
            artist_x_spin,
            artist_y_spin,
            lyrics_x_spin,
            lyrics_y_spin,
            left_hud_x_spin,
            left_hud_y_spin,
            right_hud_x_spin,
            right_hud_y_spin,
            title_scale_spin,
            artist_scale_spin,
            lyrics_scale_spin,
            hud_scale_spin,
            left_hud_font_scale_spin,
            right_hud_font_scale_spin,
            title_module_scale_spin,
            lyrics_module_scale_spin,
            left_hud_module_scale_spin,
            right_hud_module_scale_spin,
            effect_module_scale_spin,
        ]
        for widget in live_widgets:
            if isinstance(widget, QCheckBox):
                widget.toggled.connect(_apply_live_settings)
            elif isinstance(widget, QComboBox):
                widget.currentIndexChanged.connect(_apply_live_settings)
            elif isinstance(widget, QFontComboBox):
                widget.currentFontChanged.connect(_apply_live_settings)
            elif isinstance(widget, QDoubleSpinBox):
                widget.valueChanged.connect(_apply_live_settings)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        layout.addWidget(buttons)
        
        if dialog.exec():
            _apply_live_settings()
            print(
                f"[MainWindow] Settings accepted: FPS={self.settings.get('fps')}, "
                f"CanvasRatio={self.settings.get('visual_canvas_ratio')}, Render={self.settings.get('render_backend')}, "
                f"LeftHUD={self.settings.get('show_left_hud')}, RightHUD={self.settings.get('show_right_hud')}, "
                f"Lyrics={self.settings.get('show_lyrics')}"
            )
        else:
            _restore_settings_snapshot()

    def _get_feature_cache_for_track(self, track, progress_dialog=None):
        """Get analysis cache for export, extracting if necessary."""
        cache = self.visualization_sync.feature_cache
        if cache and cache.metadata.file_path == track.metadata.file_path:
            return cache

        def on_progress(current, total, message):
            if not progress_dialog:
                return
            ratio = 0 if total <= 0 else current / total
            progress_dialog.setLabelText(f"分析音频中: {message}")
            progress_dialog.setValue(min(int(ratio * 18), 18))
            from PySide6.QtWidgets import QApplication
            QApplication.processEvents()

        return self.visualization_sync.cache_manager.get_or_extract(track.metadata.file_path, on_progress)

    def _on_export_video_clicked(self):
        """Export the current visualizer scene to a video file."""
        from PySide6.QtWidgets import (
            QApplication,
            QCheckBox,
            QComboBox,
            QDialog,
            QDialogButtonBox,
            QFileDialog,
            QFormLayout,
            QGridLayout,
            QGroupBox,
            QHBoxLayout,
            QLabel,
            QLineEdit,
            QMessageBox,
            QProgressDialog,
            QPushButton,
            QSpinBox,
            QVBoxLayout,
        )

        track = self.audio_player.current_track or self.music_library.get_current_track()
        if not track:
            QMessageBox.warning(self, "无法导出", "请先加载一首歌曲再导出视频。")
            return

        dialog = QDialog(self)
        dialog.setWindowTitle("导出视频")
        dialog.setFixedWidth(520)
        dialog.setStyleSheet("background: #16162a; color: white;")
        layout = QVBoxLayout(dialog)

        desc = QLabel("导出会复用当前特效窗口的显示状态，包括标题、HUD、歌词和字体设置。")
        desc.setWordWrap(True)
        desc.setStyleSheet("color: #aab4d8;")
        layout.addWidget(desc)

        video_group = QGroupBox("视频参数")
        video_group.setStyleSheet("color: #aaaacc;")
        video_form = QFormLayout(video_group)

        resolution_widget = QWidget()
        resolution_layout = QHBoxLayout(resolution_widget)
        resolution_layout.setContentsMargins(0, 0, 0, 0)
        resolution_layout.setSpacing(8)
        aspect_ratio_combo = QComboBox()
        aspect_ratio_combo.addItems(["16:9", "9:16"])
        aspect_ratio_combo.setCurrentText(self.settings.get("visual_canvas_ratio", "16:9"))
        video_form.addRow("画幅比例:", aspect_ratio_combo)
        width_spin = QSpinBox()
        width_spin.setRange(640, 16384)
        width_spin.setSingleStep(2)
        width_spin.setValue(1920)
        height_spin = QSpinBox()
        height_spin.setRange(360, 16384)
        height_spin.setSingleStep(2)
        height_spin.setValue(1080)
        resolution_layout.addWidget(width_spin)
        resolution_layout.addWidget(QLabel("x"))
        resolution_layout.addWidget(height_spin)
        video_form.addRow("分辨率:", resolution_widget)

        sync_guard = {"value": False}

        def apply_aspect_defaults(ratio_key: str):
            sync_guard["value"] = True
            if ratio_key == "9:16":
                width_spin.setRange(360, 9216)
                height_spin.setRange(640, 16384)
                width_spin.setValue(1080)
                height_spin.setValue(1920)
            else:
                width_spin.setRange(640, 16384)
                height_spin.setRange(360, 9216)
                width_spin.setValue(1920)
                height_spin.setValue(1080)
            sync_guard["value"] = False

        def sync_height(width_value: int):
            if sync_guard["value"]:
                return
            sync_guard["value"] = True
            if aspect_ratio_combo.currentText() == "9:16":
                height_spin.setValue(max(height_spin.minimum(), ((width_value * 16) // 9) // 2 * 2))
            else:
                height_spin.setValue(max(height_spin.minimum(), ((width_value * 9) // 16) // 2 * 2))
            sync_guard["value"] = False

        def sync_width(height_value: int):
            if sync_guard["value"]:
                return
            sync_guard["value"] = True
            if aspect_ratio_combo.currentText() == "9:16":
                width_spin.setValue(max(width_spin.minimum(), ((height_value * 9) // 16) // 2 * 2))
            else:
                width_spin.setValue(max(width_spin.minimum(), ((height_value * 16) // 9) // 2 * 2))
            sync_guard["value"] = False

        width_spin.valueChanged.connect(sync_height)
        height_spin.valueChanged.connect(sync_width)
        aspect_ratio_combo.currentTextChanged.connect(apply_aspect_defaults)
        apply_aspect_defaults(aspect_ratio_combo.currentText())

        fps_spin = QSpinBox()
        fps_spin.setRange(1, 240)
        current_fps = self.settings.get("fps", 60)
        fps_spin.setValue(60 if current_fps == 0 else current_fps)
        video_form.addRow("FPS:", fps_spin)

        codec_combo = QComboBox()
        codec_combo.addItems([
            "libx264",
            "libx265",
            "libsvtav1",
            "h264_amf",
            "hevc_amf",
            "av1_amf",
            "h264_qsv",
            "hevc_qsv",
            "av1_qsv",
            "h264_nvenc",
            "hevc_nvenc",
            "prores_ks",
            "ffv1",
        ])
        video_form.addRow("视频编码:", codec_combo)

        preset_combo = QComboBox()
        preset_combo.setEditable(False)
        video_form.addRow("Preset:", preset_combo)

        crf_spin = QSpinBox()
        crf_spin.setRange(0, 51)
        crf_spin.setValue(18)
        video_form.addRow("CRF:", crf_spin)

        bitrate_edit = QLineEdit()
        bitrate_edit.setPlaceholderText("可留空，例如 18M")
        video_form.addRow("视频码率:", bitrate_edit)

        pix_fmt_combo = QComboBox()
        pix_fmt_combo.setEditable(True)
        pix_fmt_combo.addItems(["yuv420p", "nv12", "yuv422p10le", "yuv444p", "rgba"])
        video_form.addRow("像素格式:", pix_fmt_combo)

        worker_spin = QSpinBox()
        cpu_total = os.cpu_count() or 1
        worker_spin.setRange(0, max(64, cpu_total)) 
        worker_spin.setSpecialValueText("自动")
        worker_spin.setValue(0)
        worker_spin.setToolTip("0 为自动选择；手动指定更高进程数通常会提高 CPU 占用，但也会增加内存和中间文件开销。")
        video_form.addRow("渲染进程:", worker_spin)

        def update_codec_ui(codec_name: str):
            preset_combo.blockSignals(True)
            preset_combo.clear()
            if codec_name in {"h264_amf", "hevc_amf"}:
                preset_combo.addItems(["quality", "balanced", "speed"])
                preset_combo.setCurrentText("quality")
                crf_spin.setEnabled(False)
                crf_spin.setToolTip("AMF 编码器不使用 CRF，请配合码率或额外参数。")
                if not bitrate_edit.text().strip():
                    bitrate_edit.setPlaceholderText("AMF 建议填写码率，例如 18M 或 40M")
            elif codec_name == "av1_amf":
                preset_combo.addItems(["high_quality", "quality", "balanced", "speed"])
                preset_combo.setCurrentText("quality")
                crf_spin.setEnabled(False)
                crf_spin.setToolTip("AMF AV1 不使用 CRF，请配合码率或额外参数。")
                if pix_fmt_combo.findText("yuv420p") >= 0:
                    pix_fmt_combo.setCurrentText("yuv420p")
                if not bitrate_edit.text().strip():
                    bitrate_edit.setPlaceholderText("AMF AV1 建议填写码率，例如 12M 或 24M")
            elif codec_name in {"h264_nvenc", "hevc_nvenc"}:
                preset_combo.addItems(["p1", "p2", "p3", "p4", "p5", "p6", "p7"])
                preset_combo.setCurrentText("p6")
                crf_spin.setEnabled(False)
                crf_spin.setToolTip("NVENC 不使用 CRF，请配合码率或额外参数。")
                if not bitrate_edit.text().strip():
                    bitrate_edit.setPlaceholderText("NVENC 建议填写码率，例如 18M 或 40M")
            elif codec_name in {"h264_qsv", "hevc_qsv", "av1_qsv"}:
                preset_combo.addItems(["veryfast", "faster", "fast", "medium", "slow", "slower", "veryslow"])
                preset_combo.setCurrentText("medium")
                crf_spin.setEnabled(False)
                crf_spin.setToolTip("QSV 硬件编码不支持部分 CRF，建议配合码率或额外参数。")
                if pix_fmt_combo.findText("nv12") >= 0:
                    pix_fmt_combo.setCurrentText("nv12")
                if not bitrate_edit.text().strip():
                    bitrate_edit.setPlaceholderText("QSV 建议填写码率，例如 18M 或 40M")
            elif codec_name == "prores_ks":
                preset_combo.addItems(["standard", "hq", "4444", "4444xq"])
                preset_combo.setCurrentText("hq")
                crf_spin.setEnabled(False)
                crf_spin.setToolTip("ProRes 不使用 CRF。")
                if pix_fmt_combo.findText("yuv422p10le") >= 0:
                    pix_fmt_combo.setCurrentText("yuv422p10le")
                if not bitrate_edit.text().strip():
                    bitrate_edit.setPlaceholderText("ProRes 通常不需要单独填写码率")
            elif codec_name == "ffv1":
                preset_combo.addItems(["default"])
                preset_combo.setCurrentText("default")
                crf_spin.setEnabled(False)
                crf_spin.setToolTip("FFV1 为无损编码，不使用 CRF。")
                if pix_fmt_combo.findText("rgba") >= 0:
                    pix_fmt_combo.setCurrentText("rgba")
                if not bitrate_edit.text().strip():
                    bitrate_edit.setPlaceholderText("FFV1 无损编码通常不需要码率")
            else:
                preset_combo.addItems(["ultrafast", "superfast", "veryfast", "faster", "fast", "medium", "slow", "slower", "veryslow"])
                preset_combo.setCurrentText("slow")
                crf_spin.setEnabled(True)
                crf_spin.setToolTip("CRF 越小画质越高、体积越大。")
                if not bitrate_edit.text().strip():
                    bitrate_edit.setPlaceholderText("可留空，例如 18M")
            preset_combo.blockSignals(False)

        codec_combo.currentTextChanged.connect(update_codec_ui)
        update_codec_ui(codec_combo.currentText())

        extra_args_edit = QLineEdit()
        extra_args_edit.setPlaceholderText("额外 ffmpeg 参数，可留空")
        video_form.addRow("额外参数:", extra_args_edit)

        layout.addWidget(video_group)

        audio_group = QGroupBox("音频参数")
        audio_group.setStyleSheet("color: #aaaacc;")
        audio_form = QFormLayout(audio_group)

        include_audio_cb = QCheckBox("包含原始音频")
        include_audio_cb.setChecked(True)
        audio_form.addRow("", include_audio_cb)

        audio_codec_combo = QComboBox()
        audio_codec_combo.addItems(["aac", "libopus", "flac", "pcm_s16le"])
        audio_form.addRow("音频编码:", audio_codec_combo)

        audio_bitrate_edit = QLineEdit("320k")
        audio_form.addRow("音频码率:", audio_bitrate_edit)

        layout.addWidget(audio_group)

        output_group = QGroupBox("输出")
        output_group.setStyleSheet("color: #aaaacc;")
        output_layout = QGridLayout(output_group)
        output_path_edit = QLineEdit(str(Path(track.metadata.file_path).with_name(f"{Path(track.metadata.file_path).stem}_visualizer.mp4")))
        browse_btn = QPushButton("浏览")
        browse_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        browse_btn.setStyleSheet("background-color: #304058; color: white; border-radius: 4px; padding: 6px 12px;")

        def choose_output():
            path, _ = QFileDialog.getSaveFileName(
                dialog,
                "导出视频",
                output_path_edit.text(),
                "视频文件 (*.mp4 *.mov *.mkv *.avi);;所有文件 (*.*)",
            )
            if path:
                output_path_edit.setText(path)

        browse_btn.clicked.connect(choose_output)
        output_layout.addWidget(QLabel("文件路径:"), 0, 0)
        output_layout.addWidget(output_path_edit, 0, 1)
        output_layout.addWidget(browse_btn, 0, 2)
        layout.addWidget(output_group)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        layout.addWidget(buttons)

        if not dialog.exec():
            return

        output_path = output_path_edit.text().strip()
        if not output_path:
            QMessageBox.warning(self, "无法导出", "请先指定输出文件路径。")
            return

        progress = QProgressDialog("准备导出...", "取消", 0, 100, self)
        progress.setWindowTitle("导出视频")
        progress.setWindowModality(Qt.WindowModality.WindowModal)
        progress.setMinimumDuration(0)
        progress.setAutoClose(False)
        progress.setValue(0)
        progress.show()
        QApplication.processEvents()

        try:
            feature_cache = self._get_feature_cache_for_track(track, progress)
            if feature_cache is None:
                raise VideoExportError("未能加载该歌曲的分析缓存。")

            options = VideoExportOptions(
                output_path=output_path,
                width=width_spin.value(),
                height=height_spin.value(),
                fps=fps_spin.value(),
                video_codec=codec_combo.currentText(),
                preset=preset_combo.currentText(),
                crf=crf_spin.value(),
                video_bitrate=bitrate_edit.text().strip(),
                pixel_format=pix_fmt_combo.currentText().strip(),
                include_audio=include_audio_cb.isChecked(),
                audio_codec=audio_codec_combo.currentText(),
                audio_bitrate=audio_bitrate_edit.text().strip() or "320k",
                extra_ffmpeg_args=extra_args_edit.text().strip(),
                cpu_render_workers=worker_spin.value(),
            )

            exporter = VideoExporter()

            def on_export_progress(value: int, message: str):
                progress.setLabelText(message)
                progress.setValue(value)
                QApplication.processEvents()

            exported_path = exporter.export_track(
                track=track,
                feature_cache=feature_cache,
                options=options,
                progress_callback=on_export_progress,
                cancel_check=progress.wasCanceled,
            )
            progress.setValue(100)
            QMessageBox.information(self, "导出完成", f"视频已导出到:\n{exported_path}")
        except VideoExportCancelled:
            QMessageBox.information(self, "已取消", "视频导出已取消。")
        except VideoExportError as exc:
            QMessageBox.critical(self, "导出失败", str(exc))
        except Exception as exc:
            QMessageBox.critical(self, "导出失败", str(exc))
        finally:
            progress.close()

    def _on_update(self):
        """Update visualization - called every X ms by timer."""
        now = time.time()
        dt = now - self._last_update_time
        if dt > 0.1: # Prevent massive jumps after lag/pause
            dt = 0.016
        
        self._update_count += 1
        self._last_update_time = now

        # Get visualizer dimensions
        width = self.visualizer.width()
        height = self.visualizer.height()

        # Check if audio is actually playing using Qt's actual state
        qt_playing = self.audio_player._player.playbackState() == self.audio_player._player.PlaybackState.PlayingState

        if qt_playing:
            position = self.audio_player.get_position_ms() / 1000.0
            if hasattr(self.visualizer, "set_playback_position"):
                self.visualizer.set_playback_position(position)
            frame = self.visualization_sync.update(position)

            if frame:
                if self._update_count % 240 == 0:
                    delta = position - frame.time
                    print(f"[MainWindow] update #{self._update_count}: pos={position:.3f}s sync_time={frame.time:.3f}s delta={delta:.3f}s rms={frame.rms:.3f}")
                self.visualizer.scene.update(frame, True, width, height, dt)
            else:
                self.visualizer.scene.update(None, False, width, height, dt)
        else:
            # Idle animation
            self.visualizer.scene.update(None, False, width, height, dt)

        # Repaint
        self.visualizer.update()

    def closeEvent(self, event):
        """Handle close."""
        print("[MainWindow] Close event")
        self.audio_player.stop()
        self.visualizer.stop()
        self.update_timer.stop()
        print(f"[MainWindow] Total _on_update calls: {self._update_count}")
        super().closeEvent(event)
