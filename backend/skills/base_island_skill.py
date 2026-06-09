# skills/base_island_skill.py
"""
BaseIslandSkill — extend this to add a persistent strip/panel to the
Dynamic Island without touching any frontend code.

How it works
------------
1. Drop a *_skill.py in backend/skills/ that subclasses BaseIslandSkill.
2. The FeedManager polls get_island_data() every `refresh_seconds` and pushes
   the result over WebSocket as {"type": "island_skill", "skill": "<name>", "data": {...}}.
3. The frontend DynamicIsland renders the data using the generic strip renderer.

Data shape returned by get_island_data()
-----------------------------------------
{
  # Required
  "label":    str,   # tiny uppercase label  e.g. "📅 Next Class"
  "title":    str,   # main text             e.g. "Data Structures"

  # Optional
  "subtitle": str,   # secondary text        e.g. "Room 204 · in 34m"
  "progress": float, # 0.0–1.0 bar          e.g. 0.6
  "badge":    str,   # right-side badge text e.g. "34m"
  "urgent":   bool,  # amber/red highlight
  "color":    str,   # hex accent            e.g. "#4285f4"

  # Expanded panel payload (shown on hover / tap)
  "panel": {
    "items": [{"label": str, "value": str, "color": str}, ...]
  }
}
Return None to hide the strip entirely.
"""

from abc import abstractmethod
from skills.base_skill import BaseSkill, SkillContext, SkillResult


class BaseIslandSkill(BaseSkill):
    # ── Island config ──────────────────────────────────────────────────────────
    island_name: str = ""          # unique key used in WebSocket payload
    refresh_seconds: int = 60      # how often FeedManager calls get_island_data()

    # ── Subclass API ───────────────────────────────────────────────────────────

    @abstractmethod
    def get_island_data(self) -> dict | None:
        """
        Return a dict (see module docstring for shape) or None to hide strip.
        Called from a background thread — keep it fast, cache heavy I/O.
        """
        raise NotImplementedError

    # ── BaseSkill wiring ───────────────────────────────────────────────────────

    def execute(self, ctx: SkillContext) -> SkillResult:
        """Chat-triggered execution: run get_island_data and return it as text."""
        data = self.get_island_data()
        if not data:
            return SkillResult(success=True, output_text="No data available right now.")
        lines = [f"**{data.get('label', '')}** {data.get('title', '')}"]
        if data.get("subtitle"):
            lines.append(data["subtitle"])
        if data.get("panel"):
            for item in data["panel"].get("items", []):
                lines.append(f"• {item.get('label')}: {item.get('value')}")
        return SkillResult(success=True, output_text="\n".join(lines), extras={"island_data": data})
