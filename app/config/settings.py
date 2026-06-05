"""
Settings manager for the music visualizer.
"""
import json
import os
from pathlib import Path

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

    def get_cache_dir(self) -> Path:
        """Get the cache directory."""
        cache_dir = self.config_dir / "cache"
        cache_dir.mkdir(parents=True, exist_ok=True)
        return cache_dir

# Global settings instance
settings = Settings()
