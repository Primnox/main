"""JSON schema and routing for the design system.

The model fills in a structured JSON. No design decisions—just routing.
"""
from dataclasses import dataclass, field
from typing import Literal


@dataclass
class LayoutRequest:
    """What the model hands back. Zero creativity required; pure routing."""

    # Slide classification
    slide_type: Literal[
        "hero",           # Full-bleed opening slide
        "hero_left",      # Hero image on left, content on right
        "hero_right",     # Hero image on right, content on left
        "content",        # Title + bullets (default)
        "two_column",     # Split content
        "kpi",            # Key metrics (cards)
        "chart",          # Chart + caption
        "comparison",     # Before/After
        "process",        # Numbered steps
        "timeline",       # Timeline of events
        "end",            # Closing slide
    ]

    # Content density: informs whitespace and text sizing
    density: Literal["light", "medium", "heavy"] = "medium"

    # Title and body content
    title: str = ""
    subtitle: str = ""
    bullets: list[str] = field(default_factory=list)  # For content/two_column
    left_column: list[str] = field(default_factory=list)  # For two_column
    right_column: list[str] = field(default_factory=list)  # For two_column
    items: list[str] = field(default_factory=list)  # For process/timeline
    metrics: list[dict] = field(default_factory=list)  # For kpi: [{"label": "...", "value": "..."}]
    chart_type: Literal["bar", "line", "pie", "area"] = "bar"
    chart_data: dict = field(default_factory=dict)  # {"series": [1, 2, 3], ...}

    # Visual hints
    asset_type: Literal[
        "none",
        "photo",
        "illustration",
        "diagram",
        "icon",
        "chart",
        "logo",
    ] = "none"
    asset_url: str = ""  # Placeholder; real assets come from search

    # Theme/style (but still routed, not invented)
    theme: Literal[
        "light",
        "dark",
        "brand",
    ] = "light"
    accent_color: str = ""  # Optional override, but tokens are the default

    # Speaker notes or caption
    notes: str = ""

    def validate(self) -> list[str]:
        """Check for missing required fields. Return list of errors."""
        errors = []
        if not self.title:
            errors.append("title is required")
        if self.slide_type in ("content",) and not self.bullets:
            errors.append(f"bullets required for {self.slide_type}")
        if self.slide_type == "two_column" and not (self.left_column and self.right_column):
            errors.append("left_column and right_column required for two_column")
        if self.slide_type == "kpi" and not self.metrics:
            errors.append("metrics required for kpi")
        if self.slide_type == "chart" and not self.chart_data:
            errors.append("chart_data required for chart")
        if self.slide_type == "process" and not self.items:
            errors.append("items required for process")
        if self.slide_type == "timeline" and not self.items:
            errors.append("items required for timeline")
        return errors


# Design tokens: locked values a small model never chooses
class DesignTokens:
    """No magic. Every value is decided."""

    # Spacing (8-point grid)
    GRID = 8
    MARGIN_X = 64
    MARGIN_TOP = 56
    MARGIN_BOTTOM = 48
    GAP_LARGE = 32
    GAP_MEDIUM = 24
    GAP_SMALL = 16

    # Typography (consistent scale)
    TITLE_SIZE = 44
    SUBTITLE_SIZE = 28
    BODY_SIZE = 20
    CAPTION_SIZE = 14
    LABEL_SIZE = 12

    LINE_HEIGHT_TIGHT = 1.2
    LINE_HEIGHT_NORMAL = 1.5
    LINE_HEIGHT_LOOSE = 1.8

    FONT_DISPLAY = "Bahnschrift SemiBold"  # For headlines
    FONT_BODY = "Segoe UI"                 # For body copy
    FONT_MONO = "Consolas"                 # For code

    # Colors (light theme as default)
    COLOR_BG = "F6F4EF"        # paper light
    COLOR_TEXT = "100F0E"
    COLOR_MUTED = "6B6862"
    COLOR_PRIMARY = "4B3FBF"
    COLOR_ACCENT = "B8501F"

    # Shadows (three tokens)
    SHADOW_SOFT = "0 1px 2px rgba(0,0,0,0.05)"
    SHADOW_MEDIUM = "0 4px 6px rgba(0,0,0,0.1)"
    SHADOW_STRONG = "0 10px 15px rgba(0,0,0,0.2)"

    # Radius (consistent rounding)
    RADIUS_BUTTON = 8
    RADIUS_CARD = 16
    RADIUS_IMAGE = 24
    RADIUS_HERO = 32

    @classmethod
    def for_theme(cls, theme: str) -> dict:
        """Return color tokens for a theme. Everything else is locked."""
        themes = {
            "light": {
                "bg": "F6F4EF",
                "text": "100F0E",
                "muted": "6B6862",
                "primary": "4B3FBF",
                "accent": "B8501F",
            },
            "dark": {
                "bg": "060A1A",
                "text": "E7EAF7",
                "muted": "878CA1",
                "primary": "6EA8FF",
                "accent": "FF7AB8",
            },
            "brand": {
                "bg": "FFFFFF",
                "text": "0F0F0F",
                "muted": "7C7C7C",
                "primary": "2563EB",
                "accent": "DC2626",
            },
        }
        return themes.get(theme, themes["light"])
