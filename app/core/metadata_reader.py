"""
Music metadata reader using mutagen.
"""
import mutagen
from mutagen import File as MutagenFile
from mutagen.mp4 import MP4
from mutagen.flac import FLAC
from mutagen.mp3 import MP3
from typing import Optional, Dict, Any
from pathlib import Path
import base64
from io import BytesIO


class TrackMetadata:
    """Container for track metadata."""

    def __init__(self, file_path: str):
        self.file_path = file_path
        self.title = Path(file_path).stem
        self.artist = "Unknown Artist"
        self.album = "Unknown Album"
        self.duration = 0.0
        self.genre = ""
        self.year = ""
        self.bitrate = 0
        self.sample_rate = 44100
        self.channels = 2
        self.cover_art: Optional[bytes] = None
        self.cover_art_mime = ""
        import hashlib
        p = Path(file_path)
        try:
            stat_info = p.stat()
            h_str = f"{p.as_posix()}_{stat_info.st_size}_{stat_info.st_mtime}"
        except Exception:
            h_str = p.as_posix()
        self.file_hash = hashlib.blake2b(h_str.encode("utf-8"), digest_size=16).hexdigest()

        self._read_metadata()

    def _read_metadata(self):
        """Read metadata from the audio file."""
        try:
            audio = MutagenFile(self.file_path)
            if audio is None:
                return

            # Duration
            if hasattr(audio, "info"):
                self.duration = getattr(audio.info, "length", 0.0)
                self.bitrate = getattr(audio.info, "bitrate", 0)
                self.sample_rate = getattr(audio.info, "sample_rate", 44100)
                self.channels = getattr(audio.info, "channels", 2)

            # Robust tag extraction for different formats
            if audio.tags:
                # Try generic dictionary access (FLAC, OGG, etc.)
                def get_tag(keys, default):
                    for k in keys:
                        # Some formats use uppercase, some lowercase
                        val = audio.tags.get(k) or audio.tags.get(k.lower()) or audio.tags.get(k.upper())
                        if val:
                            if isinstance(val, list):
                                return str(val[0])
                            return str(val)
                    return default

                extracted_title = get_tag(["title", "TIT2", "\xa9nam"], None)
                extracted_artist = get_tag(["artist", "TPE1", "\xa9ART"], None)
                extracted_album = get_tag(["album", "TALB", "\xa9alb"], "Unknown Album")
                
                if extracted_title:
                    self.title = extracted_title
                if extracted_artist:
                    self.artist = extracted_artist
                else:
                    self.artist = "" # Use empty string instead of Unknown Artist
                self.album = extracted_album

                # Cover art
                # Check ID3
                if "APIC:" in audio.tags:
                    apic = audio.tags["APIC:"][0]
                    self.cover_art = apic.data
                    self.cover_art_mime = apic.mime
                # Check FLAC/Ogg
                elif hasattr(audio, "pictures") and audio.pictures:
                    pic = audio.pictures[0]
                    self.cover_art = pic.data
                    self.cover_art_mime = pic.mime
                # Check M4A
                elif "covr" in audio.tags:
                    covr = audio.tags["covr"][0]
                    self.cover_art = covr
                    self.cover_art_mime = "image/jpeg"

            # Finally, check for manual overrides in settings
            from ..config.settings import settings
            overrides = settings.get("metadata_overrides", {})
            if self.file_path in overrides:
                ov = overrides[self.file_path]
                self.title = ov.get("title", self.title)
                self.artist = ov.get("artist", self.artist)

        except Exception as e:
            print(f"Error reading metadata from {self.file_path}: {e}")

    def get_cover_art_base64(self) -> Optional[str]:
        """Get cover art as base64 string for QPixmap."""
        if self.cover_art:
            return base64.b64encode(self.cover_art).decode("utf-8")
        return None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "file_path": self.file_path,
            "title": self.title,
            "artist": self.artist,
            "album": self.album,
            "duration": self.duration,
            "genre": self.genre,
            "year": self.year,
            "bitrate": self.bitrate,
            "sample_rate": self.sample_rate,
            "channels": self.channels,
            "has_cover": self.cover_art is not None,
        }
