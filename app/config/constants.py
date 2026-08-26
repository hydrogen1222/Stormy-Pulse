"""
Constants for the music visualizer project.
"""

# Audio analysis constants
SAMPLE_RATE = 44100
HOP_LENGTH = 512
FFT_SIZE = 2048
N_MELS = 128
N_MFCC = 20

# Feature extraction
FEATURE_FPS = 60  # Target feature frame rate
FEATURE_FRAME_INTERVAL = 1.0 / FEATURE_FPS

# Beat detection
BEAT_TRACK_SMOOTH = 0.15
ENERGY_RATIO_LOW = 0.25
ENERGY_RATIO_MID = 0.5
ENERGY_RATIO_HIGH = 1.0

# Caching
CACHE_VERSION = "v5"
CACHE_EXT = ".npz"

# Visualization constants
VISUAL_FPS = 60
VISUAL_FPS_MIN = 30
SCREEN_WIDTH = 1280
SCREEN_HEIGHT = 720

# Color themes (Visual DNA base colors)
THEME_COLORS = {
    "cyber": {"hues": [180, 220, 280], "saturation": 0.7, "brightness": 0.8},
    "dream": {"hues": [280, 320, 180], "saturation": 0.5, "brightness": 0.9},
    "universe": {"hues": [220, 260, 300], "saturation": 0.6, "brightness": 0.7},
    "fire": {"hues": [0, 30, 60], "saturation": 0.8, "brightness": 0.8},
    "nature": {"hues": [80, 120, 40], "saturation": 0.6, "brightness": 0.75},
}

# Particle system
MAX_PARTICLES = 500
PARTICLE_LIFE_BASE = 120
PARTICLE_SPEED_BASE = 3.0

# Ring visualization
RING_COUNT_BASE = 5
RING_THICKNESS_BASE = 3.0

# File formats
SUPPORTED_FORMATS = [".mp3", ".flac", ".wav", ".m4a", ".ogg", ".aac"]
