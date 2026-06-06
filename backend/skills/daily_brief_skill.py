# backend/skills/daily_brief_skill.py
import datetime
from pathlib import Path
from skills.base_skill import BaseSkill, SkillContext, SkillResult
from logger import get_logger

log = get_logger("skill.daily_brief")

MEETINGS_DIR = Path.home() / "Documents" / "Primnox" / "Meetings"


def _todays_meeting_summaries() -> list[dict]:
    """Return summary text for each meeting recorded today."""
    if not MEETINGS_DIR.exists():
        return []
    today = datetime.date.today().strftime("%Y%m%d")
    results = []
    try:
        entries = sorted(MEETINGS_DIR.iterdir(), reverse=True)
    except OSError as e:
        log.warning(f"Could not read meetings directory: {e}")
        return []
    for d in entries:
        try:
            if not d.is_dir():
                continue
            # Meeting dirs are named Meeting_YYYYMMDD_HHMMSS
            if today not in d.name:
                continue
            summary_file = d / "summary.txt"
            if summary_file.exists():
                results.append({
                    "name": d.name,
                    "summary": summary_file.read_text(encoding="utf-8").strip()
                })
        except Exception as e:
            log.warning(f"Skipping meeting dir {d.name}: {e}")
    return results


class DailyBriefSkill(BaseSkill):
    name = "Daily Brief"
    description = (
        "Generate a concise summary of today's activity: meetings recorded, "
        "notes taken, and any context passed via feed history."
    )
    supported_extensions = []
    trigger_words = [
        "daily brief", "summarize my day", "what happened today",
        "daily debrief", "day summary", "brief me", "what did i do today"
    ]
    REQUIRES_PIP = []

    def execute(self, ctx: SkillContext) -> SkillResult:
        from brain import think

        log.info("Daily Brief skill triggered")

        today = datetime.date.today().strftime("%A, %B %d %Y")
        sections: list[str] = [f"# Daily Brief — {today}\n"]

        # 1. Meetings
        meetings = _todays_meeting_summaries()
        if meetings:
            sections.append(f"## Meetings ({len(meetings)} recorded)")
            for m in meetings:
                sections.append(f"**{m['name']}**\n{m['summary'][:400]}")
        else:
            sections.append("## Meetings\nNo meetings recorded today.")

        # 2. Notes (from metadata if passed in)
        notes_count = ctx.metadata.get("notes_count", 0)
        if notes_count:
            sections.append(f"## Notes\n{notes_count} notes in your workspace.")

        # 3. Ambient feed history (passed in via metadata from server)
        feed_history = ctx.metadata.get("feed_history", [])
        ambient = [e for e in feed_history if "Ambient:" in e]
        window_events = [e for e in feed_history if "Ambient:" not in e]

        if ambient:
            ambient_text = "\n".join(ambient[-30:])  # last 30 ambient events
            sections.append(f"## What You Said (recent)\n```\n{ambient_text}\n```")

        if window_events:
            apps = list(dict.fromkeys(
                e.split(": ", 1)[1].split(" — ")[0] if ": " in e else e
                for e in window_events[-20:]
            ))
            sections.append(f"## Apps You Used\n" + ", ".join(apps[:8]))

        # Build prompt for brain to synthesize into a proper brief
        raw = "\n\n".join(sections)
        resp = think(
            "Synthesize the following raw daily activity log into a clean, professional "
            "daily brief. Use markdown with clear headings. Be concise — no fluff. "
            "End with 'key takeaway' in 1 sentence.\n\n" + raw
        )
        content = resp.get("choices", [{}])[0].get("message", {}).get("content", "")

        if not content:
            # Fallback: return the raw brief if brain fails
            content = raw

        return SkillResult(
            success=True,
            output_text=content,
            extras={
                "meetings_count": len(meetings),
                "ambient_count": len(ambient),
                "date": today
            }
        )


if __name__ == "__main__":
    skill = DailyBriefSkill()
    print(skill.run(SkillContext()))
