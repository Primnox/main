# backend/skills/meeting_summary_skill.py
from pathlib import Path
from skills.base_skill import BaseSkill, SkillContext, SkillResult
from logger import get_logger

log = get_logger("skill.meeting")

MEETINGS_DIR = Path.home() / "Documents" / "Primnox" / "Meetings"


def _save_to_notes(meeting_name: str, summary: str):
    """Save or update the meeting summary as a note. Skips if an identical note already exists."""
    try:
        from notes_manager import add_note, get_notes
        title = f"Meeting: {meeting_name}"
        existing = [n for n in get_notes() if n.get("title") == title]
        if not existing:
            add_note(text=summary, title=title)
            log.info(f"Saved meeting summary to notes: {title}")
    except Exception as e:
        log.warning(f"Could not save meeting summary to notes: {e}")


def _get_latest_meeting_dir() -> Path | None:
    if not MEETINGS_DIR.exists():
        return None
    try:
        dirs = sorted([d for d in MEETINGS_DIR.iterdir() if d.is_dir()], reverse=True)
    except PermissionError as e:
        log.warning(f"Cannot read meetings directory: {e}")
        return None
    return dirs[0] if dirs else None


class MeetingSummarySkill(BaseSkill):
    name = "Meeting Summary"
    description = (
        "Retrieve or generate a summary of the most recent recorded meeting. "
        "Reads the saved summary file if it exists, otherwise generates one from context."
    )
    supported_extensions = []
    trigger_words = [
        "last meeting", "meeting summary", "what was my meeting about",
        "summarize meeting", "what happened in my meeting", "recap meeting"
    ]
    REQUIRES_PIP = []

    def execute(self, ctx: SkillContext) -> SkillResult:
        from brain import think

        log.info("Meeting Summary skill triggered")
        meeting_dir = _get_latest_meeting_dir()

        if not meeting_dir:
            return SkillResult(
                success=False,
                error="no meetings recorded yet. meetings are auto-detected when Zoom, Teams, Slack, or Meet is active."
            )

        summary_file = meeting_dir / "summary.txt"

        # If we already have a saved summary, return it
        if summary_file.exists():
            try:
                summary = summary_file.read_text(encoding="utf-8").strip()
                if summary:
                    log.info(f"Returning cached summary for {meeting_dir.name}")
                    _save_to_notes(meeting_dir.name, summary)
                    return SkillResult(
                        success=True,
                        output_text=f"**{meeting_dir.name}**\n\n{summary}",
                        extras={"meeting_dir": str(meeting_dir), "source": "cached"}
                    )
            except Exception as e:
                log.warning(f"Couldn't read cached summary: {e}")

        # No summary — try to generate from any available context
        log.info(f"No cached summary for {meeting_dir.name} — generating...")
        context_parts = []

        # Collect any screenshots as context hints (just file names/count)
        screenshots = list(meeting_dir.glob("*.png"))
        if screenshots:
            context_parts.append(f"{len(screenshots)} screenshots captured during the meeting.")

        # Prefer the real transcript: use transcript.txt if the recorder wrote
        # one, otherwise transcribe meeting_audio.wav now via the shared impl.
        transcript = ""
        transcript_file = meeting_dir / "transcript.txt"
        if transcript_file.exists():
            try:
                transcript = transcript_file.read_text(encoding="utf-8").strip()
            except Exception as e:
                log.warning(f"Couldn't read transcript: {e}")
        audio_file = meeting_dir / "meeting_audio.wav"
        if not transcript and audio_file.exists():
            try:
                from meeting_recorder import transcribe_meeting_audio
                transcript = transcribe_meeting_audio(audio_file)
                if transcript:
                    try:
                        transcript_file.write_text(transcript, encoding="utf-8")
                    except Exception:
                        pass
            except Exception as e:
                log.warning(f"On-demand transcription failed: {e}")

        if transcript:
            excerpt = transcript[:15000]
            if len(transcript) > 15000:
                excerpt += "\n\n[...transcript truncated for summary...]"
            resp = think(
                "Summarize this meeting from the transcript below. Use markdown with a short "
                "overview, key discussion points, decisions made, and action items (with owners "
                "if named).\n\nTRANSCRIPT:\n" + excerpt
            )
        else:
            if audio_file.exists():
                context_parts.append("Meeting audio was recorded but could not be transcribed.")
            if not context_parts:
                return SkillResult(
                    success=False,
                    error=f"meeting dir {meeting_dir.name} exists but has no usable content yet."
                )
            context = "\n".join(context_parts)
            resp = think(
                f"Generate a brief meeting note from the following metadata (no transcript was "
                f"available).\nMeeting: {meeting_dir.name}\n{context}\n\n"
                f"Format with: Overview, Key Points, Action Items.",
                context=context
            )
        content = resp.get("choices", [{}])[0].get("message", {}).get("content", "")

        if not content:
            return SkillResult(success=False, error="brain returned empty summary.")

        # Cache the generated summary
        try:
            summary_file.write_text(content, encoding="utf-8")
        except Exception:
            pass

        # Save to notes so it shows up in the Notes view
        _save_to_notes(meeting_dir.name, content)

        return SkillResult(
            success=True,
            output_text=f"**{meeting_dir.name}**\n\n{content}",
            extras={"meeting_dir": str(meeting_dir), "source": "generated"}
        )


if __name__ == "__main__":
    skill = MeetingSummarySkill()
    print(skill.run(SkillContext()))
