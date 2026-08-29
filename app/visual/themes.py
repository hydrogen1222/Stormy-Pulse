"""
Visual themes and styling.
"""
import colorsys
import math
from typing import Dict, List, Optional, Tuple

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

def blackbody_radiation_color(temp_k: float) -> ColorRGB:
    """Convert Kelvin temperature (1000K-15000K) to RGB color along Planckian Locus."""
    temp = _clamp(temp_k, 1000.0, 15000.0) / 100.0
    if temp <= 66.0:
        r = 255.0
        g = _clamp(99.4708025861 * math.log(temp) - 161.1195681661, 0.0, 255.0)
        b = 0.0 if temp <= 19.0 else _clamp(138.5177312231 * math.log(temp - 10.0) - 305.0447927307, 0.0, 255.0)
    else:
        r = _clamp(329.698727446 * ((temp - 60.0) ** -0.1332047592), 0.0, 255.0)
        g = _clamp(288.1221695283 * ((temp - 60.0) ** -0.0755148492), 0.0, 255.0)
        b = 255.0
    return (int(r), int(g), int(b))

SCIENTIFIC_PALETTE_BANKS: Dict[str, List[str]] = {
    "amber_ignition": ["#1C1005", "#451A03", "#78350F", "#D97706", "#FDE68A"],
    "royal_amethyst": ["#1A0B2E", "#2E1065", "#5B21B6", "#A78BFA", "#F3E8FF"],
    "emerald_dusk": ["#022C22", "#064E3B", "#059669", "#34D399", "#A7F3D0"],
    "rose_nebula": ["#2A0815", "#4C0519", "#9F1239", "#FB7185", "#FFE4E6"],
    "obsidian_gold": ["#0C0A09", "#1C1917", "#44403C", "#D97706", "#FEF08A"],
    "midnight_depth": ["#0B1329", "#0F172A", "#1E293B", "#0EA5E9", "#E0F2FE"],
    "aurora_teal": ["#042F2E", "#0F766E", "#14B8A6", "#5EEAD4", "#E6FFFA"],
    "cyberpunk_neon": ["#18181B", "#27272A", "#86198F", "#D946EF", "#38BDF8"],
}

SCIENTIFIC_FAMILY_ORDER = [
    "amber_ignition",
    "royal_amethyst",
    "emerald_dusk",
    "rose_nebula",
    "obsidian_gold",
    "midnight_depth",
    "aurora_teal",
    "cyberpunk_neon",
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

class DrawPlan:
    """Deterministic layer composition recipe for distinct visual archetypes."""

    def __init__(self, structure_type: str, seed: int):
        self.structure_type = (structure_type or "pulse").lower()
        self.seed = int(seed)

        # Seed-based variation
        self.polygon_sides = 5 + (self.seed % 4) # 5, 6, 7, 8 sides
        self.arm_count = 4 + ((self.seed >> 2) % 4) # 4, 5, 6, 7 arms

        self.show_optical_core = True
        self.show_vortex_atmosphere = False
        self.show_rings = True
        self.show_angular_reactor = False
        self.show_organic_membranes = False

        self.core_shape = "circle"
        self.ring_geometry_mode = "concentric"
        self.particle_flow_mode = "radial"

        if self.structure_type == "pulse":
            self.show_optical_core = True
            self.show_vortex_atmosphere = False
            self.show_rings = True
            self.core_shape = "circle"
            self.ring_geometry_mode = "concentric"
            self.particle_flow_mode = "radial"
        elif self.structure_type == "vortex":
            self.show_optical_core = False
            self.show_vortex_atmosphere = True
            self.show_rings = False
            self.core_shape = "vortex_eye"
            self.ring_geometry_mode = "spiral"
            self.particle_flow_mode = "vortex_spiral"
        elif self.structure_type == "reactor":
            self.show_optical_core = False
            self.show_vortex_atmosphere = False
            self.show_angular_reactor = True
            self.show_rings = False
            self.core_shape = "polygon"
            self.ring_geometry_mode = "orbital_polygon"
            self.particle_flow_mode = "reactor_jets"
        elif self.structure_type == "organic":
            self.show_optical_core = False
            self.show_vortex_atmosphere = False
            self.show_organic_membranes = True
            self.show_rings = False
            self.core_shape = "asymmetric_cell"
            self.ring_geometry_mode = "fluid_wave"
            self.particle_flow_mode = "cellular_drift"

    def active_layers(self) -> tuple[str, ...]:
        """Return tuple of active layer names for layer set uniqueness testing."""
        layers = []
        if self.show_vortex_atmosphere:
            layers.append("vortex_atmosphere")
        else:
            layers.append(f"atmosphere_{self.structure_type}")

        if self.show_optical_core:
            layers.append("optical_core")
        else:
            layers.append(f"core_{self.core_shape}")

        if self.show_angular_reactor:
            layers.append("angular_reactor_lattice")
        elif self.show_organic_membranes:
            layers.append("organic_membranes")

        if self.show_rings:
            layers.append(f"rings_{self.ring_geometry_mode}")

        layers.append(f"particles_{self.particle_flow_mode}")
        return tuple(layers)


def relative_luminance(rgb: ColorRGB) -> float:
    """Calculate WCAG relative luminance for an RGB tuple (0-255)."""
    def adj(c):
        cn = c / 255.0
        return cn / 12.92 if cn <= 0.03928 else ((cn + 0.055) / 1.055) ** 2.4
    return 0.2126 * adj(rgb[0]) + 0.7152 * adj(rgb[1]) + 0.0722 * adj(rgb[2])


def contrast_ratio(c1: ColorRGB, c2: ColorRGB) -> float:
    """Calculate WCAG contrast ratio between two RGB colors (>= 1.0)."""
    l1 = relative_luminance(c1)
    l2 = relative_luminance(c2)
    return (max(l1, l2) + 0.05) / (min(l1, l2) + 0.05)


def is_red_green_clash(primary: ColorRGB, secondary: ColorRGB, accent: ColorRGB) -> bool:
    """Check if any pair among primary, secondary, and accent forms a high-sat red-green clash."""
    def is_red(rgb):
        h, s, _ = rgb_to_hsl(rgb)
        return (h <= 25 or h >= 335) and s > 0.45

    def is_green(rgb):
        h, s, _ = rgb_to_hsl(rgb)
        return (75 <= h <= 165) and s > 0.45

    roles = [primary, secondary, accent]
    has_red = any(is_red(c) for c in roles)
    has_green = any(is_green(c) for c in roles)
    return has_red and has_green


def apply_color_clash_guard(
    primary: ColorRGB,
    secondary: ColorRGB,
    accent: ColorRGB,
    background_fog: ColorRGB,
    hud_text: ColorRGB,
) -> Tuple[ColorRGB, ColorRGB, ColorRGB, ColorRGB, ColorRGB]:
    """Enforce harmony: no high-sat red+green clash, HUD text contrast >= 4.5:1."""
    if is_red_green_clash(primary, secondary, accent):
        # Shift secondary or accent green to cyan/emerald to harmonize
        h_s, s_s, l_s = rgb_to_hsl(secondary)
        if 75 <= h_s <= 165:
            secondary = hsl_to_rgb(185.0, min(s_s, 0.45), l_s)

        h_a, s_a, l_a = rgb_to_hsl(accent)
        if 75 <= h_a <= 165:
            accent = hsl_to_rgb(195.0, min(s_a, 0.55), l_a)

        h_p, s_p, l_p = rgb_to_hsl(primary)
        if 75 <= h_p <= 165:
            primary = hsl_to_rgb(210.0, min(s_p, 0.45), l_p)

    if contrast_ratio(hud_text, background_fog) < 4.5:
        hud_text = (241, 245, 249)

    return primary, secondary, accent, background_fog, hud_text


class Theme:
    """Visual theme configuration representing a song's Visual DNA with Scientific Precision."""

    def __init__(self, name: str, features: GlobalFeatureSet, track_seed: int = 0):
        self.name = name
        self.features = features
        self.track_seed = int(track_seed) if track_seed != 0 else int(features.theme_hue_base * 100)

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
        
        # Refined Effect Multipliers
        self.ring_count = int(np.clip(features.ring_count + 1, 5, 8))
        self.line_thickness = features.line_thickness * 1.0

        self.show_rings = True
        self.show_particles = True
        self.show_beat_flash = True

        self.draw_plan = DrawPlan(self.structure_type, self.track_seed)

        self.palette_blend_ratio = 0.0
        self.palette_blend_family = ""
        self.colors = self._generate_scientific_palette()

    def _generate_scientific_palette(self) -> Dict[str, ColorRGB]:
        """Generate single-family coordinated palette space without cross-family hue shifts."""
        f = self.features
        families = SCIENTIFIC_FAMILY_ORDER

        family_idx = (self.track_seed + int(f.theme_hue_base / 45.0)) % len(families)
        primary_family = families[family_idx]

        hex_tuple = SCIENTIFIC_PALETTE_BANKS[primary_family]
        background_base = hex_to_rgb(hex_tuple[0])
        background_fog = hex_to_rgb(hex_tuple[1])
        background_halo = hex_to_rgb(hex_tuple[2])
        primary_rgb = hex_to_rgb(hex_tuple[2])
        secondary_rgb = hex_to_rgb(hex_tuple[3])
        accent_rgb = hex_to_rgb(hex_tuple[4])

        grid_line = lift_towards(background_fog, secondary_rgb, 0.30)
        grid_glow = lift_towards(background_halo, accent_rgb, 0.45)
        hud_text = hex_to_rgb("#E2E8F0")
        title_text = hex_to_rgb("#FFFFFF")

        primary_rgb, secondary_rgb, accent_rgb, background_fog, hud_text = apply_color_clash_guard(
            primary_rgb, secondary_rgb, accent_rgb, background_fog, hud_text
        )

        colors = {
            "background_base": background_base,
            "background_fog": background_fog,
            "background_halo": background_halo,
            "foreground_primary": primary_rgb,
            "foreground_secondary": secondary_rgb,
            "accent": accent_rgb,
            "grid_line": grid_line,
            "grid_glow": grid_glow,
            "hud_text": hud_text,
            "title_text": title_text,
        }

        self.palette_family = primary_family
        self.palette_blend_family = primary_family
        self.palette_blend_ratio = 0.0
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

def create_theme_from_features(features: GlobalFeatureSet, track_seed: int = 0) -> Theme:
    return Theme(name=f"dna_h{int(features.theme_hue_base)}", features=features, track_seed=track_seed)

def get_theme(name: str) -> Theme:
    """Legacy preset-name entry point. Themes are DNA-generated, so the name is
    ignored and default features are used. Kept for backward compatibility."""
    return create_theme_from_features(GlobalFeatureSet.compute_defaults())


def apply_dna_overrides(
    features: GlobalFeatureSet,
    overrides: Optional[dict] = None,
    track_seed: int = 0,
) -> GlobalFeatureSet:
    """Return a copy of ``features`` with honest DNA overrides applied.

    Supported override keys:
      - structure:      "auto" | "pulse" | "vortex" | "reactor" | "organic"
      - palette_family: "auto" | one of SCIENTIFIC_FAMILY_ORDER
      - hue_shift:      degrees added on top of the (possibly family-forced) base hue
      - energy / chaos / brightness: floats in [0, 1]

    The palette family selection in Theme is ``(track_seed + int(hue/45)) % N``;
    forcing a family solves for the hue that lands on the requested family.
    """
    from dataclasses import replace

    if not overrides:
        return features

    updates: Dict[str, object] = {}

    structure = str(overrides.get("structure") or "auto")
    if structure != "auto":
        updates["structure_type"] = structure
        updates["structure_prior"] = structure

    hue = float(features.theme_hue_base)
    family = str(overrides.get("palette_family") or "auto")
    if family != "auto" and family in SCIENTIFIC_FAMILY_ORDER:
        # Forcing a family is authoritative; hue_shift is ignored in this mode
        # because hue and family are coupled through the palette formula.
        n = len(SCIENTIFIC_FAMILY_ORDER)
        target = SCIENTIFIC_FAMILY_ORDER.index(family)
        seed_mod = int(track_seed) % n
        k = (target - seed_mod) % n
        hue = 45.0 * k + 22.5
    else:
        hue_shift = float(overrides.get("hue_shift") or 0.0)
        hue = (hue + hue_shift) % 360.0

    if abs(hue - float(features.theme_hue_base)) > 1e-6:
        updates["theme_hue_base"] = hue

    for key in ("energy", "chaos", "brightness"):
        value = overrides.get(key)
        if value is not None:
            updates[key] = _clamp(float(value), 0.0, 1.0)

    if not updates:
        return features
    return replace(features, **updates)
