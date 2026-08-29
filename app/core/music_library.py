"""
Music library management - handles scanning and storing track information.
"""
import os
from pathlib import Path
from typing import List, Optional
import hashlib
import json

from ..config.constants import SUPPORTED_FORMATS
from .lyrics import TrackLyrics, find_lyrics_file, parse_lrc_file
from .metadata_reader import TrackMetadata


class Track:
    """Represents a track in the library."""

    def __init__(self, file_path: str):
        self.file_path = file_path
        self.metadata = TrackMetadata(file_path)
        self.file_hash = self._compute_hash()
        self.metadata.file_hash = self.file_hash
        self.cache_path: Optional[str] = None
        self.is_analyzed = False
        self.lyrics_path: Optional[str] = None
        self.lyrics: Optional[TrackLyrics] = None

    def _compute_hash(self) -> str:
        """Compute hash based on file path and size."""
        try:
            stat = os.stat(self.file_path)
            hash_str = f"{self.file_path}_{stat.st_size}_{stat.st_mtime}"
            return hashlib.md5(hash_str.encode()).hexdigest()
        except Exception:
            return hashlib.md5(self.file_path.encode()).hexdigest()

    def __repr__(self):
        return f"Track({self.metadata.title} - {self.metadata.artist})"

    def load_lyrics(self) -> Optional[TrackLyrics]:
        """Lazy-load an associated LRC file from the same folder."""
        if self.lyrics is not None:
            return self.lyrics

        lyric_path = find_lyrics_file(self.file_path)
        self.lyrics_path = str(lyric_path) if lyric_path else None
        if not lyric_path:
            return None

        try:
            self.lyrics = parse_lrc_file(str(lyric_path))
        except Exception as exc:
            print(f"Failed to load lyrics for {self.file_path}: {exc}")
            self.lyrics = None
        return self.lyrics


class MusicLibrary:
    """Manages the music library."""

    def __init__(self):
        self.tracks: List[Track] = []
        self.current_index = -1
        self._cache_file = Path.home() / ".music_visualizer" / "library.json"

    def add_track(self, file_path: str) -> Optional[Track]:
        """Add a single track to the library."""
        path = Path(file_path)
        if not path.exists():
            return None

        ext = path.suffix.lower()
        if ext not in SUPPORTED_FORMATS:
            return None

        # Check if already in library
        for track in self.tracks:
            if track.file_path == file_path:
                return track

        track = Track(file_path)
        self.tracks.append(track)
        return track

    def add_directory(self, directory: str) -> int:
        """Scan a directory for audio files and add them."""
        count = 0
        dir_path = Path(directory)
        if not dir_path.exists():
            return 0

        for ext in SUPPORTED_FORMATS:
            for file_path in dir_path.rglob(f"*{ext}"):
                if self.add_track(str(file_path)):
                    count += 1

        return count

    def get_current_track(self) -> Optional[Track]:
        """Get the currently selected track."""
        if 0 <= self.current_index < len(self.tracks):
            return self.tracks[self.current_index]
        return None

    def set_current_index(self, index: int):
        """Set the current track index."""
        if 0 <= index < len(self.tracks):
            self.current_index = index

    def next_track(self) -> Optional[Track]:
        """Move to the next track."""
        if not self.tracks:
            return None
        self.current_index = (self.current_index + 1) % len(self.tracks)
        return self.get_current_track()

    def previous_track(self) -> Optional[Track]:
        """Move to the previous track."""
        if not self.tracks:
            return None
        self.current_index = (self.current_index - 1) % len(self.tracks)
        return self.get_current_track()

    def shuffle_indices(self) -> List[int]:
        """Get shuffled indices for shuffle mode."""
        indices = list(range(len(self.tracks)))
        import random

        random.shuffle(indices)
        return indices

    def clear(self):
        """Clear the library."""
        self.tracks.clear()
        self.current_index = -1

    def get_track_count(self) -> int:
        """Get the number of tracks in the library."""
        return len(self.tracks)

    def save_library(self):
        """Save library state to cache."""
        try:
            data = []
            for track in self.tracks:
                data.append(
                    {
                        "file_path": track.file_path,
                        "file_hash": track.file_hash,
                        "cache_path": track.cache_path,
                        "is_analyzed": track.is_analyzed,
                    }
                )

            self._cache_file.parent.mkdir(parents=True, exist_ok=True)
            with open(self._cache_file, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
        except Exception as e:
            print(f"Failed to save library: {e}")

    def load_library(self):
        """Load library state from cache."""
        if not self._cache_file.exists():
            return

        try:
            with open(self._cache_file, "r", encoding="utf-8") as f:
                data = json.load(f)

            for item in data:
                path = item["file_path"]
                if Path(path).exists():
                    track = self.add_track(path)
                    if track:
                        track.file_hash = item["file_hash"]
                        track.cache_path = item.get("cache_path")
                        track.is_analyzed = item.get("is_analyzed", False)
        except Exception as e:
            print(f"Failed to load library: {e}")
