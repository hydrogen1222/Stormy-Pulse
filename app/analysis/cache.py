"""
Feature cache management - saves and loads features from disk.
"""
import numpy as np
import gzip
import pickle
from pathlib import Path
from typing import Optional
import hashlib
import logging

from .features import FeatureCache, GlobalFeatureSet
from .extractor import FeatureExtractor
from ..config.constants import CACHE_VERSION, CACHE_EXT
from ..config.settings import settings

logger = logging.getLogger(__name__)


class FeatureCacheManager:
    """Manages feature caching to disk."""

    def __init__(self):
        self.cache_dir = settings.get_cache_dir()
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.extractor = FeatureExtractor()

    def get_cache_path(self, file_path: str) -> Path:
        """Get cache file path for a given audio file (Portable hash)."""
        p = Path(file_path)
        stat = p.stat()
        # Use filename instead of absolute path to make the cache portable across machines
        hash_str = f"{p.name}_{stat.st_size}_{stat.st_mtime}"
        file_hash = hashlib.md5(hash_str.encode()).hexdigest()

        return self.cache_dir / f"{CACHE_VERSION}_{file_hash}{CACHE_EXT}"

    def has_cache(self, file_path: str) -> bool:
        """Check if cache exists for a given audio file."""
        try:
            cache_path = self.get_cache_path(file_path)
            return cache_path.exists()
        except Exception:
            return False

    def load(self, file_path: str) -> Optional[FeatureCache]:
        """Load features from cache if available."""
        cache_path = self.get_cache_path(file_path)

        if not cache_path.exists():
            logger.debug(f"Cache not found: {cache_path}")
            return None

        try:
            with gzip.open(cache_path, "rb") as f:
                data = pickle.load(f)

            # Verify data integrity
            if not self._verify_cache(data, file_path):
                logger.warning(f"Cache verification failed: {cache_path}")
                cache_path.unlink()
                return None

            logger.info(f"Loaded features from cache: {cache_path.name}")
            return data["features"]

        except Exception as e:
            logger.error(f"Failed to load cache: {e}")
            try:
                cache_path.unlink()
            except Exception:
                pass
            return None

    def save(self, file_path: str, features: FeatureCache) -> bool:
        """Save features to cache."""
        cache_path = self.get_cache_path(file_path)

        try:
            data = {
                "file_path": file_path,
                "features": features,
                "version": CACHE_VERSION,
            }

            with gzip.open(cache_path, "wb") as f:
                pickle.dump(data, f)

            logger.info(f"Saved features to cache: {cache_path.name}")
            return True

        except Exception as e:
            logger.error(f"Failed to save cache: {e}")
            return False

    def _verify_cache(self, data: dict, file_path: str) -> bool:
        """Verify cache integrity."""
        if "features" not in data:
            return False
        if "file_path" not in data:
            return False
        if data["file_path"] != file_path:
            return False
        if "version" not in data:
            return False
        if data["version"] != CACHE_VERSION:
            return False
        return True

    def extract_and_cache(
        self, file_path: str, progress_callback=None
    ) -> Optional[FeatureCache]:
        """Extract features and save to cache."""
        logger.info(f"Extracting features for: {file_path}")

        features = self.extractor.extract(file_path, progress_callback)

        if features is not None:
            self.save(file_path, features)

        return features

    def get_or_extract(
        self, file_path: str, progress_callback=None
    ) -> Optional[FeatureCache]:
        """Get features from cache or extract if not available."""
        features = self.load(file_path)

        if features is None:
            features = self.extract_and_cache(file_path, progress_callback)

        return features

    def clear_cache(self):
        """Clear all cached features."""
        count = 0
        for cache_file in self.cache_dir.glob(f"*{CACHE_EXT}"):
            try:
                cache_file.unlink()
                count += 1
            except Exception as e:
                logger.error(f"Failed to delete {cache_file}: {e}")

        logger.info(f"Cleared {count} cache files")

    def get_cache_size(self) -> int:
        """Get total cache size in bytes."""
        total = 0
        for cache_file in self.cache_dir.glob(f"*{CACHE_EXT}"):
            total += cache_file.stat().st_size
        return total

    def get_cache_count(self) -> int:
        """Get number of cached tracks."""
        return len(list(self.cache_dir.glob(f"*{CACHE_EXT}")))
