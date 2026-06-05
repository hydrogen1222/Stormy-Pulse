"""
Player controls widget.
"""
from PySide6.QtWidgets import QWidget, QHBoxLayout, QVBoxLayout, QSlider, QLabel, QPushButton, QStyle
from PySide6.QtCore import Qt, Signal, QTimer
from PySide6.QtGui import QFont


class PlayerControls(QWidget):
    """Player control widget with transport controls."""

    play_clicked = Signal()
    pause_clicked = Signal()
    stop_clicked = Signal()
    previous_clicked = Signal()
    next_clicked = Signal()
    seek_requested = Signal(float)  # Position in seconds
    volume_changed = Signal(float)
    settings_clicked = Signal()
    export_clicked = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._is_playing = False
        self._duration = 0
        self._position = 0
        self._is_seeking = False

        self._setup_ui()
        self._setup_timer()

    def _setup_ui(self):
        """Setup the UI."""
        layout = QVBoxLayout(self)
        layout.setSpacing(8)

        # Progress bar and time
        progress_layout = QHBoxLayout()

        self.time_label = QLabel("00:00")
        self.time_label.setFont(QFont("Consolas", 10))
        self.time_label.setStyleSheet("color: #8888aa;")
        self.time_label.setMinimumWidth(50)
        progress_layout.addWidget(self.time_label)

        self.progress_slider = QSlider(Qt.Orientation.Horizontal)
        self.progress_slider.setMinimum(0)
        self.progress_slider.setMaximum(1000)
        self.progress_slider.setStyleSheet("""
            QSlider::groove:horizontal {
                border: 1px solid #3d3d5c;
                height: 6px;
                border-radius: 3px;
                background: #1a1a2e;
            }
            QSlider::handle:horizontal {
                background: #6c6cff;
                width: 14px;
                margin: -4px 0;
                border-radius: 7px;
            }
            QSlider::handle:horizontal:hover {
                background: #8888ff;
            }
            QSlider::sub-page:horizontal {
                background: #4c4c8c;
                border-radius: 3px;
            }
        """)
        self.progress_slider.sliderPressed.connect(self._on_slider_pressed)
        self.progress_slider.sliderReleased.connect(self._on_slider_released)
        self.progress_slider.sliderMoved.connect(self._on_slider_moved)
        progress_layout.addWidget(self.progress_slider)

        self.duration_label = QLabel("00:00")
        self.duration_label.setFont(QFont("Consolas", 10))
        self.duration_label.setStyleSheet("color: #8888aa;")
        self.duration_label.setMinimumWidth(50)
        progress_layout.addWidget(self.duration_label)

        layout.addLayout(progress_layout)

        # Transport controls
        controls_layout = QHBoxLayout()
        controls_layout.addStretch()

        # Previous button
        self.prev_button = QPushButton("⏮")
        self.prev_button.setFixedSize(40, 40)
        self.prev_button.setStyleSheet(self._button_style())
        self.prev_button.clicked.connect(self.previous_clicked.emit)
        controls_layout.addWidget(self.prev_button)

        # Play/Pause button
        self.play_button = QPushButton("▶")
        self.play_button.setFixedSize(50, 50)
        self.play_button.setStyleSheet(self._button_style("#6c6cff"))
        self.play_button.clicked.connect(self._on_play_clicked)
        controls_layout.addWidget(self.play_button)

        # Stop button
        self.stop_button = QPushButton("⏹")
        self.stop_button.setFixedSize(40, 40)
        self.stop_button.setStyleSheet(self._button_style())
        self.stop_button.clicked.connect(self.stop_clicked.emit)
        controls_layout.addWidget(self.stop_button)

        # Next button
        self.next_button = QPushButton("⏭")
        self.next_button.setFixedSize(40, 40)
        self.next_button.setStyleSheet(self._button_style())
        self.next_button.clicked.connect(self.next_clicked.emit)
        controls_layout.addWidget(self.next_button)

        controls_layout.addStretch()

        # Volume control
        volume_layout = QHBoxLayout()
        volume_layout.addWidget(QLabel("🔊"))
        self.volume_slider = QSlider(Qt.Orientation.Horizontal)
        self.volume_slider.setMinimum(0)
        self.volume_slider.setMaximum(100)
        self.volume_slider.setValue(80)
        self.volume_slider.setFixedWidth(100)
        self.volume_slider.setStyleSheet("""
            QSlider::groove:horizontal {
                border: 1px solid #3d3d5c;
                height: 4px;
                border-radius: 2px;
                background: #1a1a2e;
            }
            QSlider::handle:horizontal {
                background: #6c6cff;
                width: 10px;
                margin: -3px 0;
                border-radius: 5px;
            }
            QSlider::sub-page:horizontal {
                background: #4c4c8c;
                border-radius: 2px;
            }
        """)
        self.volume_slider.valueChanged.connect(self._on_volume_changed)
        volume_layout.addWidget(self.volume_slider)

        controls_layout.addLayout(volume_layout)
        
        # Settings button
        self.settings_button = QPushButton("⚙")
        self.settings_button.setFixedSize(40, 40)
        self.settings_button.setStyleSheet(self._button_style("#2d2d44"))
        self.settings_button.clicked.connect(self.settings_clicked.emit)
        controls_layout.addWidget(self.settings_button)

        self.export_button = QPushButton("EX")
        self.export_button.setFixedSize(44, 40)
        self.export_button.setStyleSheet(self._button_style("#304058"))
        self.export_button.clicked.connect(self.export_clicked.emit)
        controls_layout.addWidget(self.export_button)

        layout.addLayout(controls_layout)

    def _button_style(self, color="#4c4c8c"):
        """Get button style."""
        return f"""
            QPushButton {{
                background: {color};
                color: white;
                border: none;
                border-radius: 20px;
                font-size: 16px;
            }}
            QPushButton:hover {{
                background: #8888ff;
            }}
            QPushButton:pressed {{
                background: #3c3c9c;
            }}
        """

    def _setup_timer(self):
        """Setup position update timer."""
        self.timer = QTimer()
        self.timer.timeout.connect(self._update_time_display)

    def _on_play_clicked(self):
        """Handle play/pause button click."""
        if self._is_playing:
            self.pause_clicked.emit()
        else:
            self.play_clicked.emit()

    def _on_slider_pressed(self):
        """Handle slider press."""
        self._is_seeking = True

    def _on_slider_released(self):
        """Handle slider release."""
        if self._is_seeking and self._duration > 0:
            position = (self.progress_slider.value() / 1000.0) * self._duration
            self.seek_requested.emit(position)
        self._is_seeking = False

    def _on_slider_moved(self, value):
        """Handle slider move."""
        if self._duration > 0:
            position = (value / 1000.0) * self._duration
            self._update_time_label(position)

    def _on_volume_changed(self, value):
        """Handle volume change."""
        self.volume_changed.emit(value / 100.0)

    def _update_time_display(self):
        """Update time display from position."""
        if not self._is_seeking:
            self._update_time_label(self._position)

    def _update_time_label(self, position):
        """Update time label."""
        minutes = int(position) // 60
        seconds = int(position) % 60
        self.time_label.setText(f"{minutes:02d}:{seconds:02d}")

    def set_playing(self, is_playing: bool):
        """Set playing state."""
        self._is_playing = is_playing
        self.play_button.setText("⏸" if is_playing else "▶")
        if is_playing:
            self.timer.start(100)
        else:
            self.timer.stop()

    def set_position(self, position: float):
        """Set current position."""
        if not self._is_seeking:
            self._position = position
            if self._duration > 0:
                slider_value = int((position / self._duration) * 1000)
                self.progress_slider.setValue(slider_value)
            self._update_time_label(position)

    def set_duration(self, duration: float):
        """Set track duration."""
        self._duration = duration
        minutes = int(duration) // 60
        seconds = int(duration) % 60
        self.duration_label.setText(f"{minutes:02d}:{seconds:02d}")

    def set_enabled(self, enabled: bool):
        """Enable or disable controls."""
        self.play_button.setEnabled(enabled)
        self.stop_button.setEnabled(enabled)
        self.prev_button.setEnabled(enabled)
        self.next_button.setEnabled(enabled)
        self.progress_slider.setEnabled(enabled)
        self.export_button.setEnabled(enabled)
