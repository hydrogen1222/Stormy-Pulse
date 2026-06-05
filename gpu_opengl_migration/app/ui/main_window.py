"""
Main window for the music visualizer.
"""
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
)
from PySide6.QtCore import Qt, QTimer, Signal, QThread, QObject
from PySide6.QtGui import QFont, QPixmap

from ..core import AudioPlayer, MusicLibrary
from ..analysis import VisualizationSync
from ..export import VideoExportCancelled, VideoExportError, VideoExportOptions, VideoExporter
from ..visual_gpu import VisualizerViewport as VisualizerRenderer
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
        self.visualizer = VisualizerRenderer()
        self.visualizer.setMinimumHeight(420)
        self.visualizer.setStyleSheet("""
            background: qlineargradient(
                x1: 0, y1: 0, x2: 1, y2: 1,
                stop: 0 rgba(9, 18, 30, 255),
                stop: 0.55 rgba(13, 27, 44, 255),
                stop: 1 rgba(10, 24, 40, 255)
            );
            border: 1px solid rgba(92, 148, 204, 84);
            border-radius: 14px;
        """)
        right_panel.addWidget(self.visualizer, 1)

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
        track_layout.addWidget(self.edit_btn, 0, 2, 2, 1, Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)

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

        main_layout.addLayout(right_panel, 1)

        print(f"[MainWindow] UI setup complete. Visualizer widget: {self.visualizer}")
        print(f"[MainWindow] Visualizer size: {self.visualizer.width()}x{self.visualizer.height()}")

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
        from PySide6.QtWidgets import QDialog, QVBoxLayout, QComboBox, QFormLayout, QDialogButtonBox, QCheckBox, QGroupBox, QFontComboBox
        
        dialog = QDialog(self)
        dialog.setWindowTitle("引擎设置")
        dialog.setFixedWidth(420)
        dialog.setStyleSheet("background: #16162a; color: white;")
        
        layout = QVBoxLayout(dialog)
        
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
        
        layout.addWidget(perf_group)
        
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

        layout.addWidget(hud_group)

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

        layout.addWidget(font_group)
        
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        layout.addWidget(buttons)
        
        if dialog.exec():
            # Update settings
            selected = fps_combo.currentText()
            new_fps = 0 if selected == "No Limit" else int(selected)
            self.settings.set("fps", new_fps)
            self.settings.set("show_fps", cb_fps.isChecked())
            self.settings.set("show_track_title", cb_top_title.isChecked())
            self.settings.set("show_left_hud", cb_left_hud.isChecked())
            self.settings.set("show_right_hud", cb_right_hud.isChecked())
            self.settings.set("show_lyrics", cb_lyrics.isChecked())
            self.settings.set("show_dev_hud", cb_dev_hud.isChecked())
            self.settings.set("title_font_family", title_font_combo.currentFont().family())
            self.settings.set("artist_font_family", artist_font_combo.currentFont().family())
            self.settings.set("lyric_font_family", lyric_original_font_combo.currentFont().family())
            self.settings.set("lyric_original_font_family", lyric_original_font_combo.currentFont().family())
            self.settings.set("lyric_translation_font_family", lyric_translation_font_combo.currentFont().family())
            
            # Update immediate state
            interval = self._configure_update_timer(new_fps)
            self.visualizer.set_target_fps(new_fps)
            current_track = self.music_library.get_current_track()
            if cb_lyrics.isChecked() and current_track and hasattr(self.visualizer, "set_lyrics"):
                self.visualizer.set_lyrics(current_track.load_lyrics())
            
            print(
                f"[MainWindow] Settings updated: FPS={new_fps}, TrackTitle={cb_top_title.isChecked()}, "
                f"LeftHUD={cb_left_hud.isChecked()}, RightHUD={cb_right_hud.isChecked()}, Lyrics={cb_lyrics.isChecked()}, "
                f"TitleFont={title_font_combo.currentFont().family()}, ArtistFont={artist_font_combo.currentFont().family()}, "
                f"LyricOriginal={lyric_original_font_combo.currentFont().family()}, "
                f"LyricTranslation={lyric_translation_font_combo.currentFont().family()}, DevHUD={cb_dev_hud.isChecked()}"
            )
            # Force a visualizer update
            self.visualizer.update()

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

        def sync_height(width_value: int):
            if sync_guard["value"]:
                return
            sync_guard["value"] = True
            height_spin.setValue(max(360, ((width_value * 9) // 16) // 2 * 2))
            sync_guard["value"] = False

        def sync_width(height_value: int):
            if sync_guard["value"]:
                return
            sync_guard["value"] = True
            width_spin.setValue(max(640, ((height_value * 16) // 9) // 2 * 2))
            sync_guard["value"] = False

        width_spin.valueChanged.connect(sync_height)
        height_spin.valueChanged.connect(sync_width)

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
        pix_fmt_combo.addItems(["yuv420p", "yuv422p10le", "yuv444p", "rgba"])
        video_form.addRow("像素格式:", pix_fmt_combo)

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
