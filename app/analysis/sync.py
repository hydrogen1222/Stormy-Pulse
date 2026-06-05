"""
Visualization sync module - handles time-based synchronization.
"""
from typing import Optional
import logging

from .features import FeatureCache, FeatureFrame
from .cache import FeatureCacheManager

logger = logging.getLogger(__name__)


class VisualizationSync:
    """Synchronizes visualization with audio playback time."""

    def __init__(self):
        self.feature_cache: Optional[FeatureCache] = None
        self.cache_manager = FeatureCacheManager()
        self._current_frame: Optional[FeatureFrame] = None
        self._last_time = -1.0

    def load_track(
        self, file_path: str, progress_callback=None
    ) -> bool:
        """
        Load features for a track.

        Returns:
            True if successful, False otherwise
        """
        try:
            self.feature_cache = self.cache_manager.get_or_extract(
                file_path, progress_callback
            )

            if self.feature_cache is None:
                logger.error(f"Failed to load features for: {file_path}")
                return False

            self._current_frame = None
            self._last_time = -1.0
            logger.info(f"Loaded features for visualization sync: {file_path}")
            return True

        except Exception as e:
            logger.error(f"Error loading track features: {e}")
            return False

    def seek_to(self, time_seconds: float):
        """Seek to a specific time position."""
        if self.feature_cache is None:
            return

        self._current_frame = self.feature_cache.get_frame_at_time(time_seconds)
        self._last_time = time_seconds

    def update(self, current_time: float) -> Optional[FeatureFrame]:
        """
        Update to current playback time.

        Args:
            current_time: Current playback time in seconds

        Returns:
            FeatureFrame at the current time, or None
        """
        if self.feature_cache is None:
            return None

        # Only update if time has changed significantly
        if abs(current_time - self._last_time) < 0.001:
            return self._current_frame

        self._current_frame = self.feature_cache.get_frame_at_time(current_time)
        self._last_time = current_time

        return self._current_frame

    def get_current_frame(self) -> Optional[FeatureFrame]:
        """Get the current feature frame."""
        return self._current_frame

    def get_global_features(self):
        """Get the global features for this track."""
        if self.feature_cache is None:
            return None
        return self.feature_cache.global_features

    def get_duration(self) -> float:
        """Get the track duration."""
        if self.feature_cache is None:
            return 0.0
        return self.feature_cache.duration

    def is_loaded(self) -> bool:
        """Check if a track is loaded."""
        return self.feature_cache is not None

    def reset(self):
        """Reset the sync state."""
        self.feature_cache = None
        self._current_frame = None
        self._last_time = -1.0

    def preload_track(self, file_path: str, progress_callback=None):
        """
        Preload a track's features without blocking.
        This can be called before the track is actually played.
        """
        import threading

        def _preload():
            self.cache_manager.get_or_extract(file_path, progress_callback)

        thread = threading.Thread(target=_preload, daemon=True)
        thread.start()
