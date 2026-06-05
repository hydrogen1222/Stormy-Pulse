"""
Playback state management - maintains current playback position and state.
"""
from enum import Enum
from typing import Optional
import time


class RepeatMode(Enum):
    NONE = "none"
    ONE = "one"
    ALL = "all"


class PlaybackState:
    """Manages playback state and position tracking."""

    def __init__(self):
        self.is_playing = False
        self.position = 0.0  # Current position in seconds
        self.duration = 0.0  # Total duration in seconds
        self.volume = 0.8
        self.repeat_mode = RepeatMode.NONE
        self.shuffle = False

        # For sync tracking
        self._start_time: Optional[float] = None
        self._pause_position = 0.0

    def play(self):
        """Start playback."""
        self.is_playing = True
        self._start_time = time.perf_counter() - self._pause_position

    def pause(self):
        """Pause playback."""
        if self.is_playing:
            self.is_playing = False
            self._pause_position = time.perf_counter() - self._start_time

    def stop(self):
        """Stop playback and reset position."""
        self.is_playing = False
        self.position = 0.0
        self._pause_position = 0.0
        self._start_time = None

    def seek(self, position: float):
        """Seek to a specific position."""
        self.position = max(0.0, min(position, self.duration))
        if self.is_playing:
            self._start_time = time.perf_counter() - self.position
        else:
            self._pause_position = self.position

    def update_position(self):
        """Update current position based on elapsed time."""
        if self.is_playing and self._start_time is not None:
            self.position = time.perf_counter() - self._start_time
            if self.position >= self.duration:
                self.position = self.duration
                # Handle end of track
                if self.repeat_mode == RepeatMode.ONE:
                    self.seek(0)
                    self.play()
                elif self.repeat_mode == RepeatMode.ALL:
                    # Signal that we need the next track
                    pass
                else:
                    self.pause()

    def get_position_ms(self) -> int:
        """Get position in milliseconds."""
        return int(self.position * 1000)

    def get_duration_ms(self) -> int:
        """Get duration in milliseconds."""
        return int(self.duration * 1000)

    def get_progress(self) -> float:
        """Get progress as a value between 0 and 1."""
        if self.duration > 0:
            return self.position / self.duration
        return 0.0

    def set_duration(self, duration: float):
        """Set the track duration."""
        self.duration = duration
        if self.position > duration:
            self.position = duration
