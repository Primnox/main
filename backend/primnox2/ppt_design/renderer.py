"""Render a LayoutRequest to PPTX using the design tokens.

Uses primnox_docs.Deck as the foundation but routes through the schema
to ensure small models always produce valid, styled output.
"""
from pathlib import Path
from typing import Optional

from .schema import DesignTokens, LayoutRequest


class DesignRenderer:
    """Convert a routed layout request to a real PPTX file.

    Phase 1: Use Deck methods directly, respecting design tokens.
    Phase 2: Add layout templates, component library, and Critic.
    """

    def __init__(self, output_path: str, theme: str = "light"):
        self.output_path = Path(output_path)
        self.theme = theme
        self.tokens = DesignTokens.for_theme(theme)
        # Import here to avoid circular imports and to keep it sandbox-safe
        try:
            from ..sandbox.doc_themes import Deck
            self.Deck = Deck
        except ImportError:
            self.Deck = None

    def render(self, request: LayoutRequest) -> str:
        """Convert a layout request to a PPTX file. Return the path."""
        errors = request.validate()
        if errors:
            raise ValueError(f"Invalid request: {'; '.join(errors)}")

        if self.Deck is None:
            raise RuntimeError("primnox_docs.Deck not available in this environment")

        # Build the deck using Deck methods, but routed by the schema
        d = self.Deck(
            str(self.output_path),
            theme=self.theme,
            title=request.title,
            subtitle=request.subtitle,
        )

        # Route based on slide_type
        if request.slide_type == "hero":
            d.hero(request.title, request.subtitle)
        elif request.slide_type == "hero_left":
            # For now, use two_column as a proxy
            d.two_column(
                request.title,
                left=[request.subtitle or request.notes],
                right=[],
            )
        elif request.slide_type == "content":
            d.bullets(request.title, request.bullets or [])
        elif request.slide_type == "two_column":
            d.two_column(
                request.title,
                left=request.left_column,
                right=request.right_column,
            )
        elif request.slide_type == "kpi":
            metrics = [
                (m.get("label"), m.get("value"), m.get("delta", ""))
                for m in request.metrics
            ]
            d.kpi(request.title, metrics)
        elif request.slide_type == "chart":
            # Simplified: just the chart
            categories = request.chart_data.get("categories", ["A", "B", "C"])
            series = request.chart_data.get("series", {"Data": [1, 2, 3]})
            d.chart(request.title, categories, series, kind=request.chart_type)
        elif request.slide_type == "process":
            d.process(request.title, request.items or [])
        elif request.slide_type == "timeline":
            # Timeline expects (date, event) tuples
            events = [(item, "") for item in request.items]
            d.timeline(request.title, events)
        elif request.slide_type == "comparison":
            d.compare(
                request.title,
                "Before",
                request.left_column or [],
                "After",
                request.right_column or [],
            )
        elif request.slide_type == "end":
            d.hero(request.title, request.subtitle)
        else:
            # Default to content
            d.bullets(request.title, request.bullets or [])

        return d.save()


def render_layout_json(
    json_spec: dict, output_path: str, theme: str = "light"
) -> tuple[bool, str]:
    """Parse JSON, render to PPTX, return (success, message).

    This is what the skill calls. If it fails, return the error message
    so the model knows what went wrong.
    """
    try:
        request = LayoutRequest(**json_spec)
        renderer = DesignRenderer(output_path, theme=theme)
        path = renderer.render(request)
        return True, f"Created {Path(path).name}"
    except ValueError as e:
        return False, f"Invalid layout: {e}"
    except Exception as e:
        return False, f"Render error: {e}"
