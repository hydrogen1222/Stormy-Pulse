"""
Settings manager for the music visualizer.
"""
import json
import os
import shutil
from pathlib import Path
from typing import Optional

from .constants import CACHE_EXT

DEFAULT_SETTINGS = {
    "fps": 60,
    "theme": "auto",
    "library_folders": [],
    "recent_files": [],
    "volume": 0.8,
    "last_high_fps": 144,
    "show_left_hud": True,
    "show_right_hud": True,
    "show_track_title": True,
    "show_track_artist": True,
    "show_lyrics": False,
    "show_fps": True,
    "show_dev_hud": False,
    "render_backend": "cpu",
    "visual_canvas_ratio": "16:9",
    "hud_scale": 1.0,
    "hud_opacity": 0.8,
    "hud_glow_strength": 1.0,
    "title_font_family": "",
    "artist_font_family": "",
    "lyric_font_family": "",
    "lyric_original_font_family": "",
    "lyric_translation_font_family": "",
    "font_scale_title": 1.0,
    "font_scale_artist": 1.0,
    "font_scale_lyrics": 1.0,
    "font_scale_hud": 1.0,
    "font_scale_left_hud": 1.0,
    "font_scale_right_hud": 1.0,
    "module_scale_title": 1.0,
    "module_scale_artist": 1.0,
    "module_scale_lyrics": 1.0,
    "module_scale_left_hud": 1.0,
    "module_scale_right_hud": 1.0,
    "module_scale_effect": 1.0,
    "layout_title_x": 0.0,
    "layout_title_y": 0.0,
    "layout_artist_x": 0.0,
    "layout_artist_y": 0.0,
    "layout_lyrics_x": 0.0,
    "layout_lyrics_y": 0.0,
    "layout_left_hud_x": 0.0,
    "layout_left_hud_y": 0.0,
    "layout_right_hud_x": 0.0,
    "layout_right_hud_y": 0.0,
    "custom_track_title": "",
    "custom_track_artist": "",
    "metadata_overrides": {},
}

class Settings:
    """Manages application settings."""
    
    def __init__(self):
        self.config_dir = Path.home() / ".music_visualizer"
        self.config_file = self.config_dir / "settings.json"
        self.data = DEFAULT_SETTINGS.copy()
        self.load()

    def load(self):
        """Load settings from file."""
        if self.config_file.exists():
            try:
                with open(self.config_file, "r", encoding="utf-8") as f:
                    user_data = json.load(f)
                    self.data.update(user_data)
            except Exception as e:
                print(f"[Settings] Error loading settings: {e}")
        else:
            self.save()

    def save(self):
        """Save settings to file."""
        try:
            self.config_dir.mkdir(parents=True, exist_ok=True)
            with open(self.config_file, "w", encoding="utf-8") as f:
                json.dump(self.data, f, indent=4)
        except Exception as e:
            print(f"[Settings] Error saving settings: {e}")

    def get(self, key, default=None):
        return self.data.get(key, default)

    def set(self, key, value):
        self.data[key] = value
        self.save()

    def merge_overrides(self, values: Optional[dict]) -> dict:
        """Return the effective data dict with temporary overrides applied (no persistence)."""
        merged = dict(self.data)
        if values:
            for key, value in values.items():
                if value is not None:
                    merged[key] = value
        return merged

    def override(self, values: Optional[dict]):
        """Context manager: temporary in-memory overrides that are never saved to disk.

        Used by the WebUI / headless rendering paths so browser-side tweaks do not
        overwrite the desktop application's persisted configuration.
        """
        return _SettingsOverride(self, values)

    def get_cache_dir(self) -> Path:
        """Get the feature-cache directory.

        The cache lives in a project-local ``cache/`` folder next to the
        source code so users can easily inspect and manage it, instead of
        a hidden folder inside the user profile. Falls back to the legacy
        home directory when the project location is not usable (e.g. a
        non-editable install inside site-packages).
        """
        root = self._project_cache_root()
        if root is not None:
            cache_dir = root / "cache"
            try:
                cache_dir.mkdir(parents=True, exist_ok=True)
                self._migrate_legacy_home_cache(cache_dir)
                return cache_dir
            except OSError as exc:
                print(
                    f"[Settings] Project cache dir unavailable ({exc}); "
                    "falling back to home directory"
                )

        cache_dir = self.config_dir / "cache"
        cache_dir.mkdir(parents=True, exist_ok=True)
        return cache_dir

    @staticmethod
    def _project_cache_root() -> Optional[Path]:
        """Locate the source-checkout root that should host the cache.

        Returns None when this module is running from an installed copy
        (site-packages / .venv) rather than a source checkout.
        """
        root = Path(__file__).resolve().parents[2]
        lowered = {part.lower() for part in root.parts}
        if {"site-packages", "dist-packages"} & lowered:
            return None
        if ".venv" in lowered:
            return None
        return root

    @staticmethod
    def _migrate_legacy_home_cache(cache_dir: Path) -> None:
        """One-time migration of caches from ~/.music_visualizer/cache.

        Moves existing cache files into the project-local cache dir so
        already-analyzed tracks keep loading instantly after the
        directory change. When the project already holds a cache with
        the same key, the redundant legacy copy (e.g. re-created by a
        still-running old instance) is removed to keep things tidy.
        """
        legacy_dir = Path.home() / ".music_visualizer" / "cache"
        if not legacy_dir.is_dir() or legacy_dir == cache_dir:
            return
        for legacy_file in legacy_dir.glob(f"*{CACHE_EXT}"):
            target = cache_dir / legacy_file.name
            if target.exists():
                try:
                    legacy_file.unlink()
                    print(f"[Settings] Removed duplicate legacy cache: {legacy_file.name}")
                except OSError as exc:
                    print(f"[Settings] Could not remove legacy cache {legacy_file.name}: {exc}")
                continue
            try:
                shutil.move(str(legacy_file), str(target))
                print(f"[Settings] Migrated feature cache: {legacy_file.name}")
            except OSError as exc:
                print(f"[Settings] Failed to migrate {legacy_file.name}: {exc}")


class _SettingsOverride:
    """Reusable context manager returned by Settings.override()."""

    def __init__(self, owner: "Settings", values: Optional[dict]):
        self._owner = owner
        self._values = values
        self._original: Optional[dict] = None

    def __enter__(self) -> "Settings":
        self._original = self._owner.data
        self._owner.data = self._owner.merge_overrides(self._values)
        return self._owner

    def __exit__(self, exc_type, exc, tb) -> bool:
        if self._original is not None:
            self._owner.data = self._original
            self._original = None
        return False


# Global settings instance
settings = Settings()
