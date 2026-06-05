"""
Audio player using PySide6 multimedia.
"""
from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer
from PySide6.QtCore import QUrl, Signal, QObject
from PySide6.QtWidgets import QApplication
import sys

from .playback_state import PlaybackState
from .music_library import Track


class AudioPlayer(QObject):
    """Audio player using QtMultimedia."""

    position_changed = Signal(int)  # Position in milliseconds
    duration_changed = Signal(int)  # Duration in milliseconds
    playback_state_changed = Signal(bool)  # True if playing
    track_changed = Signal(object)  # Track object
    end_of_track = Signal()  # Emitted when track ends

    def __init__(self):
        super().__init__()
        self._player = QMediaPlayer()
        self._audio_output = QAudioOutput()
        self._player.setAudioOutput(self._audio_output)

        self.playback_state = PlaybackState()
        self.current_track: Track | None = None

        # Connect signals
        self._player.positionChanged.connect(self._on_position_changed)
        self._player.durationChanged.connect(self._on_duration_changed)
        self._player.playbackStateChanged.connect(self._on_playback_state_changed)

    def load_track(self, track: Track):
        """Load a track for playback."""
        self.current_track = track
        url = QUrl.fromLocalFile(track.metadata.file_path)
        self._player.setSource(url)
        self.playback_state.set_duration(track.metadata.duration)
        self.track_changed.emit(track)

    def play(self):
        """Start or resume playback."""
        if self.current_track is None:
            return
        self._player.play()
        self.playback_state.play()

    def pause(self):
        """Pause playback."""
        self._player.pause()
        self.playback_state.pause()

    def stop(self):
        """Stop playback."""
        self._player.stop()
        self.playback_state.stop()

    def seek(self, position_ms: int):
        """Seek to position in milliseconds."""
        self._player.setPosition(position_ms)
        self.playback_state.seek(position_ms / 1000.0)

    def set_volume(self, volume: float):
        """Set volume (0.0 to 1.0)."""
        self._audio_output.setVolume(volume)
        self.playback_state.volume = volume

    def is_playing(self) -> bool:
        """Check if currently playing."""
        return self._player.playbackState() == QMediaPlayer.PlaybackState.PlayingState

    def get_position_ms(self) -> int:
        """Get current position in milliseconds."""
        return self._player.position()

    def get_duration_ms(self) -> int:
        """Get duration in milliseconds."""
        return self._player.duration()

    def _on_position_changed(self, position: int):
        """Handle position change."""
        self.playback_state.position = position / 1000.0
        self.position_changed.emit(position)

    def _on_duration_changed(self, duration: int):
        """Handle duration change."""
        self.playback_state.duration = duration / 1000.0
        self.duration_changed.emit(duration)

    def _on_playback_state_changed(self, state):
        """Handle playback state change."""
        is_playing = state == QMediaPlayer.PlaybackState.PlayingState
        self.playback_state.is_playing = is_playing
        self.playback_state_changed.emit(is_playing)

        if (
            not is_playing
            and self.playback_state.position >= self.playback_state.duration - 0.5
        ):
            self.end_of_track.emit()
