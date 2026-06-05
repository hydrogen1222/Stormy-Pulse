"""
Playlist panel widget.
"""
from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QFileDialog,
    QLabel,
    QLineEdit,
)
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFont, QColor


class PlaylistPanel(QWidget):
    """Playlist management widget."""

    track_selected = Signal(int)  # Track index
    add_files_requested = Signal()
    add_folder_requested = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setStyleSheet("""
            background: rgba(15, 15, 30, 150);
            border-right: 1px solid rgba(80, 80, 120, 80);
        """)
        self._setup_ui()

    def _setup_ui(self):
        """Setup the UI."""
        layout = QVBoxLayout(self)
        layout.setSpacing(8)

        # Header
        header_layout = QHBoxLayout()
        title = QLabel("播放列表")
        title.setFont(QFont("Microsoft YaHei", 12, QFont.Weight.Bold))
        title.setStyleSheet("color: white;")
        header_layout.addWidget(title)
        header_layout.addStretch()

        self.add_file_btn = QPushButton("+ 文件")
        self.add_file_btn.setFixedHeight(28)
        self.add_file_btn.setStyleSheet(self._button_style())
        self.add_file_btn.clicked.connect(self.add_files_requested.emit)
        header_layout.addWidget(self.add_file_btn)

        self.add_folder_btn = QPushButton("+ 文件夹")
        self.add_folder_btn.setFixedHeight(28)
        self.add_folder_btn.setStyleSheet(self._button_style())
        self.add_folder_btn.clicked.connect(self._on_add_folder)
        header_layout.addWidget(self.add_folder_btn)

        layout.addLayout(header_layout)

        # Playlist list
        self.playlist = QListWidget()
        self.playlist.setStyleSheet("""
            QListWidget {
                background: transparent;
                border: none;
                color: #ccccdd;
                outline: none;
            }
            QListWidget::item {
                padding: 10px;
                border-bottom: 1px solid rgba(60, 60, 90, 60);
                margin: 2px 8px;
                border-radius: 6px;
            }
            QListWidget::item:selected {
                background: rgba(108, 108, 255, 100);
                color: white;
                border-left: 3px solid #6c6cff;
            }
            QListWidget::item:hover {
                background: rgba(255, 255, 255, 20);
            }
        """)
        self.playlist.currentRowChanged.connect(self._on_current_row_changed)
        layout.addWidget(self.playlist)

        # Track count
        self.count_label = QLabel("0 首歌")
        self.count_label.setStyleSheet("color: #666688; font-size: 11px;")
        layout.addWidget(self.count_label)

    def _button_style(self):
        """Get button style."""
        return """
            QPushButton {
                background: #3d3d5c;
                color: white;
                border: none;
                border-radius: 4px;
                padding: 4px 12px;
                font-size: 12px;
            }
            QPushButton:hover {
                background: #4d4d7c;
            }
        """

    def _on_add_folder(self):
        """Handle add folder click."""
        folder = QFileDialog.getExistingDirectory(
            self, "选择音乐文件夹", "", QFileDialog.Option.ShowDirsOnly
        )
        if folder:
            self.add_folder_requested.emit(folder)

    def _on_current_row_changed(self, row):
        """Handle current row change."""
        if row >= 0:
            self.track_selected.emit(row)

    def add_track(self, title: str, artist: str = "", album: str = "", duration: float = 0):
        """Add a track to the playlist."""
        text = f"{title}"
        if artist:
            text += f" - {artist}"
        if duration > 0:
            minutes = int(duration) // 60
            seconds = int(duration) % 60
            text += f" ({minutes:02d}:{seconds:02d})"

        item = QListWidgetItem(text)
        item.setData(Qt.ItemDataRole.UserRole, {"artist": artist, "album": album})
        self.playlist.addItem(item)
        self._update_count()

    def add_tracks(self, tracks: list):
        """Add multiple tracks."""
        for track in tracks:
            self.add_track(
                track.get("title", "Unknown"),
                track.get("artist", ""),
                track.get("album", ""),
                track.get("duration", 0),
            )

    def clear(self):
        """Clear the playlist."""
        self.playlist.clear()
        self._update_count()

    def set_current_row(self, row: int):
        """Set current playing row."""
        if 0 <= row < self.playlist.count():
            self.playlist.setCurrentRow(row)

    def update_current_track_info(self, title: str, artist: str):
        """Update display text for current track."""
        row = self.playlist.currentRow()
        if row >= 0:
            item = self.playlist.item(row)
            text = f"{title}"
            if artist:
                text += f" - {artist}"
            
            # Preserve old duration if it had one
            old_text = item.text()
            if "(" in old_text and ")" in old_text:
                duration_str = old_text[old_text.rfind("("):]
                text += f" {duration_str}"
                
            item.setText(text)
            
            data = item.data(Qt.ItemDataRole.UserRole)
            if isinstance(data, dict):
                data["artist"] = artist
                item.setData(Qt.ItemDataRole.UserRole, data)

    def get_current_row(self) -> int:
        """Get current selected row."""
        return self.playlist.currentRow()

    def get_track_count(self) -> int:
        """Get track count."""
        return self.playlist.count()

    def _update_count(self):
        """Update track count label."""
        count = self.playlist.count()
        self.count_label.setText(f"{count} 首歌")
