"""
Visual themes and styling.
"""
import colorsys
import math
from typing import Dict, List, Tuple

import numpy as np

from ..analysis.features import GlobalFeatureSet

ColorRGB = Tuple[int, int, int]

ROLE_ALIASES = {
    "background_base": "background_base",
    "background_fog": "background_fog",
    "background_halo": "background_halo",
    "foreground_primary": "foreground_primary",
    "foreground_secondary": "foreground_secondary",
    "accent": "accent",
    "grid_line": "grid_line",
    "grid_glow": "grid_glow",
    "hud_text": "hud_text",
    "title_text": "title_text",
    "core": "foreground_primary",
    "primary": "foreground_primary",
    "secondary": "foreground_secondary",
    "grid": "grid_line",
    "hud": "hud_text",
    "title": "title_text",
}

def _clamp(v: float, low: float, high: float) -> float:
    return max(low, min(high, v))

def _mix_channel(a: int, b: int, t: float) -> int:
    return int(round(a + (b - a) * _clamp(t, 0.0, 1.0)))

def scale_color(color: ColorRGB, factor: float, min_v: int = 0, max_v: int = 255) -> ColorRGB:
    f = _clamp(factor, 0.0, 5.0)
    return (
        int(_clamp(color[0] * f, min_v, max_v)),
        int(_clamp(color[1] * f, min_v, max_v)),
        int(_clamp(color[2] * f, min_v, max_v)),
    )

def hsl_to_rgb(h: float, s: float, l: float) -> ColorRGB:
    """Convert HSL (h in degrees 0-360, s 0-1, l 0-1) to RGB 0-255."""
    h_norm = (h % 360.0) / 360.0
    r, g, b = colorsys.hls_to_rgb(h_norm, _clamp(l, 0, 1), _clamp(s, 0, 1))
    return int(r * 255), int(g * 255), int(b * 255)

def rgb_to_hsl(color: ColorRGB) -> Tuple[float, float, float]:
    r, g, b = (channel / 255.0 for channel in color)
    h, l, s = colorsys.rgb_to_hls(r, g, b)
    return h * 360.0, s, l

def hex_to_rgb(hex_str: str) -> ColorRGB:
    hex_str = hex_str.lstrip("#")
    return tuple(int(hex_str[i : i + 2], 16) for i in (0, 2, 4))

SCIENTIFIC_PALETTE_BANKS: Dict[str, List[str]] = {
    # Deep Oceanic / Midnight (Premium Dark)
    "midnight_depth": ["#0F172A", "#1E293B", "#334155", "#0EA5E9", "#38BDF8"],
    # Space Nebula (Rich Purple/Gold)
    "space_nebula": ["#0F0A1F", "#2D1B4D", "#5B21B6", "#F59E0B", "#FCD34D"],
    # Viridian Forest (Deep Green/Teal)
    "viridian_edge": ["#064E3B", "#065F46", "#10B981", "#34D399", "#A7F3D0"],
    # Rose Gold / Sunset (Elegant Warm)
    "rose_sunset": ["#451A03", "#78350F", "#B45309", "#F59E0B", "#FB923C"],
    # Arctic / Glass (Clean Minimalist)
    "arctic_aura": ["#F8FAFC", "#F1F5F9", "#CBD5E1", "#94A3B8", "#64748B"],
    # Royal Amethyst (Luxury Purple)
    "royal_monarch": ["#2E1065", "#4C1D95", "#8B5CF6", "#A78BFA", "#DDD6FE"],
}

SCIENTIFIC_FAMILY_ORDER = [
    "midnight_depth",
    "space_nebula",
    "viridian_edge",
    "rose_sunset",
    "royal_monarch",
    "arctic_aura",
]

def interpolate_colors(c1: ColorRGB, c2: ColorRGB, t: float) -> ColorRGB:
    t = _clamp(t, 0, 1)
    return (
        _mix_channel(c1[0], c2[0], t),
        _mix_channel(c1[1], c2[1], t),
        _mix_channel(c1[2], c2[2], t)
    )

def mix_colors(colors: List[ColorRGB], weights: List[float]) -> ColorRGB:
    total = max(sum(max(0.0, w) for w in weights), 1e-6)
    r = sum(color[0] * max(0.0, weight) for color, weight in zip(colors, weights)) / total
    g = sum(color[1] * max(0.0, weight) for color, weight in zip(colors, weights)) / total
    b = sum(color[2] * max(0.0, weight) for color, weight in zip(colors, weights)) / total
    return int(_clamp(r, 0, 255)), int(_clamp(g, 0, 255)), int(_clamp(b, 0, 255))

def sample_palette_color(hex_colors: List[str], position: float) -> ColorRGB:
    size = len(hex_colors)
    if size == 1:
        return hex_to_rgb(hex_colors[0])
    pos = position % size
    idx0 = int(math.floor(pos))
    idx1 = (idx0 + 1) % size
    return interpolate_colors(hex_to_rgb(hex_colors[idx0]), hex_to_rgb(hex_colors[idx1]), pos - idx0)

def tune_color(
    color: ColorRGB,
    *,
    hue_shift: float = 0.0,
    saturation_scale: float = 1.0,
    lightness_shift: float = 0.0,
) -> ColorRGB:
    hue, saturation, lightness = rgb_to_hsl(color)
    return hsl_to_rgb(
        hue + hue_shift,
        _clamp(saturation * saturation_scale, 0.0, 1.0),
        _clamp(lightness + lightness_shift, 0.0, 1.0),
    )

def with_floor(color: ColorRGB, floor: int = 12, ceiling: int = 255) -> ColorRGB:
    return (
        int(_clamp(color[0], floor, ceiling)),
        int(_clamp(color[1], floor, ceiling)),
        int(_clamp(color[2], floor, ceiling)),
    )

def lift_towards(color: ColorRGB, target: ColorRGB, amount: float) -> ColorRGB:
    return interpolate_colors(color, target, _clamp(amount, 0.0, 1.0))

class Theme:
    """Visual theme configuration representing a song's Visual DNA with Scientific Precision."""

    def __init__(self, name: str, features: GlobalFeatureSet):
        self.name = name
        self.features = features

        self.structure_type = features.structure_type
        self.detail_style = features.detail_style
        self.motion_profile = getattr(
            features, "motion_性格", getattr(features, "motion_鎬ф牸", "steady"),
        )
        self.palette_type = features.palette_type

        # Base DNA
        self.hue_base = features.theme_hue_base
        self.saturation = features.theme_saturation
        self.brightness = features.theme_brightness
        
        # Refined Effect Multipliers (Elegant, not flashy)
        self.ring_count = int(np.clip(features.ring_count + 1, 5, 8))
        self.line_thickness = features.line_thickness * 1.0

        self.show_rings = True
        self.show_particles = True
        self.show_beat_flash = True

        self.palette_blend_ratio = 0.0
        self.palette_blend_family = ""
        self.colors = self._generate_scientific_palette()

    def _generate_scientific_palette(self) -> Dict[str, ColorRGB]:
        """Procedurally generate a large scientific-inspired palette space from hex seeds."""
        f = self.features

        chroma = np.asarray(getattr(f, "chroma_vector", np.ones(12) / 12.0), dtype=float)
        if chroma.size != 12 or float(chroma.sum()) <= 1e-6:
            chroma = np.ones(12, dtype=float) / 12.0
        else:
            chroma = chroma / float(chroma.sum())

        chroma_peak = int(np.argmax(chroma))
        chroma_center = float(np.dot(chroma, np.arange(12)))
        families = SCIENTIFIC_FAMILY_ORDER

        family_pos = (
            (f.theme_hue_base / 360.0) * len(families)
            + f.energy * 1.6
            + f.brightness * 1.1
            + chroma_peak * 0.18
        ) % len(families)
        family_idx = int(family_pos) % len(families)
        blend_idx = (family_idx + 1 + int(f.chaos * 2.0 + f.density * 1.6)) % len(families)
        accent_idx = (blend_idx + 2 + int(f.high_ratio * 2.0 + f.warmth * 1.5)) % len(families)

        primary_family = families[family_idx]
        blend_family = families[blend_idx]
        accent_family = families[accent_idx]

        primary_pos = (
            chroma_center * 0.21
            + f.tempo / 57.0
            + f.energy * 2.4
            + f.bass_ratio * 1.8
        )
        secondary_pos = primary_pos + 0.9 + f.brightness * 2.1 + f.high_ratio * 0.8
        accent_pos = primary_pos + 1.7 + f.chaos * 2.5 + f.warmth * 1.4

        seed_primary = sample_palette_color(SCIENTIFIC_PALETTE_BANKS[primary_family], primary_pos)
        seed_secondary = sample_palette_color(SCIENTIFIC_PALETTE_BANKS[blend_family], secondary_pos)
        seed_accent = sample_palette_color(SCIENTIFIC_PALETTE_BANKS[accent_family], accent_pos)

        blend_t = _clamp(0.16 + f.energy * 0.28 + f.chaos * 0.20, 0.10, 0.62)
        accent_t = _clamp(0.10 + f.brightness * 0.22 + f.high_ratio * 0.20, 0.08, 0.46)

        # --- NEW COORDINATION LOGIC ---
        # 1. Primary anchored to the strongest chroma/seed
        primary_rgb = tune_color(
            seed_primary,
            hue_shift=(f.high_ratio - f.bass_ratio) * 15.0,
            saturation_scale=1.1 + f.spectral_contrast * 0.2,
            lightness_shift=0.02 + f.brightness * 0.05,
        )

        # 2. Secondary is Analogous (+30 to +60) - provides harmony
        secondary_rgb = tune_color(
            seed_secondary,
            hue_shift=45.0 + f.energy * 15.0,
            saturation_scale=0.85 + f.energy * 0.15,
            lightness_shift=-0.05, # Darker than primary for depth
        )

        # 3. Accent is SPLIT-COMPLEMENTARY (+155) - provides interest and variety without clashing
        accent_rgb = tune_color(
            seed_accent,
            hue_shift=155.0 + f.chaos * 20.0, 
            saturation_scale=1.3 + f.energy * 0.2,
            lightness_shift=0.08 + f.brightness * 0.08, # Pop out!
        )

        lab_navy = hex_to_rgb("#08111D")
        lab_slate = hex_to_rgb("#132238")
        bg_tint = tune_color(
            mix_colors(
                [primary_rgb, secondary_rgb, seed_secondary],
                [0.62, 0.38, 0.22 + f.chaos * 0.16],
            ),
            hue_shift=-12.0 + (f.high_ratio - f.warmth) * 18.0,
            saturation_scale=0.42 + f.energy * 0.12,
            lightness_shift=-0.24 + f.brightness * 0.02,
        )
        background_base = with_floor(
            mix_colors(
                [lab_navy, lab_slate, bg_tint],
                [1.0, 0.74, 0.42 + f.energy * 0.22],
            ),
            floor=10,
            ceiling=78,
        )
        background_fog = with_floor(
            tune_color(
                mix_colors(
                    [background_base, secondary_rgb, accent_rgb],
                    [1.0, 0.38 + f.brightness * 0.18, 0.18 + f.high_ratio * 0.12],
                ),
                saturation_scale=0.84,
                lightness_shift=0.08 + f.brightness * 0.03,
            ),
            floor=18,
            ceiling=120,
        )
        background_halo = with_floor(
            tune_color(
                mix_colors(
                    [primary_rgb, accent_rgb, secondary_rgb],
                    [0.72, 0.60 + f.energy * 0.20, 0.20],
                ),
                saturation_scale=0.96 + f.energy * 0.08,
                lightness_shift=-0.06 + f.brightness * 0.02,
            ),
            floor=28,
            ceiling=168,
        )

        grid_line = with_floor(
            lift_towards(background_fog, secondary_rgb, 0.26 + f.energy * 0.10),
            floor=30,
            ceiling=170,
        )
        grid_glow = with_floor(
            lift_towards(background_halo, accent_rgb, 0.40 + f.high_ratio * 0.12),
            floor=42,
            ceiling=220,
        )
        hud_text = with_floor(
            mix_colors([hex_to_rgb("#D6DFEA"), secondary_rgb], [1.0, 0.18]),
            floor=170,
            ceiling=244,
        )
        title_text = with_floor(
            mix_colors([hex_to_rgb("#F6FAFF"), accent_rgb], [1.0, 0.12]),
            floor=220,
            ceiling=255,
        )

        colors = {
            "background_base": background_base,
            "background_fog": background_fog,
            "background_halo": background_halo,
            "foreground_primary": with_floor(primary_rgb, floor=42, ceiling=235),
            "foreground_secondary": with_floor(secondary_rgb, floor=40, ceiling=225),
            "accent": with_floor(accent_rgb, floor=96, ceiling=255),
            "grid_line": grid_line,
            "grid_glow": grid_glow,
            "hud_text": hud_text,
            "title_text": title_text,
        }

        self.palette_family = primary_family
        self.palette_blend_family = blend_family
        self.palette_blend_ratio = blend_t

        print(
            "[VisualDNA] Scientific Palette: "
            f"{self.palette_family} + {self.palette_blend_family}({self.palette_blend_ratio:.2f}) "
            f"| Primary={colors['foreground_primary']} Accent={colors['accent']}"
        )
        return colors

    def get_color(self, role: str, alpha: float = 1.0) -> Tuple[int, int, int, int]:
        if isinstance(role, int):
            keys = list(self.colors.keys())
            r, g, b = self.colors[keys[role % len(keys)]]
            return (r, g, b, int(_clamp(alpha, 0.0, 1.0) * 255))

        key = ROLE_ALIASES.get(role, role)
        if key not in self.colors:
            key = "foreground_primary"

        r, g, b = self.colors[key]
        return (r, g, b, int(_clamp(alpha, 0.0, 1.0) * 255))

    def __repr__(self):
        return f"VisualDNA({self.name}, hue={self.hue_base:.1f}, type={self.palette_type})"

def create_theme_from_features(features: GlobalFeatureSet) -> Theme:
    return Theme(name=f"dna_h{int(features.theme_hue_base)}", features=features)

def get_theme(name: str) -> Theme:
    return create_theme_from_features(GlobalFeatureSet.compute_defaults())
