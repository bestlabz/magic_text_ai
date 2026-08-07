#!/usr/bin/env python3
"""Magic Write text-style generator.

Input text is matched against a bundled local style dataset and rule-based
style engine. The selected styles are sanitized into the Konva-compatible Text
object shape used by the card editor, and each object is rendered into a small
PNG data URI for preview_image.
"""

from __future__ import annotations

import base64
import io
import json
import math
import os
import random
import re
import ssl
import sys
import urllib.error
import urllib.parse
import urllib.request
import uuid
from copy import deepcopy
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw, ImageFilter, ImageFont

PROJECT_DIR = Path(__file__).resolve().parent


def _load_local_env() -> None:
    env_path = PROJECT_DIR / ".env"
    if not env_path.exists():
        return
    try:
        lines = env_path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return
    for line in lines:
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


_load_local_env()
DEFAULT_CANVAS_WIDTH = 420
DEFAULT_CANVAS_HEIGHT = 420
DEFAULT_PREVIEW_SCALE = 3
LOCAL_MAGIC_WRITE_MODEL = "magic-write-local-rules-v1"
GOOGLE_FONTS_API_URL = "https://www.googleapis.com/webfonts/v1/webfonts"
GOOGLE_FONTS_API_KEY = os.environ.get("GOOGLE_FONTS_API_KEY", "")
HEX_RE = re.compile(r"^#[0-9A-Fa-f]{6}$")
GOOGLE_FONT_URL_RE = re.compile(r"url\((https://fonts\.gstatic\.com/[^)]+\.ttf)\)")
GOOGLE_FONT_UA = "Mozilla/5.0 (Windows NT 5.1; rv:1.0)"
_google_font_network_ok = True
MAGIC_WRITE_DATASET_VERSION = "2026.08.05-modern-v1"

try:
    import certifi
    SSL_CONTEXT = ssl.create_default_context(cafile=certifi.where())
except ImportError:
    SSL_CONTEXT = None

FONT_CACHE_DIRS = [
    PROJECT_DIR / ".font_cache",
]
PRIMARY_FONT_CACHE_DIR = FONT_CACHE_DIRS[0]
GOOGLE_FONTS_CACHE_PATH = PRIMARY_FONT_CACHE_DIR / "google_fonts_families.json"
MAC_FONT_DIR = Path("/System/Library/Fonts/Supplemental")
MAC_CORE_FONT_DIR = Path("/System/Library/Fonts")
LINUX_FONT_DIRS = [
    Path("/usr/share/fonts/truetype/dejavu"),
    Path("/usr/share/fonts/truetype/liberation2"),
    Path("/usr/share/fonts/truetype/liberation"),
]

FONT_FILES = {
    "arial": "Arial.ttf",
    "arial bold": "Arial Bold.ttf",
    "georgia": "Georgia.ttf",
    "georgia bold": "Georgia Bold.ttf",
    "impact": "Impact.ttf",
    "times new roman": "Times New Roman.ttf",
    "courier new": "Courier New.ttf",
    "snell roundhand": "SnellRoundhand.ttc",
    "brush script": "Brush Script.ttf",
    "chalkboard": "Chalkboard.ttc",
}

CANVA_FONT_FAMILIES = [
    "Goldman",
    "Great Vibes",
    "Montserrat",
    "Poppins",
    "Playfair Display",
    "Cinzel",
    "Cormorant Garamond",
    "Dancing Script",
    "Pacifico",
    "Lobster",
    "Bebas Neue",
    "Anton",
    "Abril Fatface",
    "Oswald",
    "Raleway",
    "League Spartan",
    "Lato",
    "Merriweather",
    "Josefin Sans",
    "Bodoni 72",
    "Georgia",
    "Arial",
    "Impact",
    "Times New Roman",
    "Courier New",
    "Snell Roundhand",
    "Brush Script",
    "Chalkboard",
]

FONT_KIND_ORDER = ["script", "serif", "display", "sans", "mono", "decorative"]

CANVA_FONT_GROUPS = {
    "script": [
        "Great Vibes",
        "Dancing Script",
        "Pacifico",
        "Lobster",
        "Satisfy",
        "Yellowtail",
        "Courgette",
        "Sacramento",
        "Allura",
        "Parisienne",
        "Snell Roundhand",
        "Brush Script",
    ],
    "serif": [
        "Playfair Display",
        "Cinzel",
        "Cormorant Garamond",
        "Merriweather",
        "Abril Fatface",
        "Bodoni 72",
        "Libre Baskerville",
        "Cormorant",
        "Prata",
        "DM Serif Display",
        "Georgia",
        "Times New Roman",
    ],
    "display": [
        "Goldman",
        "Bebas Neue",
        "Anton",
        "League Spartan",
        "Oswald",
        "Bungee",
        "Righteous",
        "Fredoka One",
        "Alfa Slab One",
        "Archivo Black",
        "Impact",
        "Chalkboard",
    ],
    "sans": [
        "Montserrat",
        "Poppins",
        "Raleway",
        "Lato",
        "Josefin Sans",
        "Nunito",
        "Open Sans",
        "Roboto",
        "Inter",
        "Quicksand",
        "Arial",
    ],
    "mono": [
        "Courier Prime",
        "Roboto Mono",
        "Space Mono",
        "IBM Plex Mono",
        "Courier New",
    ],
    "decorative": [
        "Monoton",
        "Faster One",
        "Rubik Moonrocks",
        "Bungee Shade",
        "Ewert",
        "Rye",
    ],
}

CANVA_FONT_FAMILIES = [
    family
    for kind in FONT_KIND_ORDER
    for family in CANVA_FONT_GROUPS.get(kind, [])
]

DESIGN_PALETTES = [
    {"fill": "#111111", "stroke": "", "shadowColor": ""},
    {"fill": "#D8A919", "stroke": "", "shadowColor": "#E8D187", "accentFill": "#D8A919"},
    {"fill": "#FF6F72", "stroke": "#FFF0CB", "shadowColor": "#FFB0A6", "accentFill": "#FF6F72"},
    {"fill": "#1B45F5", "stroke": "#31FF38", "shadowColor": "", "accentFill": "#31FF38"},
    {"fill": "#FF5BB4", "stroke": "#FF8BD0", "shadowColor": "#FF44B0", "accentFill": "#FF8BD0"},
    {"fill": "#0F6B5B", "stroke": "", "shadowColor": "#CFF7E4", "accentFill": "#0F6B5B"},
    {"fill": "#F56C2D", "stroke": "#FFE6A7", "shadowColor": "#2EC4B6", "accentFill": "#2EC4B6"},
    {"fill": "#FFFFFF", "stroke": "#8B7DFF", "shadowColor": "#8179FF", "accentFill": "#8B7DFF"},
    {"fill": "#EF4E56", "stroke": "#EF4E56", "shadowColor": "", "accentFill": "#EF4E56"},
    {"fill": "#23B7E5", "stroke": "", "shadowColor": "#FF7A22", "accentFill": "#FF7A22"},
    {"fill": "#8A8A8A", "stroke": "", "shadowColor": "#CFCFCF", "accentFill": "#55E0B4"},
    {"fill": "#B64040", "stroke": "", "shadowColor": "", "accentFill": "#B64040"},
    {"fill": "#101010", "stroke": "#FFFFFF", "shadowColor": "#DADDE5", "accentFill": "#101010"},
    {"fill": "#FFF7A8", "stroke": "#F4C430", "shadowColor": "#FF6B6B", "accentFill": "#F4C430"},
    {"fill": "#B76E79", "stroke": "#F7D9D9", "shadowColor": "#6B2F38", "accentFill": "#B76E79"},
    {"fill": "#4CC9F0", "stroke": "#FFFFFF", "shadowColor": "#4361EE", "accentFill": "#4361EE"},
]

DESIGN_EFFECTS = [
    {"suffix": "clean", "strokeWidth": 0, "shadowBlur": 0, "shadowOffsetX": 0, "shadowOffsetY": 0, "textDecoration": "", "letterSpacing": 0, "rotation": 0},
    {"suffix": "outline", "strokeWidth": 2.6, "shadowBlur": 0, "shadowOffsetX": 0, "shadowOffsetY": 0, "textDecoration": "", "letterSpacing": 0.8, "rotation": 0},
    {"suffix": "soft_shadow", "strokeWidth": 0, "shadowBlur": 0, "shadowOffsetX": 3.5, "shadowOffsetY": 4, "textDecoration": "", "letterSpacing": 0, "rotation": 0},
    {"suffix": "neon", "strokeWidth": 1.2, "shadowBlur": 13, "shadowOffsetX": 0, "shadowOffsetY": 0, "textDecoration": "", "letterSpacing": 0, "rotation": 0},
    {"suffix": "sticker", "strokeWidth": 4.0, "shadowBlur": 0, "shadowOffsetX": 2.5, "shadowOffsetY": 3.5, "textDecoration": "", "letterSpacing": 0.2, "rotation": -2},
    {"suffix": "stamp", "strokeWidth": 1.4, "shadowBlur": 0, "shadowOffsetX": 0, "shadowOffsetY": 0, "textDecoration": "underline", "letterSpacing": 1.4, "rotation": 0},
    {"suffix": "offset_pop", "strokeWidth": 2.0, "shadowBlur": 0, "shadowOffsetX": -4, "shadowOffsetY": -3, "textDecoration": "", "letterSpacing": 0, "rotation": 2},
    {"suffix": "editorial", "strokeWidth": 0, "shadowBlur": 1.4, "shadowOffsetX": 1, "shadowOffsetY": 1, "textDecoration": "", "letterSpacing": 1.8, "rotation": 0},
    {"suffix": "italic_mark", "strokeWidth": 0, "shadowBlur": 0, "shadowOffsetX": 0, "shadowOffsetY": 0, "textDecoration": "", "letterSpacing": -0.2, "rotation": -3},
    {"suffix": "bold_block", "strokeWidth": 0, "shadowBlur": 0, "shadowOffsetX": 0, "shadowOffsetY": 0, "textDecoration": "", "letterSpacing": 2.2, "rotation": 0},
]

MODERN_COMPOSITION_PALETTES = [
    {"name": "modern_ink_coral", "primary": "#101114", "secondary": "#FF4F61", "accent": "#FFE6DD", "light": "#FFFFFF", "shadow": "#BFC6D1", "glow": "#FF8C98"},
    {"name": "modern_gold_luxe", "primary": "#C99718", "secondary": "#5D4714", "accent": "#F5D66B", "light": "#FFF7D8", "shadow": "#9C771E", "glow": "#FFE58A"},
    {"name": "modern_candy_pop", "primary": "#FF6874", "secondary": "#FFF0DC", "accent": "#FFB0A8", "light": "#FFFFFF", "shadow": "#FF7E8D", "glow": "#FFA9B8"},
    {"name": "modern_soft_rose", "primary": "#B8BEC9", "secondary": "#FF4D60", "accent": "#FFFFFF", "light": "#FFFFFF", "shadow": "#FF596A", "glow": "#FFB4BF"},
    {"name": "modern_neon_pink", "primary": "#FF4FB3", "secondary": "#FF8AD7", "accent": "#FFFFFF", "light": "#FFEAF7", "shadow": "#C52783", "glow": "#FF7BCF"},
    {"name": "modern_teal_cutout", "primary": "#139B83", "secondary": "#FFFFFF", "accent": "#DDFCF5", "light": "#FFFFFF", "shadow": "#0E6E5E", "glow": "#91FFE9"},
    {"name": "ruby_mint", "primary": "#EF3F4F", "secondary": "#199B72", "accent": "#F6B7D8", "light": "#FFFFFF", "shadow": "#197C68", "glow": "#F89BB7"},
    {"name": "royal_gold", "primary": "#D6A816", "secondary": "#1E3158", "accent": "#F3D46B", "light": "#FFF8DB", "shadow": "#A3832C", "glow": "#FFE083"},
    {"name": "aqua_orange", "primary": "#20A9D6", "secondary": "#FF7A21", "accent": "#FFE2A8", "light": "#FFFFFF", "shadow": "#137897", "glow": "#7EE6FF"},
    {"name": "violet_lime", "primary": "#755CFF", "secondary": "#A6FF4D", "accent": "#EF9AFF", "light": "#FFFFFF", "shadow": "#4C3AD1", "glow": "#BFB7FF"},
    {"name": "ink_blush", "primary": "#1A1A1A", "secondary": "#CF4A61", "accent": "#FFD1DA", "light": "#FFFFFF", "shadow": "#9C3145", "glow": "#FF9FB0"},
    {"name": "forest_ivory", "primary": "#0E5436", "secondary": "#C8902E", "accent": "#F3E4BA", "light": "#FFFDF4", "shadow": "#123F2C", "glow": "#FFE6A8"},
    {"name": "blue_coral", "primary": "#1F5BFF", "secondary": "#FF595E", "accent": "#80ED99", "light": "#FFFFFF", "shadow": "#183FAE", "glow": "#91B3FF"},
    {"name": "magenta_sky", "primary": "#F041A3", "secondary": "#35B8EA", "accent": "#FFE766", "light": "#FFFFFF", "shadow": "#A72770", "glow": "#FF9BDA"},
    {"name": "charcoal_teal", "primary": "#2A2D34", "secondary": "#00A896", "accent": "#F9C74F", "light": "#FFFFFF", "shadow": "#008071", "glow": "#76F2E5"},
    {"name": "brick_cream", "primary": "#B64040", "secondary": "#264653", "accent": "#E9C46A", "light": "#FFF4E6", "shadow": "#7A2929", "glow": "#FFD58C"},
    {"name": "hotpink_yellow", "primary": "#FF4FB3", "secondary": "#FFD23F", "accent": "#31D6C4", "light": "#FFFFFF", "shadow": "#C22B80", "glow": "#FF99D6"},
    {"name": "navy_lavender", "primary": "#113A7A", "secondary": "#BCA7FF", "accent": "#42D9C8", "light": "#FFFFFF", "shadow": "#0A2550", "glow": "#CFC3FF"},
    {"name": "emerald_pink", "primary": "#057A55", "secondary": "#FF6F91", "accent": "#FEE440", "light": "#FFFFFF", "shadow": "#034E37", "glow": "#8FFFE0"},
    {"name": "cobalt_peach", "primary": "#0057B8", "secondary": "#FF9F7A", "accent": "#B8F2E6", "light": "#FFFFFF", "shadow": "#003C80", "glow": "#82C8FF"},
    {"name": "plum_citrus", "primary": "#6D326D", "secondary": "#FFB703", "accent": "#8ECAE6", "light": "#FFFFFF", "shadow": "#3F1B40", "glow": "#E6B7FF"},
    {"name": "tomato_denim", "primary": "#E63946", "secondary": "#264E86", "accent": "#A8DADC", "light": "#FFFFFF", "shadow": "#9E1F2A", "glow": "#FF9AA3"},
    {"name": "graphite_peach", "primary": "#30343F", "secondary": "#F7A072", "accent": "#71D6C3", "light": "#FFFFFF", "shadow": "#171A22", "glow": "#FFD0B8"},
    {"name": "cyan_grape", "primary": "#00B4D8", "secondary": "#7B2CBF", "accent": "#FDE74C", "light": "#FFFFFF", "shadow": "#007C96", "glow": "#8BEFFF"},
    {"name": "olive_rose", "primary": "#667B2A", "secondary": "#D1495B", "accent": "#EDA96F", "light": "#FFFDF2", "shadow": "#3F4D18", "glow": "#F8C7CF"},
    {"name": "electric_sun", "primary": "#284BFF", "secondary": "#FFDD00", "accent": "#FF4D6D", "light": "#FFFFFF", "shadow": "#182A9C", "glow": "#89A0FF"},
]

MODERN_COMPOSITION_EFFECTS = [
    {"name": "clean_display", "strokeWidth": 0, "shadowBlur": 0, "shadowOffsetX": 0, "shadowOffsetY": 0, "fillMode": "primary", "strokeMode": "", "shadowMode": ""},
    {"name": "gold_emboss", "strokeWidth": 0, "shadowBlur": 1.3, "shadowOffsetX": 1.0, "shadowOffsetY": 2.4, "fillMode": "primary", "strokeMode": "", "shadowMode": "shadow"},
    {"name": "candy_lift", "strokeWidth": 1.0, "shadowBlur": 0, "shadowOffsetX": 3.2, "shadowOffsetY": 3.8, "fillMode": "light", "strokeMode": "primary", "shadowMode": "primary"},
    {"name": "soft_marker", "strokeWidth": 0, "shadowBlur": 0, "shadowOffsetX": 2.8, "shadowOffsetY": 3.4, "fillMode": "primary", "strokeMode": "", "shadowMode": "secondary"},
    {"name": "pink_neon_bloom", "strokeWidth": 1.1, "shadowBlur": 17, "shadowOffsetX": 0, "shadowOffsetY": 0, "fillMode": "primary", "strokeMode": "secondary", "shadowMode": "glow"},
    {"name": "teal_cutout", "strokeWidth": 1.8, "shadowBlur": 0, "shadowOffsetX": 1.8, "shadowOffsetY": 2.2, "fillMode": "light", "strokeMode": "primary", "shadowMode": "shadow"},
    {"name": "solid", "strokeWidth": 0, "shadowBlur": 0, "shadowOffsetX": 0, "shadowOffsetY": 0, "fillMode": "primary", "strokeMode": "", "shadowMode": ""},
    {"name": "outline_pop", "strokeWidth": 2.3, "shadowBlur": 0, "shadowOffsetX": 2.2, "shadowOffsetY": 2.8, "fillMode": "light", "strokeMode": "secondary", "shadowMode": "accent"},
    {"name": "glow_tube", "strokeWidth": 1.4, "shadowBlur": 17, "shadowOffsetX": 0, "shadowOffsetY": 0, "fillMode": "light", "strokeMode": "accent", "shadowMode": "glow"},
    {"name": "offset_shadow", "strokeWidth": 0.8, "shadowBlur": 0, "shadowOffsetX": 3.8, "shadowOffsetY": 4.2, "fillMode": "primary", "strokeMode": "light", "shadowMode": "secondary"},
    {"name": "sticker", "strokeWidth": 3.8, "shadowBlur": 0, "shadowOffsetX": -3.0, "shadowOffsetY": 3.0, "fillMode": "accent", "strokeMode": "light", "shadowMode": "secondary"},
    {"name": "soft_depth", "strokeWidth": 0, "shadowBlur": 2.0, "shadowOffsetX": 1.4, "shadowOffsetY": 2.4, "fillMode": "primary", "strokeMode": "", "shadowMode": "shadow"},
    {"name": "reverse_outline", "strokeWidth": 2.1, "shadowBlur": 0, "shadowOffsetX": 0, "shadowOffsetY": 0, "fillMode": "light", "strokeMode": "primary", "shadowMode": ""},
    {"name": "retro_offset", "strokeWidth": 1.0, "shadowBlur": 0, "shadowOffsetX": -4.0, "shadowOffsetY": -3.0, "fillMode": "secondary", "strokeMode": "light", "shadowMode": "accent"},
    {"name": "warm_neon", "strokeWidth": 1.2, "shadowBlur": 20, "shadowOffsetX": 0, "shadowOffsetY": 0, "fillMode": "light", "strokeMode": "secondary", "shadowMode": "accent"},
    {"name": "editorial_ink", "strokeWidth": 0, "shadowBlur": 0.8, "shadowOffsetX": 1.0, "shadowOffsetY": 1.0, "fillMode": "primary", "strokeMode": "", "shadowMode": "shadow"},
    {"name": "cream_cutout", "strokeWidth": 2.8, "shadowBlur": 1.0, "shadowOffsetX": 0.8, "shadowOffsetY": 2.0, "fillMode": "light", "strokeMode": "accent", "shadowMode": "shadow"},
    {"name": "punch_shadow", "strokeWidth": 1.6, "shadowBlur": 0, "shadowOffsetX": 4.5, "shadowOffsetY": -3.5, "fillMode": "primary", "strokeMode": "accent", "shadowMode": "secondary"},
    {"name": "halo_outline", "strokeWidth": 1.8, "shadowBlur": 9.0, "shadowOffsetX": 0, "shadowOffsetY": 0, "fillMode": "primary", "strokeMode": "light", "shadowMode": "glow"},
    {"name": "glass_shadow", "strokeWidth": 1.0, "shadowBlur": 3.5, "shadowOffsetX": 2.0, "shadowOffsetY": 2.5, "fillMode": "light", "strokeMode": "primary", "shadowMode": "accent"},
    {"name": "pressed_offset", "strokeWidth": 0, "shadowBlur": 0, "shadowOffsetX": 2.5, "shadowOffsetY": -2.5, "fillMode": "secondary", "strokeMode": "", "shadowMode": "primary"},
    {"name": "fine_line", "strokeWidth": 0.7, "shadowBlur": 0, "shadowOffsetX": 0, "shadowOffsetY": 0, "fillMode": "primary", "strokeMode": "accent", "shadowMode": ""},
    {"name": "chunky_shadow", "strokeWidth": 0.5, "shadowBlur": 0, "shadowOffsetX": 5.0, "shadowOffsetY": 5.0, "fillMode": "light", "strokeMode": "primary", "shadowMode": "secondary"},
    {"name": "mist_glow", "strokeWidth": 0, "shadowBlur": 14.0, "shadowOffsetX": 0, "shadowOffsetY": 0, "fillMode": "primary", "strokeMode": "", "shadowMode": "glow"},
    {"name": "accent_edge", "strokeWidth": 1.9, "shadowBlur": 0, "shadowOffsetX": 1.0, "shadowOffsetY": 3.5, "fillMode": "secondary", "strokeMode": "accent", "shadowMode": "primary"},
    {"name": "quiet_luxe", "strokeWidth": 0.4, "shadowBlur": 1.6, "shadowOffsetX": 0.8, "shadowOffsetY": 1.8, "fillMode": "primary", "strokeMode": "light", "shadowMode": "shadow"},
]

MODERN_FEATURED_DESIGN_SEQUENCE = [
    ("modern_ink_coral", "clean_display"),
    ("modern_gold_luxe", "gold_emboss"),
    ("modern_candy_pop", "soft_marker"),
    ("modern_neon_pink", "pink_neon_bloom"),
    ("modern_soft_rose", "soft_marker"),
    ("modern_teal_cutout", "teal_cutout"),
]


def get_magic_write_training_dataset() -> dict[str, Any]:
    """Return the reusable Magic Write trained dataset/configuration."""
    return {
        "name": "magic_write",
        "version": MAGIC_WRITE_DATASET_VERSION,
        "canvas": {
            "width": DEFAULT_CANVAS_WIDTH,
            "height": DEFAULT_CANVAS_HEIGHT,
            "preview_scale": DEFAULT_PREVIEW_SCALE,
        },
        "fonts": {
            "families": deepcopy(CANVA_FONT_FAMILIES),
            "groups": deepcopy(CANVA_FONT_GROUPS),
            "kind_order": deepcopy(FONT_KIND_ORDER),
        },
        "style_presets": deepcopy(STYLE_PRESETS),
        "modern_style_dataset": deepcopy(MODERN_MAGIC_WRITE_DATASET),
        "modern_composition_templates": deepcopy(MODERN_COMPOSITION_TEMPLATES),
        "modern_composition_palettes": deepcopy(MODERN_COMPOSITION_PALETTES),
        "modern_composition_effects": deepcopy(MODERN_COMPOSITION_EFFECTS),
    }


def save_magic_write_training_dataset(path: str | os.PathLike[str]) -> Path:
    """Save the Magic Write trained dataset/configuration as JSON."""
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(get_magic_write_training_dataset(), indent=2),
        encoding="utf-8",
    )
    return output_path


class MagicWriteModel:
    """Small reusable local wrapper for separate projects."""

    def __init__(
        self,
        model: str | None = None,
        timeout: int = 45,
        canvas_width: int = DEFAULT_CANVAS_WIDTH,
        canvas_height: int = DEFAULT_CANVAS_HEIGHT,
    ) -> None:
        # model/timeout are accepted for backwards compatibility; generation is local.
        self.model = LOCAL_MAGIC_WRITE_MODEL
        self.timeout = timeout
        self.canvas_width = canvas_width
        self.canvas_height = canvas_height
        self.dataset = get_magic_write_training_dataset()

    def generate(
        self,
        text: str,
        count: int = 12,
        modern: bool = True,
        seed: int | None = None,
        **kwargs: Any,
    ) -> dict[str, Any]:
        return generate_magic_write(
            text=text,
            count=count,
            model=self.model,
            timeout=self.timeout,
            canvas_width=self.canvas_width,
            canvas_height=self.canvas_height,
            modern=modern,
            seed=seed,
            **kwargs,
        )


STYLE_PRESETS: list[dict[str, Any]] = [
    {
        "name": "happy_birthday_marker",
        "fontFamily": "Goldman",
        "fontSize": 40,
        "fontWeight": "bold",
        "fontStyle": "normal",
        "fill": "#111111",
        "stroke": "",
        "strokeWidth": 0,
        "textDecoration": "",
        "shadowColor": "",
        "shadowBlur": 0,
        "shadowOffsetX": 0,
        "shadowOffsetY": 0,
        "letterSpacing": 0,
        "lineHeight": 1.02,
    },
    {
        "name": "gold_serif",
        "fontFamily": "Georgia",
        "fontSize": 42,
        "fontWeight": "bold",
        "fontStyle": "normal",
        "fill": "#D8A919",
        "stroke": "",
        "strokeWidth": 0,
        "textDecoration": "",
        "shadowColor": "#E8D187",
        "shadowBlur": 1.2,
        "shadowOffsetX": 0,
        "shadowOffsetY": 1,
        "letterSpacing": 0,
        "lineHeight": 0.92,
    },
    {
        "name": "candy_shadow",
        "fontFamily": "Snell Roundhand",
        "fontSize": 44,
        "fontWeight": "bold",
        "fontStyle": "normal",
        "fill": "#FF6F72",
        "stroke": "#FFF0CB",
        "strokeWidth": 3,
        "textDecoration": "",
        "shadowColor": "#FFB0A6",
        "shadowBlur": 0,
        "shadowOffsetX": 4,
        "shadowOffsetY": 5,
        "letterSpacing": 0,
        "lineHeight": 0.95,
    },
    {
        "name": "brush_pop",
        "fontFamily": "Snell Roundhand",
        "fontSize": 42,
        "fontWeight": "bold",
        "fontStyle": "normal",
        "fill": "#FF4B5C",
        "stroke": "",
        "strokeWidth": 0,
        "textDecoration": "",
        "shadowColor": "#B8B8C9",
        "shadowBlur": 0,
        "shadowOffsetX": -5,
        "shadowOffsetY": -4,
        "letterSpacing": 0,
        "lineHeight": 0.95,
    },
    {
        "name": "neon_glow",
        "fontFamily": "Arial",
        "fontSize": 42,
        "fontWeight": "bold",
        "fontStyle": "normal",
        "fill": "#FF5BB4",
        "stroke": "#FF8BD0",
        "strokeWidth": 1.5,
        "textDecoration": "",
        "shadowColor": "#FF44B0",
        "shadowBlur": 12,
        "shadowOffsetX": 0,
        "shadowOffsetY": 0,
        "letterSpacing": 0,
        "lineHeight": 1.0,
    },
    {
        "name": "varsity_stamp",
        "fontFamily": "Georgia",
        "fontSize": 54,
        "fontWeight": "bold",
        "fontStyle": "normal",
        "fill": "#FF5056",
        "stroke": "#FF5056",
        "strokeWidth": 1,
        "textDecoration": "underline",
        "shadowColor": "",
        "shadowBlur": 0,
        "shadowOffsetX": 0,
        "shadowOffsetY": 0,
        "letterSpacing": 1.2,
        "lineHeight": 0.95,
    },
    {
        "name": "like_subscribe_hollow",
        "fontFamily": "Goldman",
        "fontSize": 38,
        "fontWeight": "bold",
        "fontStyle": "normal",
        "fill": "#FFFFFF",
        "stroke": "#F4CF39",
        "strokeWidth": 2.6,
        "textDecoration": "",
        "shadowColor": "#FF7E5F",
        "shadowBlur": 0,
        "shadowOffsetX": 1.8,
        "shadowOffsetY": 2.6,
        "letterSpacing": 1.1,
        "lineHeight": 0.95,
    },
    {
        "name": "engaged_script",
        "fontFamily": "Great Vibes",
        "fontSize": 48,
        "fontWeight": "normal",
        "fontStyle": "italic",
        "fill": "#101010",
        "stroke": "",
        "strokeWidth": 0,
        "textDecoration": "",
        "shadowColor": "",
        "shadowBlur": 0,
        "shadowOffsetX": 0,
        "shadowOffsetY": 0,
        "letterSpacing": 0,
        "lineHeight": 0.92,
    },
    {
        "name": "order_now_blue_orange",
        "fontFamily": "Arial",
        "fontSize": 38,
        "fontWeight": "bold",
        "fontStyle": "italic",
        "fill": "#23B7E5",
        "stroke": "",
        "strokeWidth": 0,
        "textDecoration": "",
        "shadowColor": "#FF7A22",
        "shadowBlur": 0,
        "shadowOffsetX": 3.5,
        "shadowOffsetY": 0,
        "letterSpacing": -0.4,
        "lineHeight": 1.0,
    },
    {
        "name": "diskon_bold",
        "fontFamily": "Arial",
        "fontSize": 46,
        "fontWeight": "bold",
        "fontStyle": "normal",
        "fill": "#222222",
        "stroke": "",
        "strokeWidth": 0,
        "textDecoration": "",
        "shadowColor": "",
        "shadowBlur": 0,
        "shadowOffsetX": 0,
        "shadowOffsetY": 0,
        "letterSpacing": 0,
        "lineHeight": 0.9,
    },
    {
        "name": "bride_groom_serif",
        "fontFamily": "Georgia",
        "fontSize": 43,
        "fontWeight": "normal",
        "fontStyle": "italic",
        "fill": "#16462D",
        "stroke": "",
        "strokeWidth": 0,
        "textDecoration": "",
        "shadowColor": "",
        "shadowBlur": 0,
        "shadowOffsetX": 0,
        "shadowOffsetY": 0,
        "letterSpacing": -0.3,
        "lineHeight": 0.86,
    },
    {
        "name": "now_open_neon",
        "fontFamily": "Snell Roundhand",
        "fontSize": 45,
        "fontWeight": "bold",
        "fontStyle": "normal",
        "fill": "#FFFFFF",
        "stroke": "#8B7DFF",
        "strokeWidth": 1.4,
        "textDecoration": "",
        "shadowColor": "#8179FF",
        "shadowBlur": 13,
        "shadowOffsetX": 0,
        "shadowOffsetY": 0,
        "letterSpacing": 0,
        "lineHeight": 0.95,
    },
    {
        "name": "royal_blue_outline",
        "fontFamily": "Goldman",
        "fontSize": 42,
        "fontWeight": "600",
        "fontStyle": "normal",
        "fill": "#1B45F5",
        "stroke": "#31FF38",
        "strokeWidth": 1.2,
        "textDecoration": "underline",
        "shadowColor": "",
        "shadowBlur": 0,
        "shadowOffsetX": 0,
        "shadowOffsetY": 0,
        "letterSpacing": 0,
        "lineHeight": 1.03,
    },
    {
        "name": "coral_chunky_shadow",
        "fontFamily": "Arial",
        "fontSize": 44,
        "fontWeight": "bold",
        "fontStyle": "normal",
        "fill": "#FF595E",
        "stroke": "#FFFFFF",
        "strokeWidth": 2.8,
        "textDecoration": "",
        "shadowColor": "#FFD166",
        "shadowBlur": 0,
        "shadowOffsetX": 3,
        "shadowOffsetY": 4,
        "letterSpacing": 0.6,
        "lineHeight": 0.92,
    },
    {
        "name": "mint_script",
        "fontFamily": "Great Vibes",
        "fontSize": 48,
        "fontWeight": "normal",
        "fontStyle": "normal",
        "fill": "#0F6B5B",
        "stroke": "",
        "strokeWidth": 0,
        "textDecoration": "",
        "shadowColor": "#CFF7E4",
        "shadowBlur": 3,
        "shadowOffsetX": 0,
        "shadowOffsetY": 2,
        "letterSpacing": 0,
        "lineHeight": 0.9,
    },
    {
        "name": "retro_orange",
        "fontFamily": "Georgia",
        "fontSize": 41,
        "fontWeight": "bold",
        "fontStyle": "normal",
        "fill": "#F56C2D",
        "stroke": "#FFE6A7",
        "strokeWidth": 1.8,
        "textDecoration": "",
        "shadowColor": "#2EC4B6",
        "shadowBlur": 0,
        "shadowOffsetX": -3,
        "shadowOffsetY": 3,
        "letterSpacing": 0.2,
        "lineHeight": 0.95,
    },
    {
        "name": "soft_gray_red_brush",
        "fontFamily": "Snell Roundhand",
        "fontSize": 43,
        "fontWeight": "bold",
        "fontStyle": "normal",
        "fill": "#F94958",
        "stroke": "",
        "strokeWidth": 0,
        "textDecoration": "",
        "shadowColor": "#B8BBC6",
        "shadowBlur": 0,
        "shadowOffsetX": -5,
        "shadowOffsetY": -5,
        "letterSpacing": 0,
        "lineHeight": 0.96,
    },
    {
        "name": "black_white_sticker",
        "fontFamily": "Arial",
        "fontSize": 43,
        "fontWeight": "bold",
        "fontStyle": "normal",
        "fill": "#111111",
        "stroke": "#FFFFFF",
        "strokeWidth": 4.2,
        "textDecoration": "",
        "shadowColor": "#DADDE5",
        "shadowBlur": 0,
        "shadowOffsetX": 2,
        "shadowOffsetY": 3,
        "letterSpacing": 0,
        "lineHeight": 0.95,
    },
    {
        "name": "yellow_pop_outline",
        "fontFamily": "Goldman",
        "fontSize": 42,
        "fontWeight": "bold",
        "fontStyle": "normal",
        "fill": "#FFF7A8",
        "stroke": "#F4C430",
        "strokeWidth": 2.2,
        "textDecoration": "",
        "shadowColor": "#FF6B6B",
        "shadowBlur": 0,
        "shadowOffsetX": 2,
        "shadowOffsetY": 2,
        "letterSpacing": 0.8,
        "lineHeight": 0.94,
    },
    {
        "name": "purple_glow_script",
        "fontFamily": "Great Vibes",
        "fontSize": 50,
        "fontWeight": "normal",
        "fontStyle": "normal",
        "fill": "#FFFFFF",
        "stroke": "#A389FF",
        "strokeWidth": 1.2,
        "textDecoration": "",
        "shadowColor": "#9A7DFF",
        "shadowBlur": 10,
        "shadowOffsetX": 0,
        "shadowOffsetY": 0,
        "letterSpacing": 0,
        "lineHeight": 0.9,
    },
    {
        "name": "clean_luxury_serif",
        "fontFamily": "Georgia",
        "fontSize": 39,
        "fontWeight": "normal",
        "fontStyle": "normal",
        "fill": "#2F2F2F",
        "stroke": "",
        "strokeWidth": 0,
        "textDecoration": "",
        "shadowColor": "",
        "shadowBlur": 0,
        "shadowOffsetX": 0,
        "shadowOffsetY": 0,
        "letterSpacing": 1.6,
        "lineHeight": 1.0,
    },
    {
        "name": "red_stamp_hollow",
        "fontFamily": "Georgia",
        "fontSize": 48,
        "fontWeight": "bold",
        "fontStyle": "normal",
        "fill": "#FFF4F4",
        "stroke": "#EF4E56",
        "strokeWidth": 2.6,
        "textDecoration": "underline",
        "shadowColor": "",
        "shadowBlur": 0,
        "shadowOffsetX": 0,
        "shadowOffsetY": 0,
        "letterSpacing": 1.1,
        "lineHeight": 0.9,
    },
    {
        "name": "sky_blue_bubble",
        "fontFamily": "Arial",
        "fontSize": 43,
        "fontWeight": "bold",
        "fontStyle": "normal",
        "fill": "#4CC9F0",
        "stroke": "#FFFFFF",
        "strokeWidth": 3.2,
        "textDecoration": "",
        "shadowColor": "#4361EE",
        "shadowBlur": 0,
        "shadowOffsetX": 3,
        "shadowOffsetY": 3,
        "letterSpacing": 0,
        "lineHeight": 0.95,
    },
    {
        "name": "minimal_black_caps",
        "fontFamily": "Arial",
        "fontSize": 38,
        "fontWeight": "bold",
        "fontStyle": "normal",
        "fill": "#111111",
        "stroke": "",
        "strokeWidth": 0,
        "textDecoration": "",
        "shadowColor": "",
        "shadowBlur": 0,
        "shadowOffsetX": 0,
        "shadowOffsetY": 0,
        "letterSpacing": 2.4,
        "lineHeight": 1.08,
    },
    {
        "name": "rose_gold_serif",
        "fontFamily": "Georgia",
        "fontSize": 42,
        "fontWeight": "bold",
        "fontStyle": "normal",
        "fill": "#B76E79",
        "stroke": "#F7D9D9",
        "strokeWidth": 1,
        "textDecoration": "",
        "shadowColor": "#6B2F38",
        "shadowBlur": 1.5,
        "shadowOffsetX": 1,
        "shadowOffsetY": 1,
        "letterSpacing": 0.6,
        "lineHeight": 0.94,
    },
    {
        "name": "teal_cream_shadow",
        "fontFamily": "Goldman",
        "fontSize": 41,
        "fontWeight": "bold",
        "fontStyle": "normal",
        "fill": "#087E8B",
        "stroke": "#FFF6D6",
        "strokeWidth": 2,
        "textDecoration": "",
        "shadowColor": "#FF5A5F",
        "shadowBlur": 0,
        "shadowOffsetX": 3,
        "shadowOffsetY": 2,
        "letterSpacing": 0.3,
        "lineHeight": 0.96,
    },
    {
        "name": "magenta_outline_script",
        "fontFamily": "Snell Roundhand",
        "fontSize": 48,
        "fontWeight": "bold",
        "fontStyle": "normal",
        "fill": "#FF3EA5",
        "stroke": "#FFFFFF",
        "strokeWidth": 2.4,
        "textDecoration": "",
        "shadowColor": "#601A4A",
        "shadowBlur": 4,
        "shadowOffsetX": 0,
        "shadowOffsetY": 2,
        "letterSpacing": 0,
        "lineHeight": 0.9,
    },
]

MODERN_MAGIC_WRITE_DATASET: list[dict[str, Any]] = [
    {
        "name": "modern_coming_soon_serif",
        "category": "editorial_serif",
        "fontFamily": "Playfair Display",
        "fontSize": 44,
        "fontWeight": "normal",
        "fontStyle": "italic",
        "fill": "#B64040",
        "stroke": "",
        "strokeWidth": 0,
        "shadowColor": "",
        "shadowBlur": 0,
        "shadowOffsetX": 0,
        "shadowOffsetY": 0,
        "letterSpacing": 0.2,
        "lineHeight": 0.85,
        "textDecoration": "",
        "textTransform": "upper",
        "previewLayout": "coming_soon",
        "sample": "COMING\nSOON\nStay Tuned",
    },
    {
        "name": "modern_discount_condensed",
        "category": "sale_condensed",
        "fontFamily": "Bebas Neue",
        "fontSize": 68,
        "fontWeight": "bold",
        "fontStyle": "normal",
        "fill": "#8A8A8A",
        "stroke": "",
        "strokeWidth": 0,
        "shadowColor": "#CFCFCF",
        "shadowBlur": 0,
        "shadowOffsetX": 3,
        "shadowOffsetY": 4,
        "letterSpacing": 0.4,
        "lineHeight": 0.75,
        "textDecoration": "",
        "textTransform": "upper",
        "previewLayout": "sale",
        "accentFill": "#55E0B4",
        "sample": "30%\nOFF\nON ALL PRODUCTS",
    },
    {
        "name": "modern_signature_blue",
        "category": "signature",
        "fontFamily": "Sacramento",
        "fontSize": 52,
        "fontWeight": "normal",
        "fontStyle": "normal",
        "fill": "#2A638B",
        "stroke": "",
        "strokeWidth": 0,
        "shadowColor": "",
        "shadowBlur": 0,
        "shadowOffsetX": 0,
        "shadowOffsetY": 0,
        "letterSpacing": 0,
        "lineHeight": 0.78,
        "textDecoration": "",
        "textTransform": "none",
        "previewLayout": "signature",
        "sample": "love\nalways",
    },
    {
        "name": "modern_title_heading",
        "category": "title_heading",
        "fontFamily": "Montserrat",
        "fontSize": 58,
        "fontWeight": "bold",
        "fontStyle": "normal",
        "fill": "#050505",
        "stroke": "",
        "strokeWidth": 0,
        "shadowColor": "",
        "shadowBlur": 0,
        "shadowOffsetX": 0,
        "shadowOffsetY": 0,
        "letterSpacing": 0,
        "lineHeight": 0.86,
        "textDecoration": "",
        "textTransform": "none",
        "previewLayout": "title_heading",
        "sample": "Title\nHEADING",
    },
    {
        "name": "modern_signature_glow",
        "category": "neon_signature",
        "fontFamily": "Yellowtail",
        "fontSize": 42,
        "fontWeight": "normal",
        "fontStyle": "normal",
        "fill": "#FFFFFF",
        "stroke": "#FFE9A6",
        "strokeWidth": 0.8,
        "shadowColor": "#FFE16A",
        "shadowBlur": 12,
        "shadowOffsetX": 0,
        "shadowOffsetY": 0,
        "letterSpacing": 0,
        "lineHeight": 0.9,
        "textDecoration": "",
        "textTransform": "none",
        "previewLayout": "glow_signature",
        "sample": "Signature",
    },
    {
        "name": "modern_tattoo_arc",
        "category": "tattoo_arc",
        "fontFamily": "Rye",
        "fontSize": 44,
        "fontWeight": "normal",
        "fontStyle": "normal",
        "fill": "#101010",
        "stroke": "",
        "strokeWidth": 0,
        "shadowColor": "",
        "shadowBlur": 0,
        "shadowOffsetX": 0,
        "shadowOffsetY": 0,
        "letterSpacing": 1.5,
        "lineHeight": 0.85,
        "textDecoration": "",
        "textTransform": "upper",
        "previewLayout": "arc",
        "sample": "TATTOO\nstudio",
    },
    {
        "name": "modern_clean_sans",
        "category": "bold_sans",
        "fontFamily": "Poppins",
        "fontSize": 56,
        "fontWeight": "bold",
        "fontStyle": "normal",
        "fill": "#0A0A0A",
        "stroke": "",
        "strokeWidth": 0,
        "shadowColor": "",
        "shadowBlur": 0,
        "shadowOffsetX": 0,
        "shadowOffsetY": 0,
        "letterSpacing": -0.4,
        "lineHeight": 0.92,
        "textDecoration": "",
        "textTransform": "none",
        "previewLayout": "title_heading",
        "sample": "Title\nHEADING",
    },
    {
        "name": "modern_outline_sale",
        "category": "outline_display",
        "fontFamily": "Bungee",
        "fontSize": 42,
        "fontWeight": "bold",
        "fontStyle": "normal",
        "fill": "#FFFFFF",
        "stroke": "#FF705C",
        "strokeWidth": 2.4,
        "shadowColor": "#F7D85F",
        "shadowBlur": 0,
        "shadowOffsetX": 2,
        "shadowOffsetY": 3,
        "letterSpacing": 0.8,
        "lineHeight": 0.92,
        "textDecoration": "",
        "textTransform": "upper",
        "previewLayout": "stacked",
        "sample": "LIKE &\nSUBSCRIBE",
    },
    {
        "name": "modern_luxury_serif",
        "category": "luxury_serif",
        "fontFamily": "Cormorant Garamond",
        "fontSize": 46,
        "fontWeight": "bold",
        "fontStyle": "normal",
        "fill": "#D2A21B",
        "stroke": "",
        "strokeWidth": 0,
        "shadowColor": "#E8D187",
        "shadowBlur": 1.2,
        "shadowOffsetX": 0,
        "shadowOffsetY": 1,
        "letterSpacing": 0.6,
        "lineHeight": 0.9,
        "textDecoration": "",
        "textTransform": "upper",
        "previewLayout": "stacked",
        "sample": "GOLDEN\nHOUR",
    },
    {
        "name": "modern_mono_label",
        "category": "mono_label",
        "fontFamily": "Space Mono",
        "fontSize": 34,
        "fontWeight": "bold",
        "fontStyle": "normal",
        "fill": "#2B2B2B",
        "stroke": "",
        "strokeWidth": 0,
        "shadowColor": "",
        "shadowBlur": 0,
        "shadowOffsetX": 0,
        "shadowOffsetY": 0,
        "letterSpacing": 1.5,
        "lineHeight": 1.0,
        "textDecoration": "",
        "textTransform": "upper",
        "previewLayout": "stacked",
        "sample": "NEW\nDROP",
    },
    {
        "name": "modern_editorial_caps",
        "category": "editorial_caps",
        "fontFamily": "Cinzel",
        "fontSize": 40,
        "fontWeight": "bold",
        "fontStyle": "normal",
        "fill": "#1B1B1B",
        "stroke": "",
        "strokeWidth": 0,
        "shadowColor": "",
        "shadowBlur": 0,
        "shadowOffsetX": 0,
        "shadowOffsetY": 0,
        "letterSpacing": 1.8,
        "lineHeight": 0.95,
        "textDecoration": "",
        "textTransform": "upper",
        "previewLayout": "stacked",
        "sample": "MODERN\nTYPE",
    },
    {
        "name": "modern_marker_pop",
        "category": "marker_pop",
        "fontFamily": "Permanent Marker",
        "fontSize": 42,
        "fontWeight": "normal",
        "fontStyle": "normal",
        "fill": "#F94B5D",
        "stroke": "#FFFFFF",
        "strokeWidth": 2.2,
        "shadowColor": "#BFC2CF",
        "shadowBlur": 0,
        "shadowOffsetX": -4,
        "shadowOffsetY": -4,
        "letterSpacing": 0,
        "lineHeight": 0.92,
        "textDecoration": "",
        "textTransform": "none",
        "previewLayout": "stacked",
        "sample": "Happy\nbirthday!",
    },
]

MODERN_COMPOSITION_TEMPLATES: list[dict[str, Any]] = [
    {"name": "modern_comp_happy_birthday", "kind": "happy_birthday"},
    {"name": "modern_comp_golden_hour", "kind": "golden_hour"},
    {"name": "modern_comp_light_script", "kind": "light_script"},
    {"name": "modern_comp_neon_glow", "kind": "neon_glow"},
    {"name": "modern_comp_thank_you", "kind": "thank_you"},
    {"name": "modern_comp_luxury_names", "kind": "luxury_names"},
    {"name": "modern_comp_editorial_caps", "kind": "editorial_caps"},
    {"name": "modern_comp_script_club", "kind": "script_club"},
    {"name": "modern_comp_bride_groom", "kind": "bride_groom"},
    {"name": "modern_comp_xoxo", "kind": "xoxo"},
    {"name": "modern_comp_studio_badge", "kind": "studio_badge"},
    {"name": "modern_comp_streaming_now", "kind": "streaming_now"},
    {"name": "modern_comp_quarterly_targets", "kind": "quarterly_targets"},
    {"name": "modern_comp_quarter_roadmap", "kind": "quarter_roadmap"},
    {"name": "modern_comp_neon_open", "kind": "neon_open"},
]


def _clamp_number(value: Any, default: float, minimum: float, maximum: float) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        number = default
    return min(max(number, minimum), maximum)


def _clean_hex(value: Any, default: str = "") -> str:
    if not isinstance(value, str):
        return default
    value = value.strip()
    if not value:
        return default
    if not value.startswith("#"):
        value = f"#{value}"
    if len(value) == 4 and re.fullmatch(r"#[0-9A-Fa-f]{3}", value):
        value = "#" + "".join(ch * 2 for ch in value[1:])
    return value.upper() if HEX_RE.match(value) else default


def _http_get(url: str, timeout: int = 20, headers: dict[str, str] | None = None) -> bytes:
    request = urllib.request.Request(url, headers=headers or {})
    with urllib.request.urlopen(request, timeout=timeout, context=SSL_CONTEXT) as response:
        return response.read()


def _load_cached_google_font_families() -> list[str]:
    try:
        data = json.loads(GOOGLE_FONTS_CACHE_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    if isinstance(data, dict):
        families = data.get("families", [])
    else:
        families = data
    if not isinstance(families, list):
        return []
    return _normalize_font_families(families)


def fetch_google_font_families(
    api_key: str | None = None,
    sort: str = "alpha",
    category: str | None = None,
    refresh: bool = False,
    timeout: int = 30,
) -> list[str]:
    """Return the current Google Fonts family list.

    The official Google Fonts Developer API requires an API key. If a key is
    missing or the request fails, use the locally cached list first, then the
    bundled fallback list.
    """
    api_key = (api_key or GOOGLE_FONTS_API_KEY or "").strip()
    if not refresh:
        cached = _load_cached_google_font_families()
        if cached and not api_key:
            return cached

    if api_key:
        query = {"key": api_key, "sort": sort or "alpha"}
        if category:
            query["category"] = category
        url = GOOGLE_FONTS_API_URL + "?" + urllib.parse.urlencode(query)
        try:
            payload = json.loads(_http_get(url, timeout=timeout).decode("utf-8"))
            families = [
                str(item.get("family", "")).strip()
                for item in payload.get("items", [])
                if isinstance(item, dict) and item.get("family")
            ]
            families = _normalize_font_families(families)
            if families:
                PRIMARY_FONT_CACHE_DIR.mkdir(parents=True, exist_ok=True)
                GOOGLE_FONTS_CACHE_PATH.write_text(
                    json.dumps({"families": families, "sort": sort, "category": category}, indent=2),
                    encoding="utf-8",
                )
                return families
        except (OSError, urllib.error.URLError, RuntimeError, json.JSONDecodeError) as exc:
            print(f"warning: Google Fonts API fetch failed, using cached/bundled fonts: {exc}", file=sys.stderr)

    cached = _load_cached_google_font_families()
    return cached or CANVA_FONT_FAMILIES[:]


def _rotate_hex_color(value: str, shift: int) -> str:
    color = _clean_hex(value, "")
    if not color:
        return value
    red = int(color[1:3], 16)
    green = int(color[3:5], 16)
    blue = int(color[5:7], 16)
    channels = [red, green, blue]
    shift = shift % 3
    if shift:
        channels = channels[-shift:] + channels[:-shift]
    return f"#{channels[0]:02X}{channels[1]:02X}{channels[2]:02X}"


def _variant_from_preset(preset: dict[str, Any], cycle: int) -> dict[str, Any]:
    style = deepcopy(preset)
    if cycle <= 0:
        return style

    # Repeated requests beyond the curated set should still produce visibly
    # different options instead of exact duplicates.
    color_shift = cycle % 3
    for key in ("fill", "stroke", "shadowColor"):
        if style.get(key):
            style[key] = _rotate_hex_color(str(style[key]), color_shift)
    style["fontSize"] = _clamp_number(style.get("fontSize"), 40, 8, 96) * (0.94 + 0.03 * (cycle % 5))
    style["letterSpacing"] = _clamp_number(style.get("letterSpacing"), 0, -1, 6) + ((cycle % 4) * 0.25)
    style["rotation"] = [0, -3, 3, -5, 5][cycle % 5]
    style["name"] = f"{style.get('name', 'style')}_{cycle + 1}"
    return style


def _make_rng(seed: int | None = None) -> random.Random:
    return random.Random(seed) if seed is not None else random.SystemRandom()


def _shuffle_copy(values: list[Any] | tuple[Any, ...], rng: random.Random) -> list[Any]:
    result = list(values)
    rng.shuffle(result)
    return result


def _pick_unused_font(candidates: list[str], rng: random.Random, used_fonts: set[str],
                      fallback: str | None = None) -> str:
    normalized = _normalize_font_families(candidates or ([fallback] if fallback else None))
    available = [family for family in normalized if family.lower() not in used_fonts]
    pool = available or normalized or CANVA_FONT_FAMILIES[:]
    family = rng.choice(pool)
    used_fonts.add(family.lower())
    return family


def _pick_unused_font_with_global_fallback(candidates: list[str], rng: random.Random,
                                           used_fonts: set[str]) -> str:
    primary = _normalize_font_families(candidates)
    primary_available = [family for family in primary if family.lower() not in used_fonts]
    if primary_available:
        family = rng.choice(primary_available)
        used_fonts.add(family.lower())
        return family

    global_available = [
        family
        for family in CANVA_FONT_FAMILIES
        if family.lower() not in used_fonts
    ]
    if global_available:
        family = rng.choice(global_available)
        used_fonts.add(family.lower())
        return family

    return _pick_unused_font(primary, rng, used_fonts)


def _font_pool_for_style(style: dict[str, Any]) -> list[str]:
    category = str(style.get("category") or "").lower()
    layout = str(style.get("previewLayout") or "").lower()
    name = str(style.get("name") or "").lower()
    current_family = str(style.get("fontFamily") or "")

    if any(token in f"{category} {layout} {name}" for token in ("signature", "script", "brush")):
        return CANVA_FONT_GROUPS["script"]
    if any(token in f"{category} {layout} {name}" for token in ("serif", "luxury", "editorial", "coming")):
        return CANVA_FONT_GROUPS["serif"]
    if any(token in f"{category} {layout} {name}" for token in ("sale", "title", "heading", "outline", "marker", "caps")):
        return CANVA_FONT_GROUPS["display"] + CANVA_FONT_GROUPS["sans"]
    if any(token in f"{category} {layout} {name}" for token in ("tattoo", "arc", "decorative")):
        return CANVA_FONT_GROUPS["decorative"] + CANVA_FONT_GROUPS["serif"]
    if "mono" in f"{category} {layout} {name}":
        return CANVA_FONT_GROUPS["mono"]

    kind = _font_kind(current_family)
    return CANVA_FONT_GROUPS.get(kind, CANVA_FONT_FAMILIES)


def _randomize_style_font(style: dict[str, Any], rng: random.Random, used_fonts: set[str]) -> dict[str, Any]:
    randomized = deepcopy(style)
    randomized["fontFamily"] = _pick_unused_font(
        _font_pool_for_style(randomized),
        rng,
        used_fonts,
        fallback=str(randomized.get("fontFamily") or "Arial"),
    )
    return randomized


def _design_signature(style: dict[str, Any]) -> tuple[Any, ...]:
    return (
        str(style.get("fill") or ""),
        str(style.get("stroke") or ""),
        round(float(style.get("strokeWidth") or 0), 2),
        str(style.get("shadowColor") or ""),
        round(float(style.get("shadowBlur") or 0), 2),
        round(float(style.get("shadowOffsetX") or 0), 2),
        round(float(style.get("shadowOffsetY") or 0), 2),
        str(style.get("textDecoration") or ""),
        round(float(style.get("letterSpacing") or 0), 2),
        round(float(style.get("rotation") or 0), 2),
        str(style.get("previewLayout") or "stacked"),
    )


def _apply_random_design(style: dict[str, Any], rng: random.Random, index: int,
                         used_designs: set[tuple[Any, ...]]) -> dict[str, Any]:
    randomized = deepcopy(style)
    kind = _font_kind(str(randomized.get("fontFamily") or ""))
    palette_order = _shuffle_copy(DESIGN_PALETTES, rng)
    effect_order = _shuffle_copy(DESIGN_EFFECTS, rng)

    selected: dict[str, Any] | None = None
    selected_palette: dict[str, Any] | None = None
    selected_effect: dict[str, Any] | None = None
    for palette in palette_order:
        for effect in effect_order:
            candidate = deepcopy(randomized)
            candidate.update(palette)
            stroke = _clean_hex(candidate.get("stroke"), "")
            candidate["stroke"] = stroke
            candidate["strokeWidth"] = float(effect["strokeWidth"]) if stroke else 0
            candidate["shadowColor"] = _clean_hex(candidate.get("shadowColor"), "")
            candidate["shadowBlur"] = float(effect["shadowBlur"]) if candidate["shadowColor"] else 0
            candidate["shadowOffsetX"] = float(effect["shadowOffsetX"]) if candidate["shadowColor"] else 0
            candidate["shadowOffsetY"] = float(effect["shadowOffsetY"]) if candidate["shadowColor"] else 0
            candidate["textDecoration"] = effect["textDecoration"]
            candidate["letterSpacing"] = float(effect["letterSpacing"])
            candidate["rotation"] = float(effect["rotation"])
            if kind == "script":
                candidate["letterSpacing"] = min(candidate["letterSpacing"], 0.4)
                candidate["fontStyle"] = rng.choice(["normal", "italic"])
            elif kind in {"display", "mono", "decorative"}:
                candidate["letterSpacing"] = max(candidate["letterSpacing"], rng.choice([0.6, 1.0, 1.4]))
                candidate["fontWeight"] = "bold"
            elif kind == "serif":
                candidate["fontStyle"] = rng.choice(["normal", "italic"])
                candidate["letterSpacing"] = max(candidate["letterSpacing"], rng.choice([0.2, 0.8, 1.2]))
            signature = _design_signature(candidate)
            if signature not in used_designs:
                selected = candidate
                selected_palette = palette
                selected_effect = effect
                break
        if selected:
            break

    if selected is None:
        selected_palette = palette_order[index % len(palette_order)]
        selected_effect = effect_order[index % len(effect_order)]
        selected = deepcopy(randomized)
        selected.update(selected_palette)
        selected["stroke"] = _clean_hex(selected.get("stroke"), "")
        selected["strokeWidth"] = float(selected_effect["strokeWidth"]) if selected["stroke"] else 0
        selected["shadowColor"] = _clean_hex(selected.get("shadowColor"), "")
        selected["shadowBlur"] = float(selected_effect["shadowBlur"]) if selected["shadowColor"] else 0
        selected["shadowOffsetX"] = float(selected_effect["shadowOffsetX"]) if selected["shadowColor"] else 0
        selected["shadowOffsetY"] = float(selected_effect["shadowOffsetY"]) if selected["shadowColor"] else 0
        selected["textDecoration"] = selected_effect["textDecoration"]
        selected["letterSpacing"] = float(selected_effect["letterSpacing"]) + (index % 5) * 0.25
        selected["rotation"] = float(selected_effect["rotation"]) + [-4, -2, 0, 2, 4][index % 5]

    base_size = _clamp_number(selected.get("fontSize"), 40, 8, 96)
    selected["fontSize"] = base_size * rng.uniform(0.88, 1.12)
    if rng.random() < 0.18:
        selected["textDecoration"] = rng.choice(["underline", ""])
    if str(selected.get("previewLayout") or "") in {"sale", "title_heading", "coming_soon", "signature", "glow_signature", "arc"}:
        selected["rotation"] = 0

    effect_name = str((selected_effect or {}).get("suffix") or "custom")
    selected["name"] = f"{selected.get('name', 'style')}_{effect_name}_{index + 1}"
    used_designs.add(_design_signature(selected))
    return selected


def _canva_style_presets(count: int, randomize_fonts: bool = True,
                         randomize_designs: bool = True,
                         rng: random.Random | None = None) -> list[dict[str, Any]]:
    rng = rng or _make_rng()
    preset_order = _shuffle_copy(STYLE_PRESETS, rng) if randomize_fonts else STYLE_PRESETS[:]
    used_fonts: set[str] = set()
    used_designs: set[tuple[Any, ...]] = set()
    styles: list[dict[str, Any]] = []
    for index in range(count):
        preset = preset_order[index % len(preset_order)]
        style = _variant_from_preset(preset, index // len(preset_order))
        if randomize_fonts:
            style = _randomize_style_font(style, rng, used_fonts)
        if randomize_designs:
            style = _apply_random_design(style, rng, index, used_designs)
        styles.append(style)
    return styles


def _modern_style_dataset(count: int | None = None, mood: str | None = None,
                          randomize_fonts: bool = True,
                          randomize_designs: bool = True,
                          rng: random.Random | None = None) -> list[dict[str, Any]]:
    rng = rng or _make_rng()
    styles = [deepcopy(style) for style in MODERN_MAGIC_WRITE_DATASET]
    mood_text = str(mood or "").lower()
    if mood_text:
        def score(style: dict[str, Any]) -> int:
            haystack = " ".join(
                str(style.get(key, ""))
                for key in ("name", "category", "fontFamily", "sample", "previewLayout")
            ).lower()
            return sum(1 for token in re.findall(r"[a-z0-9]+", mood_text) if token in haystack)
        styles.sort(key=score, reverse=True)
    elif randomize_fonts:
        rng.shuffle(styles)

    if count is None:
        selected = styles
    else:
        selected = []
        for index in range(count):
            style = deepcopy(styles[index % len(styles)])
            if index >= len(styles):
                style = _variant_from_preset(style, index // len(styles))
            selected.append(style)

    if randomize_fonts:
        used_fonts: set[str] = set()
        selected = [_randomize_style_font(style, rng, used_fonts) for style in selected]
    if randomize_designs:
        used_designs: set[tuple[Any, ...]] = set()
        selected = [_apply_random_design(style, rng, index, used_designs) for index, style in enumerate(selected)]
    return selected


def _normalize_font_families(font_families: list[str] | tuple[str, ...] | str | None) -> list[str]:
    if font_families is None:
        return CANVA_FONT_FAMILIES[:]
    if isinstance(font_families, str):
        raw_values = font_families.split(",")
    else:
        raw_values = list(font_families)

    families: list[str] = []
    seen = set()
    for value in raw_values:
        family = str(value or "").strip()
        if not family:
            continue
        key = family.lower()
        if key in seen:
            continue
        families.append(family[:80])
        seen.add(key)
    return families or CANVA_FONT_FAMILIES[:]


def _font_kind(font_family: str) -> str:
    lowered = font_family.lower()
    if any(word in lowered for word in (
        "script", "vibes", "pacifico", "lobster", "dancing", "roundhand", "brush",
        "satisfy", "yellowtail", "courgette", "sacramento", "allura", "parisienne",
        "calligraffitti", "cookie", "kaushan", "marck", "caveat", "handlee",
        "shadows", "permanent marker", "patrick hand"
    )):
        return "script"
    if any(word in lowered for word in (
        "playfair", "cinzel", "garamond", "merriweather", "bodoni", "georgia", "times",
        "abril", "baskerville", "cormorant", "prata", "serif", "lora", "vollkorn",
        "crimson", "bitter", "spectral", "cardo", "domine", "alegreya"
    )):
        return "serif"
    if any(word in lowered for word in (
        "bebas", "anton", "impact", "league", "goldman", "oswald", "bungee",
        "righteous", "fredoka", "alfa", "archivo black", "teko", "staatliches",
        "black ops", "luckiest", "passion one", "paytone", "rammetto"
    )):
        return "display"
    if any(word in lowered for word in ("monoton", "faster", "moonrocks", "shade", "ewert", "rye", "creepster", "frijole")):
        return "decorative"
    if any(word in lowered for word in ("courier", "mono", "code", "plex mono", "space mono", "source code")):
        return "mono"
    return "sans"


def _balanced_font_families(families: list[str], randomize_fonts: bool = True,
                            rng: random.Random | None = None) -> list[str]:
    rng = rng or _make_rng()
    groups: dict[str, list[str]] = {kind: [] for kind in FONT_KIND_ORDER}
    extras: list[str] = []
    seen = set()
    for family in families:
        family = str(family or "").strip()
        key = family.lower()
        if not family or key in seen:
            continue
        seen.add(key)
        kind = _font_kind(family)
        if kind in groups:
            groups[kind].append(family)
        else:
            extras.append(family)

    kind_order = FONT_KIND_ORDER[:]
    if randomize_fonts:
        rng.shuffle(kind_order)
        for values in groups.values():
            rng.shuffle(values)
        rng.shuffle(extras)

    ordered: list[str] = []
    while any(groups.values()):
        for kind in kind_order:
            if groups[kind]:
                ordered.append(groups[kind].pop(0))
    ordered.extend(extras)
    return ordered


def _apply_text_transform(text: str, transform: str | None) -> str:
    normalized = str(transform or "none").strip().lower()
    if normalized == "upper":
        return text.upper()
    if normalized == "lower":
        return text.lower()
    if normalized == "title":
        return text.title()
    return text


def _adaptive_modern_layout(style: dict[str, Any], text: str) -> str:
    layout = str(style.get("previewLayout") or "stacked")
    normalized = text.lower()
    lines = [line.strip() for line in text.splitlines() if line.strip()]

    if layout == "sale":
        has_discount = bool(re.search(r"\d+\s*%", text))
        has_sale_word = any(word in normalized for word in ("off", "sale", "discount"))
        return "sale" if has_discount or has_sale_word else "stacked"
    if layout == "coming_soon":
        return "coming_soon" if "coming" in normalized or "soon" in normalized else "stacked"
    if layout == "title_heading":
        heading_like = len(lines) <= 2 and any(word in normalized for word in ("title", "heading", "headline"))
        return "title_heading" if heading_like else "stacked"
    if layout == "arc":
        tattoo_like = any(word in normalized for word in ("tattoo", "studio", "brand", "logo"))
        short_arc = bool(lines and len(lines[0]) <= 14)
        return "arc" if tattoo_like or short_arc else "stacked"
    return layout


def _font_family_style(font_family: str, index: int) -> dict[str, Any]:
    kind = _font_kind(font_family)
    preset_by_kind = {
        "script": "engaged_script",
        "serif": "gold_serif",
        "display": "like_subscribe_hollow",
        "mono": "red_stamp_hollow",
        "decorative": "yellow_pop_outline",
        "sans": "neon_glow",
    }
    fallback_preset = STYLE_PRESETS[index % len(STYLE_PRESETS)]
    preset_name = preset_by_kind.get(kind)
    preset = next((style for style in STYLE_PRESETS if style.get("name") == preset_name), fallback_preset)
    style = _variant_from_preset(preset, index // len(STYLE_PRESETS))
    palette = [
        ("#111111", "", ""),
        ("#D8A919", "", "#E8D187"),
        ("#FF6F72", "#FFF0CB", "#FFB0A6"),
        ("#1B45F5", "#31FF38", ""),
        ("#FF5BB4", "#FF8BD0", "#FF44B0"),
        ("#0F6B5B", "", "#CFF7E4"),
        ("#F56C2D", "#FFE6A7", "#2EC4B6"),
        ("#FFFFFF", "#8B7DFF", "#8179FF"),
        ("#EF4E56", "#EF4E56", ""),
        ("#23B7E5", "", "#FF7A22"),
    ]
    fill, stroke, shadow = palette[index % len(palette)]
    style.update({
        "name": f"font_{re.sub(r'[^a-zA-Z0-9]+', '_', font_family).strip('_').lower() or index}",
        "fontFamily": font_family,
        "fill": fill,
        "stroke": stroke,
        "shadowColor": shadow,
        "strokeWidth": 2.4 if stroke else 0,
        "shadowBlur": 10 if shadow and index % 4 == 0 else style.get("shadowBlur", 0),
        "letterSpacing": 1.4 if kind in {"display", "mono", "decorative"} else 0,
        "fontStyle": "italic" if kind in {"script", "serif"} and index % 2 else "normal",
        "fontWeight": "normal" if kind == "script" else "bold",
        "lineHeight": 0.9 if kind in {"script", "serif"} else 0.98,
    })
    if kind == "script":
        style["fontSize"] = 50
    elif kind == "display":
        style["fontSize"] = 42
    elif kind == "mono":
        style["fontSize"] = 36
    elif kind == "decorative":
        style["fontSize"] = 38
        style["strokeWidth"] = 2.8 if style.get("stroke") else 0
    else:
        style["fontSize"] = 40
    return style


def _styles_for_font_families(font_families: list[str] | tuple[str, ...] | str | None,
                              count: int | None = None,
                              randomize_fonts: bool = True,
                              randomize_designs: bool = True,
                              rng: random.Random | None = None) -> list[dict[str, Any]]:
    rng = rng or _make_rng()
    families = _balanced_font_families(
        _normalize_font_families(font_families),
        randomize_fonts=randomize_fonts,
        rng=rng,
    )
    if count is not None and count > 0:
        families = families[:count]
    styles = [_font_family_style(family, index) for index, family in enumerate(families)]
    if randomize_designs:
        used_designs: set[tuple[Any, ...]] = set()
        styles = [_apply_random_design(style, rng, index, used_designs) for index, style in enumerate(styles)]
    return styles


def _intent_terms(text: str, mood: str | None) -> list[str]:
    raw = f"{text} {mood or ''}".lower()
    terms = re.findall(r"[a-z0-9%]+", raw)

    intent_groups = [
        (("birthday", "bday", "party", "celebrate", "celebration"), ["birthday", "happy", "marker", "pop", "script"]),
        (("thank", "thanks", "grateful", "gratitude"), ["thank", "you", "clean", "serif", "script"]),
        (("bride", "groom", "wedding", "engaged", "engagement", "love"), ["bride", "groom", "luxury", "rose", "script"]),
        (("sale", "off", "discount", "%", "deal", "offer"), ["sale", "discount", "bold", "outline", "condensed"]),
        (("open", "opening", "launch", "new"), ["open", "neon", "glow", "bold"]),
        (("logo", "brand", "studio", "tattoo"), ["logo", "studio", "badge", "arc", "clean"]),
        (("target", "roadmap", "quarter", "business", "report"), ["editorial", "mono", "label", "clean"]),
        (("royal", "gold", "luxury", "premium"), ["royal", "gold", "luxury", "serif"]),
        (("neon", "glow", "night"), ["neon", "glow", "outline"]),
    ]
    for needles, additions in intent_groups:
        if any(needle in raw for needle in needles):
            terms.extend(additions)
    return terms


def _style_search_text(style: dict[str, Any]) -> str:
    return " ".join(
        str(style.get(key, ""))
        for key in ("name", "category", "fontFamily", "sample", "previewLayout", "textTransform")
    ).lower()


def _local_style_library(text: str, mood: str | None, rng: random.Random,
                         randomize: bool) -> list[dict[str, Any]]:
    library = [deepcopy(style) for style in STYLE_PRESETS]
    library.extend(deepcopy(style) for style in MODERN_MAGIC_WRITE_DATASET)
    terms = [term for term in _intent_terms(text, mood) if len(term) >= 2]

    scored: list[tuple[int, int, dict[str, Any]]] = []
    for index, style in enumerate(library):
        haystack = _style_search_text(style)
        score = sum(3 if term in haystack else 0 for term in terms)
        kind = _font_kind(str(style.get("fontFamily") or ""))
        if kind in terms:
            score += 2
        scored.append((score, index, style))

    if any(score for score, _, _ in scored):
        scored.sort(key=lambda item: (-item[0], item[1]))
        return [style for _, _, style in scored]

    if randomize:
        rng.shuffle(library)
    return library


def _style_candidates(text: str, count: int, mood: str | None,
                      randomize_fonts: bool = True,
                      randomize_designs: bool = True,
                      rng: random.Random | None = None) -> list[dict[str, Any]]:
    rng = rng or _make_rng()
    base_styles = _local_style_library(text, mood, rng, randomize_fonts)
    used_fonts: set[str] = set()
    used_designs: set[tuple[Any, ...]] = set()
    styles: list[dict[str, Any]] = []

    for index in range(count):
        base = deepcopy(base_styles[index % len(base_styles)])
        style = _variant_from_preset(base, index // len(base_styles))
        if randomize_fonts:
            style = _randomize_style_font(style, rng, used_fonts)
        if randomize_designs:
            style = _apply_random_design(style, rng, index, used_designs)
        styles.append(style)
    return styles


def _font_cache_path(family: str, bold: bool, italic: bool = False) -> Path | None:
    family_key = re.sub(r"[^a-zA-Z0-9]+", "_", family).strip("_").lower()
    variants = []
    if bold and italic:
        variants.extend(["700italic", "italic", "700", "regular"])
    elif bold:
        variants.extend(["700", "regular"])
    elif italic:
        variants.extend(["italic", "regular"])
    else:
        variants.extend(["regular", "700"])
    for cache_dir in FONT_CACHE_DIRS:
        for variant in variants:
            path = cache_dir / f"{family_key}__{variant}.ttf"
            if path.exists():
                return path
    return None


def _download_google_font(family: str, bold: bool = False, italic: bool = False) -> Path | None:
    global _google_font_network_ok
    if not _google_font_network_ok:
        return None

    family_key = re.sub(r"[^a-zA-Z0-9]+", "_", family).strip("_").lower() or "font"
    variants = []
    if bold and italic:
        variants.extend(["700italic", "italic", "700", "regular"])
    elif bold:
        variants.extend(["700", "regular"])
    elif italic:
        variants.extend(["italic", "regular"])
    else:
        variants.append("regular")

    for variant in variants:
        cache_path = PRIMARY_FONT_CACHE_DIR / f"{family_key}__{variant}.ttf"
        if cache_path.exists():
            return cache_path
        missing_path = cache_path.with_suffix(".missing")
        if missing_path.exists():
            continue

        query = family if variant == "regular" else f"{family}:{variant}"
        css_url = "https://fonts.googleapis.com/css?family=" + urllib.parse.quote(query)
        try:
            css = _http_get(css_url, timeout=8, headers={"User-Agent": GOOGLE_FONT_UA}).decode("utf-8", "ignore")
            match = GOOGLE_FONT_URL_RE.search(css)
            if not match:
                PRIMARY_FONT_CACHE_DIR.mkdir(parents=True, exist_ok=True)
                missing_path.touch()
                continue
            font_bytes = _http_get(match.group(1), timeout=15, headers={"User-Agent": GOOGLE_FONT_UA})
            PRIMARY_FONT_CACHE_DIR.mkdir(parents=True, exist_ok=True)
            cache_path.write_bytes(font_bytes)
            return cache_path
        except urllib.error.HTTPError as exc:
            if exc.code in {400, 404}:
                PRIMARY_FONT_CACHE_DIR.mkdir(parents=True, exist_ok=True)
                missing_path.touch()
                continue
            print(f"warning: couldn't download Google font {family!r} ({variant}): {exc}", file=sys.stderr)
            return None
        except urllib.error.URLError as exc:
            print(f"warning: couldn't download Google font {family!r} ({variant}): {exc}", file=sys.stderr)
            _google_font_network_ok = False
            return None
        except OSError as exc:
            print(f"warning: couldn't download Google font {family!r} ({variant}): {exc}", file=sys.stderr)
            return None
    return None


def _system_font_path(family: str, bold: bool, allow_default: bool = True) -> Path | None:
    lowered = family.strip().lower()
    if bold and lowered in {"arial", "georgia"}:
        lowered = f"{lowered} bold"
    candidates = []
    if lowered in FONT_FILES:
        candidates.append(MAC_FONT_DIR / FONT_FILES[lowered])
    if "brush" in lowered:
        candidates.append(MAC_FONT_DIR / FONT_FILES["brush script"])
    if "script" in lowered or "vibes" in lowered or "roundhand" in lowered:
        candidates.append(MAC_FONT_DIR / FONT_FILES["snell roundhand"])
    if "serif" in lowered or "gold" in lowered or "georgia" in lowered:
        candidates.append(MAC_FONT_DIR / ("Georgia Bold.ttf" if bold else "Georgia.ttf"))
    if allow_default:
        candidates.extend(
            [
                MAC_FONT_DIR / ("Arial Bold.ttf" if bold else "Arial.ttf"),
                MAC_CORE_FONT_DIR / "Helvetica.ttc",
            ]
        )
    linux_sans = "DejaVuSans-Bold.ttf" if bold else "DejaVuSans.ttf"
    linux_serif = "DejaVuSerif-Bold.ttf" if bold else "DejaVuSerif.ttf"
    linux_mono = "DejaVuSansMono-Bold.ttf" if bold else "DejaVuSansMono.ttf"
    if "mono" in lowered or "courier" in lowered:
        candidates.extend(font_dir / linux_mono for font_dir in LINUX_FONT_DIRS)
    elif "serif" in lowered or lowered in {"georgia", "times new roman", "times new roman bold"}:
        candidates.extend(font_dir / linux_serif for font_dir in LINUX_FONT_DIRS)
    if allow_default:
        candidates.extend(font_dir / linux_sans for font_dir in LINUX_FONT_DIRS)
    return next((p for p in candidates if p.exists()), None)


def _load_font(family: str, size: float, weight: str | None = None, italic: bool = False) -> ImageFont.FreeTypeFont:
    bold = str(weight or "").strip().lower() in {"bold", "700", "600", "semibold", "semi-bold"}
    path = (
        _font_cache_path(family, bold, italic)
        or _system_font_path(family, bold, allow_default=False)
        or _download_google_font(family, bold, italic)
        or _system_font_path(family, bold, allow_default=True)
    )
    if path:
        return ImageFont.truetype(str(path), max(int(round(size)), 1))
    return ImageFont.load_default()


def _line_width(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.ImageFont, spacing: float) -> float:
    if not text:
        return 0
    width = sum(draw.textlength(ch, font=font) for ch in text)
    return width + max(len(text) - 1, 0) * spacing


def _fit_text_box(text_obj: dict[str, Any], canvas_width: int, canvas_height: int) -> dict[str, Any]:
    obj = deepcopy(text_obj)
    lines = str(obj["text"]).splitlines() or [str(obj["text"])]
    font_size = float(obj["fontSize"])
    spacing = float(obj.get("letterSpacing") or 0)
    line_height = float(obj.get("lineHeight") or 1.0)
    draw = ImageDraw.Draw(Image.new("RGBA", (10, 10)))
    max_width = canvas_width - 100
    max_height = canvas_height - 80

    while font_size > 8:
        font = _load_font(
            obj["fontFamily"],
            font_size,
            obj.get("fontWeight"),
            str(obj.get("fontStyle") or "").lower() == "italic",
        )
        widths = [_line_width(draw, line, font, spacing) for line in lines]
        total_h = len(lines) * font_size * line_height
        if (max(widths or [0]) <= max_width) and total_h <= max_height:
            break
        font_size *= 0.94

    obj["fontSize"] = font_size
    obj["width"] = min(max_width, max(max(widths or [0]), 80) + 24)
    obj["height"] = max(len(lines) * font_size * line_height + 12, font_size + 12)
    obj["x"] = (canvas_width - obj["width"]) / 2
    obj["y"] = (canvas_height - obj["height"]) / 2
    return obj


def _konva_text(text: str, style: dict[str, Any], z_index: int, canvas_width: int, canvas_height: int) -> dict[str, Any]:
    raw_text = text
    layout = _adaptive_modern_layout(style, raw_text)
    if layout in {"sale", "title_heading", "coming_soon", "signature", "glow_signature", "arc"}:
        text = raw_text
    else:
        text = _apply_text_transform(raw_text, style.get("textTransform"))
    fill = _clean_hex(style.get("fill"), "#111111")
    stroke = _clean_hex(style.get("stroke"), "")
    shadow = _clean_hex(style.get("shadowColor"), "")
    decoration = str(style.get("textDecoration") or "").strip().lower()
    if decoration not in {"", "underline", "line-through"}:
        decoration = ""
    font_style = str(style.get("fontStyle") or "normal").strip().lower()
    if font_style not in {"normal", "italic"}:
        font_style = "normal"
    align = str(style.get("align") or style.get("textAlign") or "center").strip().lower()
    if align not in {"left", "center", "right"}:
        align = "center"

    stroke_width = _clamp_number(style.get("strokeWidth"), 0, 0, 8) if stroke else 0
    obj = {
        "id": f"text_{uuid.uuid4()}",
        "type": "Text",
        "x": 50.0,
        "y": 154.0,
        "width": canvas_width - 100,
        "height": 112,
        "scaleX": 1,
        "scaleY": 1,
        "rotation": _clamp_number(style.get("rotation"), 0, -18, 18),
        "opacity": 1,
        "draggable": True,
        "zIndex": z_index,
        "text": text,
        "fontSize": _clamp_number(style.get("fontSize"), 36, 8, 96),
        "fontFamily": str(style.get("fontFamily") or "Arial").strip()[:80] or "Arial",
        "fontWeight": str(style.get("fontWeight") or "normal").strip()[:20] or "normal",
        "fontStyle": font_style,
        "fill": fill,
        "align": align,
        "textAlign": align,
        "wrap": "none",
        "letterSpacing": _clamp_number(style.get("letterSpacing"), 0, -1, 6),
        "lineHeight": _clamp_number(style.get("lineHeight"), 1.0, 0.75, 1.5),
        "padding": 0,
        "textDecoration": decoration,
        "shadowColor": shadow,
        "shadowBlur": _clamp_number(style.get("shadowBlur"), 0, 0, 30),
        "shadowOffsetX": _clamp_number(style.get("shadowOffsetX"), 0, -20, 20),
        "shadowOffsetY": _clamp_number(style.get("shadowOffsetY"), 0, -20, 20),
        "stroke": stroke,
        "strokeWidth": stroke_width,
        "ellipsis": False,
        "listening": True,
        "magicWriteStyle": str(style.get("name") or ""),
        "magicWriteCategory": str(style.get("category") or ""),
        "magicWriteLayout": layout,
        "textTransform": str(style.get("textTransform") or "none"),
        "accentFill": _clean_hex(style.get("accentFill"), ""),
    }
    return _fit_text_box(obj, canvas_width, canvas_height)


def _text_lines(text: str) -> list[str]:
    lines = [line.strip() for line in str(text or "").splitlines() if line.strip()]
    if lines:
        return lines
    words = re.findall(r"\S+", str(text or ""))
    return words or [str(text or "").strip() or "Text"]


def _split_display_lines(text: str, max_lines: int = 2) -> list[str]:
    lines = _text_lines(text)
    connectors = {"&", "+", "and", "AND"}
    compacted: list[str] = []
    index = 0
    while index < len(lines):
        if index + 2 < len(lines) and lines[index + 1].strip() in connectors:
            compacted.append(f"{lines[index]} {lines[index + 1].strip()}")
            compacted.append(lines[index + 2])
            index += 3
            continue
        compacted.append(lines[index])
        index += 1

    if len(compacted) <= max_lines:
        return compacted
    lines = compacted
    words = re.findall(r"\S+", " ".join(lines))
    if len(words) <= 2:
        return [" ".join(words)] if words else lines
    midpoint = max(1, len(words) // 2)
    return [" ".join(words[:midpoint]), " ".join(words[midpoint:])]


def _layer_text(
    text: str,
    style: dict[str, Any],
    z_index: int,
    x: float,
    y: float,
    width: float,
    height: float,
) -> dict[str, Any]:
    fill = _clean_hex(style.get("fill"), "#111111")
    stroke = _clean_hex(style.get("stroke"), "")
    shadow = _clean_hex(style.get("shadowColor"), "")
    decoration = str(style.get("textDecoration") or "").strip().lower()
    if decoration not in {"", "underline", "line-through"}:
        decoration = ""
    font_style = str(style.get("fontStyle") or "normal").strip().lower()
    if font_style not in {"normal", "italic"}:
        font_style = "normal"
    align = str(style.get("align") or style.get("textAlign") or "center").strip().lower()
    if align not in {"left", "center", "right"}:
        align = "center"

    return {
        "id": f"text_{uuid.uuid4()}",
        "type": "Text",
        "x": float(x),
        "y": float(y),
        "width": float(width),
        "height": float(height),
        "scaleX": 1,
        "scaleY": 1,
        "rotation": _clamp_number(style.get("rotation"), 0, -18, 18),
        "opacity": 1,
        "draggable": True,
        "zIndex": z_index,
        "text": str(text),
        "fontSize": _clamp_number(style.get("fontSize"), 36, 8, 120),
        "fontFamily": str(style.get("fontFamily") or "Arial").strip()[:80] or "Arial",
        "fontWeight": str(style.get("fontWeight") or "normal").strip()[:20] or "normal",
        "fontStyle": font_style,
        "fill": fill,
        "align": align,
        "textAlign": align,
        "wrap": "none",
        "letterSpacing": _clamp_number(style.get("letterSpacing"), 0, -1, 8),
        "lineHeight": _clamp_number(style.get("lineHeight"), 1.0, 0.65, 1.6),
        "padding": 0,
        "textDecoration": decoration,
        "shadowColor": shadow,
        "shadowBlur": _clamp_number(style.get("shadowBlur"), 0, 0, 30),
        "shadowOffsetX": _clamp_number(style.get("shadowOffsetX"), 0, -20, 20),
        "shadowOffsetY": _clamp_number(style.get("shadowOffsetY"), 0, -20, 20),
        "stroke": stroke,
        "strokeWidth": _clamp_number(style.get("strokeWidth"), 0, 0, 8) if stroke else 0,
        "ellipsis": False,
        "listening": True,
        "magicWriteRole": str(style.get("role") or ""),
    }


def _composition_group(
    name: str,
    category: str,
    children: list[dict[str, Any]],
    z_index: int,
    canvas_width: int,
    canvas_height: int,
) -> dict[str, Any]:
    return {
        "id": f"group_{uuid.uuid4()}",
        "type": "Group",
        "x": 0,
        "y": 0,
        "width": canvas_width,
        "height": canvas_height,
        "scaleX": 1,
        "scaleY": 1,
        "rotation": 0,
        "opacity": 1,
        "draggable": True,
        "zIndex": z_index,
        "children": children,
        "magicWriteStyle": name,
        "magicWriteCategory": category,
        "magicWriteLayout": "composition",
        "listening": True,
    }


def _text_visual_height_for_child(child: dict[str, Any]) -> float:
    text = str(child.get("text") or "")
    lines = text.splitlines() or [text]
    size = float(child.get("fontSize") or 36)
    italic = str(child.get("fontStyle") or "").lower() == "italic"
    font = _load_font(child.get("fontFamily", "Arial"), size, child.get("fontWeight"), italic)
    draw = ImageDraw.Draw(Image.new("RGBA", (10, 10)))
    heights = []
    for line in lines:
        bbox = draw.textbbox((0, 0), line or " ", font=font)
        heights.append(max(bbox[3] - bbox[1], size * 0.5))
    return sum(heights) * float(child.get("lineHeight") or 1.0)


def _tighten_composition_children(children: list[dict[str, Any]], canvas_height: int) -> list[dict[str, Any]]:
    if not children:
        return children
    ordered = sorted((deepcopy(child) for child in children), key=lambda child: int(child.get("zIndex") or 0))
    visible_text_children = [child for child in ordered if str(child.get("text") or "").strip()]
    primary_text_children = [
        child
        for child in visible_text_children
        if str(child.get("magicWriteRole") or "") != "middle"
    ]
    if len(primary_text_children) >= 2:
        sizes = [float(child.get("fontSize") or 36) for child in primary_text_children]
        balanced = _clamp_number(sum(sizes) / len(sizes), 42, 34, 54)
        for child in primary_text_children:
            child["fontSize"] = balanced
            child["height"] = max(float(child.get("height") or balanced), balanced + 8)
        visual_heights = [_text_visual_height_for_child(child) for child in primary_text_children]
        target_visual_h = max(visual_heights or [balanced])
        for child, visual_h in zip(primary_text_children, visual_heights):
            if visual_h > 0:
                child["fontSize"] = _clamp_number(
                    float(child.get("fontSize") or balanced) * (target_visual_h / visual_h),
                    balanced,
                    26,
                    58,
                )
                child["height"] = max(float(child.get("height") or 0), float(child["fontSize"]) + 8)
        for child in visible_text_children:
            if str(child.get("magicWriteRole") or "") == "middle":
                middle_size = _clamp_number(balanced * 0.72, 30, 24, 38)
                child["fontSize"] = middle_size
                child["height"] = max(float(child.get("height") or middle_size), middle_size + 6)

    compact: list[dict[str, Any]] = []
    for child in ordered:
        text = str(child.get("text") or "")
        lines = text.splitlines() or [text]
        font_size = float(child.get("fontSize") or 36)
        line_height = float(child.get("lineHeight") or 1.0)
        natural_h = max(len(lines) * font_size * line_height, font_size)
        shadow_pad = float(child.get("shadowBlur") or 0) * 1.4
        child["height"] = min(float(child.get("height") or natural_h), natural_h + 8 + shadow_pad)
        compact.append(child)

    gaps: list[float] = []
    for current, next_child in zip(compact, compact[1:]):
        current_role = str(current.get("magicWriteRole") or "")
        next_role = str(next_child.get("magicWriteRole") or "")
        if current_role == "top" and next_role == "middle":
            gaps.append(2)
        elif current_role == "middle" and next_role == "main":
            gaps.append(0)
        elif current_role in {"script", "serif", "sub"} and next_role == "main":
            gaps.append(-2)
        else:
            gaps.append(4)

    total_h = sum(float(child.get("height") or 0) for child in compact) + sum(gaps)
    y = (canvas_height - total_h) / 2
    for index, child in enumerate(compact):
        child["y"] = float(y)
        y += float(child.get("height") or 0)
        if index < len(gaps):
            y += gaps[index]
    return compact


def _use_single_font_family_per_group(children: list[dict[str, Any]]) -> list[dict[str, Any]]:
    primary = next(
        (
            child
            for child in children
            if isinstance(child, dict) and str(child.get("magicWriteRole") or "") == "main"
        ),
        None,
    )
    fallback = next((child for child in children if isinstance(child, dict)), None)
    family = str((primary or fallback or {}).get("fontFamily") or "").strip()
    if not family:
        return children
    for child in children:
        if isinstance(child, dict) and child.get("type") == "Text":
            child["fontFamily"] = family
    return children


def _remove_duplicate_text_children(children: list[dict[str, Any]]) -> list[dict[str, Any]]:
    children = [
        child
        for child in children
        if not isinstance(child, dict)
        or child.get("type") != "Text"
        or str(child.get("text") or "").strip()
    ]
    grouped: dict[str, list[dict[str, Any]]] = {}
    order: list[str] = []
    for child in children:
        if not isinstance(child, dict):
            continue
        key = re.sub(r"\s+", " ", str(child.get("text") or "").strip()).lower()
        if not key:
            continue
        if key not in grouped:
            grouped[key] = []
            order.append(key)
        grouped[key].append(child)

    keep_ids: set[str] = set()
    for key in order:
        candidates = grouped[key]
        chosen = next(
            (child for child in candidates if str(child.get("magicWriteRole") or "") == "main"),
            max(candidates, key=lambda child: float(child.get("fontSize") or 0)),
        )
        keep_ids.add(str(chosen.get("id") or ""))

    return [
        child
        for child in children
        if not isinstance(child, dict)
        or not str(child.get("text") or "").strip()
        or str(child.get("id") or "") in keep_ids
    ]


def _modern_palette_value(palette: dict[str, str], mode: str) -> str:
    return _clean_hex(palette.get(mode), "") if mode else ""


def _hex_luminance(hex_color: str) -> float:
    color = _clean_hex(hex_color, "#000000").lstrip("#")
    channels = [int(color[index:index + 2], 16) / 255 for index in (0, 2, 4)]
    linear = [
        value / 12.92 if value <= 0.03928 else ((value + 0.055) / 1.055) ** 2.4
        for value in channels
    ]
    return 0.2126 * linear[0] + 0.7152 * linear[1] + 0.0722 * linear[2]


def _strengthen_transparent_text_contrast(children: list[dict[str, Any]]) -> list[dict[str, Any]]:
    adjusted = deepcopy(children)
    for child in adjusted:
        if not isinstance(child, dict) or child.get("type") != "Text":
            continue
        fill = _clean_hex(child.get("fill"), "#111111")
        stroke = _clean_hex(child.get("stroke"), "")
        stroke_width = float(child.get("strokeWidth") or 0)
        shadow = _clean_hex(child.get("shadowColor"), "")
        shadow_blur = float(child.get("shadowBlur") or 0)
        has_edge = bool(stroke and stroke_width >= 0.8) or bool(shadow and shadow_blur >= 3)
        if has_edge:
            continue

        luminance = _hex_luminance(fill)
        if luminance < 0.28:
            continue
        elif luminance > 0.82:
            child["stroke"] = "#1F2937"
            child["strokeWidth"] = max(stroke_width, 0.9)
            child["shadowColor"] = "#1F2937"
            child["shadowBlur"] = max(shadow_blur, 1.2)
            child["shadowOffsetX"] = max(float(child.get("shadowOffsetX") or 0), 1.0)
            child["shadowOffsetY"] = max(float(child.get("shadowOffsetY") or 0), 1.4)
    return adjusted


def _composition_alpha_bbox(
    children: list[dict[str, Any]],
    canvas_width: int,
    canvas_height: int,
    scale: int = 2,
) -> tuple[float, float, float, float] | None:
    width = canvas_width * scale
    height = canvas_height * scale
    img = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    ordered = [child for child in children if isinstance(child, dict)]
    ordered.sort(key=lambda child: int(child.get("zIndex") or 0))
    for child in ordered:
        if child.get("type") == "Text":
            _draw_text_object_on_layer(img, child, scale)
    bbox = img.getchannel("A").getbbox()
    if not bbox:
        return None
    return tuple(value / scale for value in bbox)  # type: ignore[return-value]


def _scale_child_geometry(child: dict[str, Any], origin: tuple[float, float], factor: float) -> None:
    ox, oy = origin
    child["x"] = ox + (float(child.get("x") or 0) - ox) * factor
    child["y"] = oy + (float(child.get("y") or 0) - oy) * factor
    for key in ("width", "height", "fontSize", "strokeWidth", "shadowBlur", "letterSpacing"):
        child[key] = float(child.get(key) or 0) * factor
    for key in ("shadowOffsetX", "shadowOffsetY"):
        child[key] = float(child.get(key) or 0) * factor


def _shift_child_geometry(child: dict[str, Any], dx: float, dy: float) -> None:
    child["x"] = float(child.get("x") or 0) + dx
    child["y"] = float(child.get("y") or 0) + dy


def _fit_composition_children_to_canvas(
    children: list[dict[str, Any]],
    canvas_width: int,
    canvas_height: int,
) -> list[dict[str, Any]]:
    fitted = deepcopy(children)
    bbox = _composition_alpha_bbox(fitted, canvas_width, canvas_height)
    if not bbox:
        return fitted

    left, top, right, bottom = bbox
    bbox_w = max(right - left, 1)
    bbox_h = max(bottom - top, 1)
    min_w = canvas_width * 0.62
    min_h = canvas_height * 0.18
    max_w = canvas_width * 0.88
    max_h = canvas_height * 0.58

    max_fit = min(max_w / bbox_w, max_h / bbox_h)
    grow = max(min_w / bbox_w, min_h / bbox_h, 1.0)
    factor = min(grow, max_fit, 1.9) if grow > 1.0 else min(max_fit, 1.0)
    if factor > 1.01 or factor < 0.99:
        origin = ((left + right) / 2, (top + bottom) / 2)
        for child in fitted:
            if isinstance(child, dict) and child.get("type") == "Text":
                _scale_child_geometry(child, origin, factor)

    bbox = _composition_alpha_bbox(fitted, canvas_width, canvas_height)
    if not bbox:
        return fitted
    left, top, right, bottom = bbox
    target_cx = canvas_width / 2
    target_cy = canvas_height / 2
    dx = target_cx - (left + right) / 2
    dy = target_cy - (top + bottom) / 2
    pad = canvas_width * 0.04
    if left + dx < pad:
        dx += pad - (left + dx)
    if right + dx > canvas_width - pad:
        dx -= (right + dx) - (canvas_width - pad)
    if top + dy < pad:
        dy += pad - (top + dy)
    if bottom + dy > canvas_height - pad:
        dy -= (bottom + dy) - (canvas_height - pad)
    for child in fitted:
        if isinstance(child, dict) and child.get("type") == "Text":
            _shift_child_geometry(child, dx, dy)

    return fitted


def _modern_composition_signature(children: list[dict[str, Any]]) -> tuple[Any, ...]:
    parts: list[Any] = []
    for child in children:
        if not isinstance(child, dict) or child.get("type") != "Text":
            continue
        parts.extend(
            (
                str(child.get("magicWriteRole") or ""),
                str(child.get("fill") or ""),
                str(child.get("stroke") or ""),
                round(float(child.get("strokeWidth") or 0), 2),
                str(child.get("shadowColor") or ""),
                round(float(child.get("shadowBlur") or 0), 2),
                round(float(child.get("shadowOffsetX") or 0), 2),
                round(float(child.get("shadowOffsetY") or 0), 2),
                round(float(child.get("letterSpacing") or 0), 2),
                round(float(child.get("rotation") or 0), 2),
            )
        )
    return tuple(parts)


def _modern_design_choices(
    index: int,
    rng: random.Random,
    randomize_designs: bool,
    used_designs: set[tuple[str, str]],
    used_palettes: set[str],
    used_effects: set[str],
) -> tuple[dict[str, str], dict[str, Any]]:
    palettes_by_name = {str(palette["name"]): palette for palette in MODERN_COMPOSITION_PALETTES}
    effects_by_name = {str(effect["name"]): effect for effect in MODERN_COMPOSITION_EFFECTS}
    featured = [
        (palettes_by_name[palette_name], effects_by_name[effect_name])
        for palette_name, effect_name in MODERN_FEATURED_DESIGN_SEQUENCE
        if palette_name in palettes_by_name and effect_name in effects_by_name
    ]
    for offset in range(len(featured)):
        palette, effect = featured[(index + offset) % len(featured)]
        signature = (str(palette["name"]), str(effect["name"]))
        if signature not in used_designs:
            used_designs.add(signature)
            used_palettes.add(str(palette["name"]))
            used_effects.add(str(effect["name"]))
            return palette, effect

    palettes = _shuffle_copy(MODERN_COMPOSITION_PALETTES, rng) if randomize_designs else MODERN_COMPOSITION_PALETTES[:]
    effects = _shuffle_copy(MODERN_COMPOSITION_EFFECTS, rng) if randomize_designs else MODERN_COMPOSITION_EFFECTS[:]
    palette_pool = [palette for palette in palettes if str(palette["name"]) not in used_palettes] or palettes
    effect_pool = [effect for effect in effects if str(effect["name"]) not in used_effects] or effects

    for palette in palette_pool:
        for effect in effect_pool:
            signature = (str(palette["name"]), str(effect["name"]))
            if signature not in used_designs:
                used_designs.add(signature)
                used_palettes.add(str(palette["name"]))
                used_effects.add(str(effect["name"]))
                return palette, effect

    palette = palettes[index % len(palettes)]
    effect = effects[(index // len(palettes)) % len(effects)]
    used_designs.add((str(palette["name"]), str(effect["name"])))
    used_palettes.add(str(palette["name"]))
    used_effects.add(str(effect["name"]))
    return palette, effect


def _apply_modern_composition_design(
    children: list[dict[str, Any]],
    kind: str,
    index: int,
    rng: random.Random,
    randomize_designs: bool,
    used_designs: set[tuple[str, str]],
    used_palettes: set[str],
    used_effects: set[str],
) -> tuple[list[dict[str, Any]], str, str]:
    palette, effect = _modern_design_choices(
        index,
        rng,
        randomize_designs,
        used_designs,
        used_palettes,
        used_effects,
    )
    fill_mode = str(effect.get("fillMode") or "primary")
    stroke_mode = str(effect.get("strokeMode") or "")
    shadow_mode = str(effect.get("shadowMode") or "")
    base_stroke = float(effect.get("strokeWidth") or 0)
    base_shadow_blur = float(effect.get("shadowBlur") or 0)
    base_shadow_x = float(effect.get("shadowOffsetX") or 0)
    base_shadow_y = float(effect.get("shadowOffsetY") or 0)
    effect_name = str(effect.get("name") or "custom")
    designed = deepcopy(children)

    for child in designed:
        if not isinstance(child, dict) or child.get("type") != "Text":
            continue
        role = str(child.get("magicWriteRole") or "main")
        is_main = role == "main" or len(designed) == 1
        role_fill_mode = fill_mode if is_main else ("secondary" if fill_mode != "secondary" else "primary")
        if effect_name in {"glow_tube", "warm_neon"}:
            role_fill_mode = "light"
        elif effect_name == "reverse_outline" and not is_main:
            role_fill_mode = "primary"
        elif effect_name == "sticker" and not is_main:
            role_fill_mode = "primary"
        child["fill"] = _modern_palette_value(palette, role_fill_mode) or str(child.get("fill") or "#111111")

        stroke = _modern_palette_value(palette, stroke_mode)
        if effect_name == "solid" and not is_main:
            stroke = ""
        child["stroke"] = stroke
        child["strokeWidth"] = base_stroke if stroke else 0

        shadow = _modern_palette_value(palette, shadow_mode)
        child["shadowColor"] = shadow
        child["shadowBlur"] = base_shadow_blur if shadow else 0
        child["shadowOffsetX"] = base_shadow_x if shadow else 0
        child["shadowOffsetY"] = base_shadow_y if shadow else 0

        if role in {"script", "serif"}:
            child["letterSpacing"] = min(float(child.get("letterSpacing") or 0), 0.6)
            child["rotation"] = float(child.get("rotation") or 0) + (rng.choice([-2, -1, 0, 1, 2]) if randomize_designs else 0)
        elif role in {"top", "sub"}:
            child["letterSpacing"] = max(float(child.get("letterSpacing") or 0), 1.2 + (index % 3) * 0.4)
        else:
            child["letterSpacing"] = max(float(child.get("letterSpacing") or 0), (index % 4) * 0.25)

        if kind in {"light_script", "neon_glow", "neon_open"} and effect_name in {"glow_tube", "warm_neon"}:
            child["fill"] = _modern_palette_value(palette, "light") or "#FFFFFF"
            child["stroke"] = _modern_palette_value(palette, "accent") or child["stroke"]
            child["strokeWidth"] = max(float(child.get("strokeWidth") or 0), 1.1)
            child["shadowColor"] = _modern_palette_value(palette, "glow") or child["stroke"]
            child["shadowBlur"] = max(float(child.get("shadowBlur") or 0), 16 + (index % 3) * 2)
            child["shadowOffsetX"] = 0
            child["shadowOffsetY"] = 0
        elif kind in {"golden_hour", "editorial_caps"} and effect_name == "solid":
            child["shadowColor"] = _modern_palette_value(palette, "shadow")
            child["shadowBlur"] = 1.2
            child["shadowOffsetX"] = 1.5
            child["shadowOffsetY"] = 2.2

    return designed, str(palette["name"]), effect_name


def _composition_text_for_kind(text: str, kind: str) -> dict[str, Any]:
    normalized = text.lower()
    lines = _text_lines(text)
    display_lines = _split_display_lines(text, 2)
    display_first = display_lines[0] if display_lines else (lines[0] if lines else text)
    display_second = display_lines[1] if len(display_lines) > 1 else ""
    first = lines[0] if lines else text
    second = lines[1] if len(lines) > 1 else ""
    third = lines[2] if len(lines) > 2 else ""

    if kind in {"light_script", "neon_glow"}:
        return {"main": " ".join(display_lines)}
    if kind == "thank_you":
        if len(lines) >= 3 and second.strip() in {"&", "+", "and", "AND"}:
            return {"top": first.upper(), "middle": second.strip(), "main": third.upper()}
        if "thank" in normalized and "you" in normalized:
            return {"top": "THANK", "middle": "", "main": "YOU"}
        if len(lines) >= 2:
            return {"top": first.upper(), "middle": "", "main": second.upper()}
        return {"top": "", "middle": "", "main": first.upper()}
    if kind == "happy_birthday":
        if "birthday" in normalized:
            return {"script": "Happy", "main": "BIRTHDAY"}
        if len(lines) >= 2:
            return {"script": first, "main": "\n".join(line.upper() for line in lines[1:3])}
        return {"script": "", "main": first.upper()}
    if kind == "bride_groom":
        if "bride" in normalized or "groom" in normalized:
            return {"script": "Bride &", "main": "GROOM"}
        if len(lines) >= 3 and second.strip() == "&":
            return {"script": f"{first} &", "main": third}
        if len(lines) >= 2:
            return {"script": first, "main": second}
        return {"script": "", "main": first}
    if kind == "golden_hour":
        return {"main": "\n".join(line.upper() for line in display_lines)}
    if kind == "script_club":
        return {"script": " ".join(display_lines), "sub": ""}
    if kind == "xoxo":
        return {"main": " ".join(display_lines).upper()}
    if kind == "studio_badge":
        return {"main": "\n".join(display_lines).upper(), "badge": ""}
    if kind == "streaming_now":
        return {"script": display_first if display_second else "", "main": (display_second or display_first).upper()}
    if kind == "quarterly_targets":
        return {"sub": display_first.upper() if display_second else "", "main": (display_second or display_first).upper()}
    if kind == "quarter_roadmap":
        return {"serif": display_first if display_second else "", "main": (display_second or display_first).upper()}
    if kind == "neon_open":
        return {"main": "\n".join(display_lines)}
    if kind == "editorial_caps":
        return {"main": "\n".join(line.upper() for line in display_lines)}
    return {"script": first if len(lines) > 1 else "", "main": "\n".join(lines[1:]) if len(lines) > 1 else first}


def _modern_composition_variant(
    text: str,
    template: dict[str, Any],
    index: int,
    rng: random.Random,
    canvas_width: int,
    canvas_height: int,
    used_fonts: set[str],
    used_designs: set[tuple[str, str]],
    used_palettes: set[str],
    used_effects: set[str],
    randomize_designs: bool,
) -> dict[str, Any]:
    kind = str(template.get("kind") or "luxury_names")
    data = _composition_text_for_kind(text, kind)
    margin = canvas_width * 0.08
    full_w = canvas_width - margin * 2
    z_base = index * 10 + 1

    def pick_font(kind_name: str, extra_pool: list[str] | None = None) -> str:
        pool = extra_pool or CANVA_FONT_GROUPS[kind_name]
        return _pick_unused_font_with_global_fallback(pool, rng, used_fonts)

    def script_font() -> str:
        return pick_font("script")

    def serif_font() -> str:
        return pick_font("serif")

    def display_font() -> str:
        strong_display = [
            "Bebas Neue",
            "Anton",
            "League Spartan",
            "Oswald",
            "Bungee",
            "Fredoka One",
            "Alfa Slab One",
            "Archivo Black",
            "Impact",
            "Chalkboard",
        ]
        return pick_font("display", strong_display)

    def sans_font() -> str:
        return pick_font("sans")

    group_font = display_font()

    def shared_font() -> str:
        return group_font

    children: list[dict[str, Any]] = []
    if kind == "light_script":
        children.append(_layer_text(data["main"], {"fontFamily": script_font(), "fontSize": 64, "fontWeight": "normal", "fontStyle": "italic", "fill": "#FFFFFF", "stroke": "#FFD37A", "strokeWidth": 1.3, "shadowColor": "#FFD37A", "shadowBlur": 18, "shadowOffsetX": 0, "shadowOffsetY": 0, "letterSpacing": 0, "lineHeight": 0.82, "role": "main"}, z_base, margin, 154, full_w, 96))
    elif kind == "neon_glow":
        children.append(_layer_text(data["main"], {"fontFamily": script_font(), "fontSize": 54, "fontWeight": "normal", "fontStyle": "italic", "fill": "#FFFFFF", "stroke": "#9A8CFF", "strokeWidth": 1.4, "shadowColor": "#8179FF", "shadowBlur": 18, "shadowOffsetX": 0, "shadowOffsetY": 0, "letterSpacing": 0, "lineHeight": 0.86, "role": "main"}, z_base, margin, 154, full_w, 100))
    elif kind == "thank_you":
        if data.get("top"):
            children.append(_layer_text(data["top"], {"fontFamily": shared_font(), "fontSize": 46, "fontWeight": "bold", "fill": "#FF5056", "letterSpacing": 1.0, "rotation": -3, "lineHeight": 0.88, "role": "top"}, z_base, margin, 136, full_w, 50))
        if data.get("middle"):
            children.append(_layer_text(data["middle"], {"fontFamily": shared_font(), "fontSize": 34, "fontWeight": "bold", "fill": "#FF5056", "stroke": "#FFFFFF", "strokeWidth": 1.0, "lineHeight": 0.86, "role": "middle"}, z_base + 1, margin, 172, full_w, 36))
        main_y = 202 if data.get("middle") else 184 if data.get("top") else 170
        children.append(_layer_text(data["main"], {"fontFamily": shared_font(), "fontSize": 44, "fontWeight": "bold", "fill": "#FFFFFF", "stroke": "#FF5056", "strokeWidth": 2.0, "shadowColor": "#FF5056", "shadowBlur": 0, "shadowOffsetX": 1.2, "shadowOffsetY": 1.6, "letterSpacing": 0.6, "lineHeight": 0.88, "role": "main"}, z_base + 2, margin, main_y, full_w, 50))
    elif kind == "bride_groom":
        if data.get("script"):
            children.append(_layer_text(data["script"], {"fontFamily": script_font(), "fontSize": 58, "fontWeight": "normal", "fontStyle": "italic", "fill": "#16462D", "lineHeight": 0.85, "role": "script"}, z_base, margin, 128, full_w, 86))
        children.append(_layer_text(data["main"], {"fontFamily": serif_font(), "fontSize": 44, "fontWeight": "normal", "fill": "#16462D", "letterSpacing": 0.4, "lineHeight": 0.88, "role": "main"}, z_base + 1, margin, 200 if data.get("script") else 170, full_w, 80))
    elif kind == "happy_birthday":
        if data.get("script"):
            children.append(_layer_text(data["script"], {"fontFamily": script_font(), "fontSize": 42, "fontWeight": "bold", "fill": "#111111", "stroke": "#FFFFFF", "strokeWidth": 1.2, "rotation": -4, "lineHeight": 0.9, "role": "script"}, z_base, margin, 128, full_w, 66))
        children.append(_layer_text(data["main"], {"fontFamily": display_font(), "fontSize": 48, "fontWeight": "bold", "fill": "#050505", "letterSpacing": 0.2, "lineHeight": 0.9, "role": "main"}, z_base + 1, margin, 186 if data.get("script") else 162, full_w, 96))
    elif kind == "golden_hour":
        children.append(_layer_text(data["main"], {"fontFamily": serif_font(), "fontSize": 58, "fontWeight": "bold", "fill": "#D8A919", "shadowColor": "#BCA36B", "shadowBlur": 1.2, "shadowOffsetX": 2, "shadowOffsetY": 3, "letterSpacing": 0.2, "lineHeight": 0.83, "role": "main"}, z_base, margin, 136, full_w, 158))
    elif kind == "script_club":
        children.append(_layer_text(data["script"], {"fontFamily": script_font(), "fontSize": 50, "fontWeight": "normal", "fontStyle": "italic", "fill": "#5C84FF", "stroke": "#FFFFFF", "strokeWidth": 0.8, "rotation": -4, "lineHeight": 0.82, "role": "script"}, z_base, margin, 164, full_w, 70))
        if data.get("sub"):
            children.append(_layer_text(data["sub"], {"fontFamily": sans_font(), "fontSize": 10, "fontWeight": "bold", "fill": "#FFFFFF", "letterSpacing": 3.4, "role": "sub"}, z_base + 1, margin, 218, full_w, 24))
    elif kind == "xoxo":
        children.append(_layer_text(data["main"], {"fontFamily": display_font(), "fontSize": 50, "fontWeight": "bold", "fill": "#FFFFFF", "stroke": "#D94E78", "strokeWidth": 2.2, "shadowColor": "#F4A3B8", "shadowBlur": 0, "shadowOffsetX": 3, "shadowOffsetY": 3, "letterSpacing": 1.6, "role": "main"}, z_base, margin, 162, full_w, 90))
    elif kind == "studio_badge":
        children.append(_layer_text(data["main"], {"fontFamily": serif_font(), "fontSize": 38, "fontWeight": "normal", "fill": "#FFFFFF", "stroke": "#F6F6F6", "strokeWidth": 0.6, "letterSpacing": 0.4, "lineHeight": 0.9, "role": "main"}, z_base, margin, 132, full_w, 112))
        if data.get("badge"):
            children.append(_layer_text(data["badge"], {"fontFamily": sans_font(), "fontSize": 13, "fontWeight": "bold", "fill": "#FFFFFF", "stroke": "#D93C76", "strokeWidth": 3.5, "letterSpacing": 1.1, "role": "badge"}, z_base + 1, margin, 244, full_w, 32))
    elif kind == "streaming_now":
        if data.get("script"):
            children.append(_layer_text(data["script"], {"fontFamily": script_font(), "fontSize": 28, "fontWeight": "normal", "fill": "#2C8B6F", "lineHeight": 0.86, "role": "script"}, z_base, margin, 142, full_w, 42))
        children.append(_layer_text(data["main"], {"fontFamily": display_font(), "fontSize": 54, "fontWeight": "bold", "fill": "#F0B3E8", "stroke": "#2C8B6F", "strokeWidth": 1.4, "shadowColor": "#2C8B6F", "shadowBlur": 0, "shadowOffsetX": 0, "shadowOffsetY": 4, "letterSpacing": 0.4, "lineHeight": 0.82, "role": "main"}, z_base + 1, margin, 174, full_w, 82))
    elif kind == "quarterly_targets":
        if data.get("sub"):
            children.append(_layer_text(data["sub"], {"fontFamily": sans_font(), "fontSize": 21, "fontWeight": "bold", "fontStyle": "italic", "fill": "#8AA0A0", "letterSpacing": 1.8, "role": "sub"}, z_base, margin, 140, full_w, 38))
        children.append(_layer_text(data["main"], {"fontFamily": serif_font(), "fontSize": 50, "fontWeight": "bold", "fill": "#173F8A", "letterSpacing": -0.8, "lineHeight": 0.85, "role": "main"}, z_base + 1, margin, 174 if data.get("sub") else 166, full_w, 78))
    elif kind == "quarter_roadmap":
        if data.get("serif"):
            children.append(_layer_text(data["serif"], {"fontFamily": serif_font(), "fontSize": 26, "fontWeight": "normal", "fill": "#42A4FF", "letterSpacing": 1.4, "role": "serif"}, z_base, margin, 148, full_w, 44))
        children.append(_layer_text(data["main"], {"fontFamily": sans_font(), "fontSize": 31, "fontWeight": "normal", "fill": "#2D3552", "letterSpacing": 1.7, "role": "main"}, z_base + 1, margin, 186 if data.get("serif") else 172, full_w, 52))
    elif kind == "neon_open":
        children.append(_layer_text(data["main"], {"fontFamily": script_font(), "fontSize": 45, "fontWeight": "normal", "fill": "#FFFFFF", "stroke": "#8B7DFF", "strokeWidth": 1.4, "shadowColor": "#8179FF", "shadowBlur": 13, "lineHeight": 0.9, "role": "main"}, z_base, margin, 150, full_w, 110))
    elif kind == "editorial_caps":
        children.append(_layer_text(data["main"], {"fontFamily": serif_font(), "fontSize": 45, "fontWeight": "normal", "fontStyle": "italic", "fill": "#B64040", "letterSpacing": 0.6, "lineHeight": 0.86, "role": "main"}, z_base, margin, 142, full_w, 120))
    else:
        children.append(_layer_text(data.get("script", text), {"fontFamily": script_font(), "fontSize": 52, "fontWeight": "normal", "fontStyle": "italic", "fill": "#B64040", "lineHeight": 0.82, "role": "script"}, z_base, margin, 130, full_w, 82))
        children.append(_layer_text(data.get("main", text), {"fontFamily": serif_font(), "fontSize": 30, "fontWeight": "normal", "fill": "#B64040", "lineHeight": 0.9, "role": "main"}, z_base + 1, margin, 196, full_w, 76))

    children = _remove_duplicate_text_children(children)
    children = _use_single_font_family_per_group(children)
    children, palette_name, effect_name = _apply_modern_composition_design(
        children,
        kind,
        index,
        rng,
        randomize_designs,
        used_designs,
        used_palettes,
        used_effects,
    )
    children = _tighten_composition_children(children, canvas_height)
    children = _strengthen_transparent_text_contrast(children)
    children = _fit_composition_children_to_canvas(children, canvas_width, canvas_height)
    group = _composition_group(str(template.get("name") or kind), kind, children, index + 1, canvas_width, canvas_height)
    group["magicWritePalette"] = palette_name
    group["magicWriteEffect"] = effect_name
    group["magicWriteDesignSignature"] = _modern_composition_signature(children)
    return group


def _modern_composition_groups(
    text: str,
    count: int | None,
    rng: random.Random,
    canvas_width: int,
    canvas_height: int,
    randomize_designs: bool = True,
) -> list[dict[str, Any]]:
    templates = MODERN_COMPOSITION_TEMPLATES[:]
    template_order = {
        str(template.get("kind") or template.get("name") or ""): position
        for position, template in enumerate(MODERN_COMPOSITION_TEMPLATES)
    }
    normalized = text.lower()

    def score(template: dict[str, Any]) -> int:
        kind = str(template.get("kind") or "")
        checks = {
            "light_script": ("sparkle", "light", "glow", "shine", "neon"),
            "neon_glow": ("neon", "glow", "open", "light"),
            "thank_you": ("thank", "you"),
            "bride_groom": ("bride", "groom", "wedding", "&"),
            "happy_birthday": ("happy", "birthday"),
            "golden_hour": ("golden", "hour", "luxury"),
            "script_club": ("script", "club"),
            "xoxo": ("xoxo", "love"),
            "studio_badge": ("studio", "est", "agatho"),
            "streaming_now": ("streaming", "now", "live"),
            "quarterly_targets": ("quarterly", "targets", "target"),
            "quarter_roadmap": ("quarter", "roadmap", "road map"),
            "neon_open": ("open", "now"),
            "editorial_caps": ("coming", "soon"),
        }
        return sum(1 for token in checks.get(kind, ()) if token in normalized)

    templates.sort(key=lambda template: (-score(template), template_order.get(str(template.get("kind") or ""), 999)))
    requested = count or len(templates)
    groups = []
    used_fonts: set[str] = set()
    used_designs: set[tuple[str, str]] = set()
    used_palettes: set[str] = set()
    used_effects: set[str] = set()
    for index in range(requested):
        groups.append(_modern_composition_variant(
            text,
            templates[index % len(templates)],
            index,
            rng,
            canvas_width,
            canvas_height,
            used_fonts,
            used_designs,
            used_palettes,
            used_effects,
            randomize_designs,
        ))
    return groups


def _font_families_from_magic_write(objects: list[dict[str, Any]], primary_per_group: bool = False) -> list[str]:
    families: list[str] = []
    seen = set()
    for obj in objects:
        candidates = obj.get("children") if isinstance(obj.get("children"), list) else [obj]
        if primary_per_group and isinstance(candidates, list):
            primary = next(
                (
                    child
                    for child in candidates
                    if isinstance(child, dict) and str(child.get("magicWriteRole") or "") == "main"
                ),
                None,
            )
            candidates = [primary or next((child for child in candidates if isinstance(child, dict)), None)]
        for child in candidates:
            if not isinstance(child, dict):
                continue
            family = str(child.get("fontFamily") or "").strip()
            key = family.lower()
            if family and key not in seen:
                families.append(family)
                seen.add(key)
    return families


def _draw_text_with_spacing(
    layer: Image.Image,
    xy: tuple[float, float],
    text: str,
    font: ImageFont.ImageFont,
    fill: str,
    spacing: float,
    stroke: str,
    stroke_width: float,
) -> None:
    draw = ImageDraw.Draw(layer)
    x, y = xy
    for ch in text:
        draw.text(
            (x, y),
            ch,
            font=font,
            fill=fill,
            stroke_width=max(int(round(stroke_width)), 0),
            stroke_fill=stroke or fill,
        )
        x += draw.textlength(ch, font=font) + spacing


def _modern_line_width(text: str, font: ImageFont.ImageFont, spacing: float) -> float:
    draw = ImageDraw.Draw(Image.new("RGBA", (10, 10)))
    return _line_width(draw, text, font, spacing)


def _draw_centered_line(
    layer: Image.Image,
    text: str,
    y: float,
    font: ImageFont.ImageFont,
    fill: str,
    spacing: float = 0,
    stroke: str = "",
    stroke_width: float = 0,
    shadow: str = "",
    shadow_blur: float = 0,
    shadow_offset: tuple[float, float] = (0, 0),
) -> float:
    width, _ = layer.size
    line_w = _modern_line_width(text, font, spacing)
    x = (width - line_w) / 2
    if shadow:
        shadow_layer = Image.new("RGBA", layer.size, (0, 0, 0, 0))
        _draw_text_with_spacing(
            shadow_layer,
            (x + shadow_offset[0], y + shadow_offset[1]),
            text,
            font,
            shadow,
            spacing,
            shadow,
            stroke_width,
        )
        if shadow_blur:
            shadow_layer = shadow_layer.filter(ImageFilter.GaussianBlur(radius=shadow_blur))
        layer.alpha_composite(shadow_layer)
    _draw_text_with_spacing(layer, (x, y), text, font, fill, spacing, stroke, stroke_width)
    return line_w


def _fit_font_size_for_lines(
    lines: list[str],
    family: str,
    base_size: float,
    max_width: float,
    max_height: float,
    weight: str | None = None,
    italic: bool = False,
    spacing: float = 0,
    line_height: float = 1.0,
    min_size: float = 8,
) -> float:
    size = max(base_size, min_size)
    while size > min_size:
        font = _load_font(family, size, weight, italic)
        widths = [_modern_line_width(line, font, spacing) for line in lines]
        height = len(lines) * size * line_height
        if max(widths or [0]) <= max_width and height <= max_height:
            return size
        size *= 0.92
    return min_size


def _trim_transparent_preview(img: Image.Image, scale: int, padding: int = 10) -> Image.Image:
    rgba = img.convert("RGBA")
    alpha_bbox = rgba.getchannel("A").getbbox()
    if not alpha_bbox:
        return Image.new("RGBA", (1, 1), (0, 0, 0, 0))

    pad = max(int(padding * scale), 0)
    left = max(alpha_bbox[0] - pad, 0)
    top = max(alpha_bbox[1] - pad, 0)
    right = min(alpha_bbox[2] + pad, rgba.width)
    bottom = min(alpha_bbox[3] + pad, rgba.height)
    cropped = rgba.crop((left, top, right, bottom))

    target_width = max(1, int(round(cropped.width / max(scale, 1))))
    target_height = max(1, int(round(cropped.height / max(scale, 1))))
    return cropped.resize((target_width, target_height), Image.Resampling.LANCZOS)


def _draw_arc_text(
    layer: Image.Image,
    text: str,
    center: tuple[float, float],
    radius: float,
    font: ImageFont.ImageFont,
    fill: str,
    spacing_degrees: float = 8,
) -> None:
    if not text:
        return
    total_angle = min(max(len(text) * spacing_degrees, 80), 155)
    start_angle = -90 - total_angle / 2
    for index, char in enumerate(text):
        angle = math.radians(start_angle + index * (total_angle / max(len(text) - 1, 1)))
        x = center[0] + math.cos(angle) * radius
        y = center[1] + math.sin(angle) * radius
        draw = ImageDraw.Draw(layer)
        bbox = draw.textbbox((0, 0), char, font=font)
        char_w = bbox[2] - bbox[0]
        char_h = bbox[3] - bbox[1]
        draw.text((x - char_w / 2, y - char_h / 2), char, font=font, fill=fill)


def _render_modern_preview_data_uri(
    text_obj: dict[str, Any],
    canvas_width: int,
    canvas_height: int,
    scale: int,
) -> str:
    width = canvas_width * scale
    height = canvas_height * scale
    img = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    obj = deepcopy(text_obj)
    layout = str(obj.get("magicWriteLayout") or "stacked").lower()
    lines = [line for line in str(obj.get("text", "")).splitlines() if line.strip()]
    if not lines:
        lines = [str(obj.get("text", ""))]

    family = obj.get("fontFamily", "Arial")
    fill = obj.get("fill") or "#111111"
    stroke = obj.get("stroke") or ""
    accent = obj.get("accentFill") or fill
    shadow = obj.get("shadowColor") or ""
    stroke_width = float(obj.get("strokeWidth") or 0) * scale
    shadow_blur = float(obj.get("shadowBlur") or 0) * scale
    shadow_offset = (
        float(obj.get("shadowOffsetX") or 0) * scale,
        float(obj.get("shadowOffsetY") or 0) * scale,
    )
    spacing = float(obj.get("letterSpacing") or 0) * scale
    safe_w = width - 72 * scale
    safe_h = height - 72 * scale

    if layout == "sale":
        main = lines[0] if lines else "30%"
        second = lines[1] if len(lines) > 1 else "OFF"
        third = " ".join(lines[2:]) if len(lines) > 2 else ""
        base = min(float(obj.get("fontSize", 64)) * 2.1, 96) * scale
        main_size = _fit_font_size_for_lines([main], family, base, safe_w * 0.58, safe_h, obj.get("fontWeight"), False, -2 * scale, 0.8, 18 * scale)
        tall_font = _load_font(family, main_size, obj.get("fontWeight"), False)
        off_size = max(main_size * 0.32, 14 * scale)
        off_font = _load_font("Montserrat", off_size, "bold", False)
        small_font = _load_font("Montserrat", max(off_size * 0.44, 8 * scale), "bold", False)
        main_w = _modern_line_width(main, tall_font, -2 * scale)
        group_w = main_w + 14 * scale + max(_modern_line_width(second, off_font, 0), _modern_line_width(third, small_font, 0))
        x = (width - group_w) / 2
        y = (height - main_size * 1.05) / 2
        _draw_text_with_spacing(img, (x + 3 * scale, y + 4 * scale), main, tall_font, "#CFCFCF", -2 * scale, "", 0)
        _draw_text_with_spacing(img, (x, y), main, tall_font, fill, -2 * scale, "", 0)
        right_x = x + main_w + 14 * scale
        _draw_text_with_spacing(img, (right_x, y + main_size * 0.36), second, off_font, accent, 0, "", 0)
        if third:
            _draw_text_with_spacing(img, (right_x, y + main_size * 0.72), third, small_font, "#777777", 0, "", 0)
    elif layout == "title_heading":
        first = lines[0] if lines else "Title"
        second = lines[1] if len(lines) > 1 else "HEADING"
        title_size = _fit_font_size_for_lines([first], family, 58 * scale, safe_w, safe_h * 0.62, "bold", False, -0.4 * scale, 0.9, 14 * scale)
        heading_size = min(title_size * 0.5, 28 * scale)
        heading_size = _fit_font_size_for_lines([second.upper()], "Montserrat", heading_size, safe_w, safe_h * 0.34, "bold", True, 0.8 * scale, 0.9, 10 * scale)
        title_font = _load_font(family, title_size, "bold", False)
        heading_font = _load_font("Montserrat", heading_size, "bold", True)
        y = (height - (title_size + heading_size + 12 * scale)) / 2
        _draw_centered_line(img, first, y, title_font, fill, -0.4 * scale)
        _draw_centered_line(img, second.upper(), y + title_size + 12 * scale, heading_font, fill, 0.8 * scale)
    elif layout == "coming_soon":
        main_lines = lines[:2] if len(lines) > 1 else [lines[0]]
        sub = lines[2] if len(lines) > 2 else "Stay Tuned"
        main_size = _fit_font_size_for_lines([line.upper() for line in main_lines], family, float(obj.get("fontSize", 44)) * scale, safe_w, safe_h * 0.72, obj.get("fontWeight"), True, 0.2 * scale, 0.92, 12 * scale)
        sub_size = min(main_size * 0.6, 26 * scale)
        main_font = _load_font(family, main_size, obj.get("fontWeight"), True)
        sub_font = _load_font("Great Vibes", sub_size, "normal", False)
        total_h = len(main_lines) * main_size * 0.92 + sub_size + 16 * scale
        y = (height - total_h) / 2
        for line in main_lines:
            _draw_centered_line(img, line.upper(), y, main_font, fill, 0.2 * scale)
            y += main_size * 0.92
        _draw_centered_line(img, sub, y + 8 * scale, sub_font, fill, 0)
    elif layout in {"signature", "glow_signature"}:
        fitted = _fit_font_size_for_lines(lines, family, float(obj.get("fontSize", 48)) * scale, safe_w, safe_h, obj.get("fontWeight"), False, spacing, 0.78, 10 * scale)
        font = _load_font(family, fitted, obj.get("fontWeight"), False)
        total_h = len(lines) * fitted * 0.78
        y = (height - total_h) / 2
        for line in lines:
            _draw_centered_line(
                img,
                line,
                y,
                font,
                fill,
                spacing,
                stroke,
                stroke_width,
                shadow,
                shadow_blur,
                shadow_offset,
            )
            y += fitted * 0.78
    elif layout == "arc":
        arc_line = lines[0].upper()
        sub = lines[1] if len(lines) > 1 else ""
        arc_size = _fit_font_size_for_lines([arc_line], family, 42 * scale, safe_w, safe_h * 0.5, obj.get("fontWeight"), False, 0, 1.0, 12 * scale)
        arc_font = _load_font(family, arc_size, obj.get("fontWeight"), False)
        sub_font = _load_font("Great Vibes", min(arc_size * 0.55, 22 * scale), "normal", False)
        _draw_arc_text(img, arc_line, (width / 2, height * 0.6), min(90 * scale, safe_w * 0.28), arc_font, fill)
        if sub:
            _draw_centered_line(img, sub, height * 0.55, sub_font, fill, 0)
    else:
        italic = str(obj.get("fontStyle") or "") == "italic"
        fitted = _fit_font_size_for_lines(lines, family, float(obj.get("fontSize", 40)) * scale, safe_w, safe_h, obj.get("fontWeight"), italic, spacing, float(obj.get("lineHeight") or 1), 10 * scale)
        font = _load_font(family, fitted, obj.get("fontWeight"), italic)
        total_h = len(lines) * fitted * float(obj.get("lineHeight") or 1)
        y = (height - total_h) / 2
        for line in lines:
            _draw_centered_line(img, line, y, font, fill, spacing, stroke, stroke_width, shadow, shadow_blur, shadow_offset)
            y += fitted * float(obj.get("lineHeight") or 1)

    img = _trim_transparent_preview(img, scale)
    out = io.BytesIO()
    img.save(out, format="PNG")
    return "data:image/png;base64," + base64.b64encode(out.getvalue()).decode("ascii")


def _draw_text_object_on_layer(img: Image.Image, obj: dict[str, Any], scale: int) -> None:
    lines = str(obj.get("text", "")).splitlines() or [str(obj.get("text", ""))]
    letter_spacing = float(obj.get("letterSpacing") or 0) * scale
    box_x = float(obj.get("x", 0)) * scale
    box_y = float(obj.get("y", 0)) * scale
    box_w = float(obj.get("width", img.size[0] / scale)) * scale
    box_h = float(obj.get("height", img.size[1] / scale)) * scale
    fill = obj.get("fill") or "#111111"
    stroke = obj.get("stroke") or ""
    stroke_width = float(obj.get("strokeWidth") or 0) * scale
    shadow = obj.get("shadowColor") or ""
    align = obj.get("align") or obj.get("textAlign") or "center"
    italic = str(obj.get("fontStyle") or "").lower() == "italic"
    font_size = float(obj.get("fontSize", 36)) * scale
    fitted_size = _fit_font_size_for_lines(
        lines,
        obj.get("fontFamily", "Arial"),
        font_size,
        max(box_w, 1),
        max(box_h, 1),
        obj.get("fontWeight"),
        italic,
        letter_spacing,
        float(obj.get("lineHeight") or 1.0),
        7 * scale,
    )
    font = _load_font(obj.get("fontFamily", "Arial"), fitted_size, obj.get("fontWeight"), italic)
    draw = ImageDraw.Draw(img)
    line_height = float(obj.get("lineHeight") or 1.0) * fitted_size
    content_h = len(lines) * line_height
    y = box_y + max((box_h - content_h) / 2, 0)
    positions: list[tuple[str, float, float, float]] = []
    for line in lines:
        line_w = _line_width(draw, line, font, letter_spacing)
        if align == "left":
            x = box_x
        elif align == "right":
            x = box_x + box_w - line_w
        else:
            x = box_x + (box_w - line_w) / 2
        positions.append((line, x, y, line_w))
        y += line_height

    target = img
    rotation = float(obj.get("rotation") or 0)
    if abs(rotation) > 0.01:
        target = Image.new("RGBA", img.size, (0, 0, 0, 0))

    if shadow:
        shadow_layer = Image.new("RGBA", img.size, (0, 0, 0, 0))
        for line, x, y, _ in positions:
            _draw_text_with_spacing(
                shadow_layer,
                (x + float(obj.get("shadowOffsetX") or 0) * scale, y + float(obj.get("shadowOffsetY") or 0) * scale),
                line,
                font,
                shadow,
                letter_spacing,
                shadow,
                stroke_width,
            )
        blur = float(obj.get("shadowBlur") or 0) * scale
        if blur:
            shadow_layer = shadow_layer.filter(ImageFilter.GaussianBlur(radius=blur))
        target.alpha_composite(shadow_layer)

    text_layer = Image.new("RGBA", img.size, (0, 0, 0, 0))
    for line, x, y, _ in positions:
        _draw_text_with_spacing(text_layer, (x, y), line, font, fill, letter_spacing, stroke, stroke_width)
    target.alpha_composite(text_layer)

    decoration = str(obj.get("textDecoration") or "").lower()
    if decoration in {"underline", "line-through"}:
        draw = ImageDraw.Draw(target)
        for _, x, y, line_w in positions:
            offset = fitted_size * (0.82 if decoration == "underline" else 0.48)
            line_y = y + offset
            draw.line((x, line_y, x + line_w, line_y), fill=fill, width=max(1, int(fitted_size * 0.05)))

    if target is not img:
        target = target.rotate(rotation, resample=Image.Resampling.BICUBIC, expand=False)
        img.alpha_composite(target)


def _render_group_preview_data_uri(
    group_obj: dict[str, Any],
    canvas_width: int,
    canvas_height: int,
    scale: int,
) -> str:
    width = canvas_width * scale
    height = canvas_height * scale
    img = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    children = [child for child in group_obj.get("children", []) if isinstance(child, dict)]
    children.sort(key=lambda child: int(child.get("zIndex") or 0))
    for child in children:
        if child.get("type") == "Text":
            _draw_text_object_on_layer(img, child, scale)
    img = _trim_transparent_preview(img, scale)
    out = io.BytesIO()
    img.save(out, format="PNG")
    return "data:image/png;base64," + base64.b64encode(out.getvalue()).decode("ascii")


def render_preview_data_uri(text_obj: dict[str, Any], canvas_width: int = DEFAULT_CANVAS_WIDTH,
                            canvas_height: int = DEFAULT_CANVAS_HEIGHT,
                            scale: int = DEFAULT_PREVIEW_SCALE) -> str:
    if text_obj.get("type") == "Group" or text_obj.get("children"):
        return _render_group_preview_data_uri(text_obj, canvas_width, canvas_height, scale)
    layout = str(text_obj.get("magicWriteLayout") or "stacked").lower()
    if layout in {"sale", "title_heading", "coming_soon", "signature", "glow_signature", "arc"}:
        return _render_modern_preview_data_uri(text_obj, canvas_width, canvas_height, scale)

    width = canvas_width * scale
    height = canvas_height * scale
    img = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    obj = deepcopy(text_obj)
    font_size = float(obj.get("fontSize", 36)) * scale
    lines = str(obj.get("text", "")).splitlines() or [str(obj.get("text", ""))]
    letter_spacing = float(obj.get("letterSpacing") or 0) * scale
    draw = ImageDraw.Draw(img)

    box_x = float(obj.get("x", 0)) * scale
    box_y = float(obj.get("y", 0)) * scale
    box_w = float(obj.get("width", canvas_width)) * scale
    box_h = float(obj.get("height", canvas_height)) * scale
    safe_box_w = max(min(box_w, width - 72 * scale), 1)
    fill = obj.get("fill") or "#111111"
    stroke = obj.get("stroke") or ""
    stroke_width = float(obj.get("strokeWidth") or 0) * scale
    shadow = obj.get("shadowColor") or ""
    align = obj.get("align") or obj.get("textAlign") or "center"
    italic = str(obj.get("fontStyle") or "").lower() == "italic"
    fitted_size = _fit_font_size_for_lines(
        lines,
        obj.get("fontFamily", "Arial"),
        font_size,
        safe_box_w,
        max(box_h, 1),
        obj.get("fontWeight"),
        italic,
        letter_spacing,
        float(obj.get("lineHeight") or 1.0),
        8 * scale,
    )
    font = _load_font(obj.get("fontFamily", "Arial"), fitted_size, obj.get("fontWeight"), italic)
    line_height = float(obj.get("lineHeight") or 1.0) * fitted_size

    content_h = len(lines) * line_height
    y = box_y + max((box_h - content_h) / 2, 0)
    text_positions: list[tuple[str, float, float, float]] = []
    for line in lines:
        line_w = _line_width(draw, line, font, letter_spacing)
        if align == "left":
            x = box_x
        elif align == "right":
            x = box_x + box_w - line_w
        else:
            x = box_x + (box_w - line_w) / 2
        text_positions.append((line, x, y, line_w))
        y += line_height

    if shadow:
        shadow_layer = Image.new("RGBA", img.size, (0, 0, 0, 0))
        for line, x, y, _ in text_positions:
            _draw_text_with_spacing(
                shadow_layer,
                (x + float(obj.get("shadowOffsetX") or 0) * scale, y + float(obj.get("shadowOffsetY") or 0) * scale),
                line,
                font,
                shadow,
                letter_spacing,
                shadow,
                stroke_width,
            )
        blur = float(obj.get("shadowBlur") or 0) * scale
        if blur:
            shadow_layer = shadow_layer.filter(ImageFilter.GaussianBlur(radius=blur))
        img.alpha_composite(shadow_layer)

    text_layer = Image.new("RGBA", img.size, (0, 0, 0, 0))
    for line, x, y, _ in text_positions:
        _draw_text_with_spacing(text_layer, (x, y), line, font, fill, letter_spacing, stroke, stroke_width)
    img.alpha_composite(text_layer)

    decoration = str(obj.get("textDecoration") or "").lower()
    if decoration in {"underline", "line-through"}:
        draw = ImageDraw.Draw(img)
        for _, x, y, line_w in text_positions:
            offset = font_size * (0.82 if decoration == "underline" else 0.48)
            line_y = y + offset
            draw.line((x, line_y, x + line_w, line_y), fill=fill, width=max(1, int(font_size * 0.05)))

    rotation = float(obj.get("rotation") or 0)
    if abs(rotation) > 0.01:
        img = img.rotate(rotation, resample=Image.Resampling.BICUBIC, expand=False, fillcolor=(0, 0, 0, 0))

    img = _trim_transparent_preview(img, scale)
    out = io.BytesIO()
    img.save(out, format="PNG")
    return "data:image/png;base64," + base64.b64encode(out.getvalue()).decode("ascii")


def generate_magic_write(
    text: str,
    count: int | None = 6,
    mood: str | None = None,
    model: str | None = LOCAL_MAGIC_WRITE_MODEL,
    timeout: int = 45,
    canvas_width: int = DEFAULT_CANVAS_WIDTH,
    canvas_height: int = DEFAULT_CANVAS_HEIGHT,
    modern: bool = False,
    all_fonts: bool = False,
    all_google_fonts: bool = False,
    font_families: list[str] | tuple[str, ...] | str | None = None,
    google_fonts_api_key: str | None = None,
    google_font_sort: str = "alpha",
    google_font_category: str | None = None,
    refresh_google_fonts: bool = False,
    randomize_fonts: bool = True,
    randomize_designs: bool = True,
    seed: int | None = None,
) -> dict[str, Any]:
    text = str(text or "").strip()
    if not text:
        raise ValueError("text is required")
    requested_count = int(_clamp_number(count, 1, 0, 10000)) if count is not None else None
    canvas_width = int(_clamp_number(canvas_width, DEFAULT_CANVAS_WIDTH, 160, 2000))
    canvas_height = int(_clamp_number(canvas_height, DEFAULT_CANVAS_HEIGHT, 160, 2000))
    model_name = LOCAL_MAGIC_WRITE_MODEL
    rng = _make_rng(seed)

    if requested_count == 0:
        return {
            "magic_write": [],
            "preview_image": [],
            "meta": {
                "model": model_name,
                "canvas_width": canvas_width,
                "canvas_height": canvas_height,
                "count": 0,
                "mode": "modern_composition" if modern else "all_google_fonts" if all_google_fonts else "all_fonts" if all_fonts or font_families else "style_presets",
                "font_families": [],
                "child_font_families": [] if modern else None,
                "randomize_fonts": randomize_fonts,
                "randomize_designs": randomize_designs,
                "seed": seed,
                "google_font_sort": google_font_sort if all_google_fonts else None,
                "google_font_category": google_font_category if all_google_fonts else None,
            },
        }

    if modern:
        objects = _modern_composition_groups(
            text,
            requested_count,
            rng=rng,
            canvas_width=canvas_width,
            canvas_height=canvas_height,
            randomize_designs=randomize_designs,
        )
    elif all_google_fonts:
        google_families = fetch_google_font_families(
            api_key=google_fonts_api_key,
            sort=google_font_sort,
            category=google_font_category,
            refresh=refresh_google_fonts,
        )
        styles = _styles_for_font_families(
            google_families,
            count=requested_count,
            randomize_fonts=randomize_fonts,
            randomize_designs=randomize_designs,
            rng=rng,
        )
    elif all_fonts or font_families:
        styles = _styles_for_font_families(
            font_families,
            count=requested_count,
            randomize_fonts=randomize_fonts,
            randomize_designs=randomize_designs,
            rng=rng,
        )
    else:
        styles = _style_candidates(
            text,
            count=requested_count or 6,
            mood=mood,
            randomize_fonts=randomize_fonts,
            randomize_designs=randomize_designs,
            rng=rng,
        )
    if not modern:
        objects = [_konva_text(text, style, z_index=index + 1, canvas_width=canvas_width, canvas_height=canvas_height)
                   for index, style in enumerate(styles)]
    previews = [
        {
            "image": render_preview_data_uri(obj, canvas_width=canvas_width, canvas_height=canvas_height),
        }
        for obj in objects
    ]
    return {
        "magic_write": objects,
        "preview_image": previews,
        "meta": {
            "model": model_name,
            "canvas_width": canvas_width,
            "canvas_height": canvas_height,
            "count": len(objects),
            "mode": "modern_composition" if modern else "all_google_fonts" if all_google_fonts else "all_fonts" if all_fonts or font_families else "style_presets",
            "font_families": _font_families_from_magic_write(objects, primary_per_group=modern),
            "child_font_families": _font_families_from_magic_write(objects) if modern else None,
            "randomize_fonts": randomize_fonts,
            "randomize_designs": randomize_designs,
            "seed": seed,
            "google_font_sort": google_font_sort if all_google_fonts else None,
            "google_font_category": google_font_category if all_google_fonts else None,
        },
    }


def save_preview_images(result: dict[str, Any], output_dir: str | Path) -> list[Path]:
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    for index, preview in enumerate(result.get("preview_image") or [], start=1):
        uri = preview.get("image", "")
        if not isinstance(uri, str) or "," not in uri:
            continue
        raw = base64.b64decode(uri.split(",", 1)[1])
        path = output / f"magic_write_{index}.png"
        path.write_bytes(raw)
        written.append(path)
    return written
