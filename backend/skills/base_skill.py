# skills/base_skill.py
import time
from dataclasses import dataclass, field
from typing import Any, Optional
from abc import ABC, abstractmethod


@dataclass
class SkillContext:
    """Typed context carrier passed into every skill execution."""
    file_path: Optional[str] = None
    user_message: Optional[str] = None
    session_id: Optional[str] = None
    chat_history: list = field(default_factory=list)
    metadata: dict = field(default_factory=dict)


@dataclass
class SkillResult:
    """Typed result returned from every skill execution."""
    success: bool = True
    output_text: str = ""
    output_path: Optional[str] = None
    confidence: float = 1.0
    elapsed_ms: float = 0.0
    extras: dict = field(default_factory=dict)
    error: Optional[str] = None


class BaseSkill(ABC):
    name: str = ""
    description: str = ""
    # Use tuples (immutable) so subclasses that forget to override their own
    # list can't accidentally mutate the shared class-level default for everyone.
    supported_extensions: tuple = ()
    trigger_words: tuple = ()
    REQUIRES_SYSTEM: tuple = ()
    REQUIRES_PIP: tuple = ()

    @property
    def input_schema(self) -> dict:
        """Claude-style tool input schema."""
        return {
            "type": "object",
            "properties": {
                "file_path": {
                    "type": "string",
                    "description": "Path to the file to process (optional)"
                },
                "user_message": {
                    "type": "string",
                    "description": "User's instruction or natural-language query"
                },
                "session_id": {
                    "type": "string",
                    "description": "Active chat session ID (optional)"
                }
            },
            "required": []
        }

    def describe(self) -> dict:
        """Return a Claude-style tool definition for this skill."""
        return {
            "name": self.name.lower().replace(" ", "_"),
            "description": self.description,
            "input_schema": self.input_schema,
            "triggers": {
                "extensions": self.supported_extensions,
                "words": self.trigger_words
            }
        }

    # ── Lifecycle hooks ───────────────────────────────────────────────────────

    def before_execute(self, ctx: SkillContext) -> None:
        """Runs before execute(). Override to add pre-processing or validation."""
        pass

    @abstractmethod
    def execute(self, ctx: SkillContext) -> SkillResult:
        raise NotImplementedError

    def after_execute(self, ctx: SkillContext, result: SkillResult) -> SkillResult:
        """Runs after execute(). Override to add post-processing or enrichment."""
        return result

    # ── Main entry point ──────────────────────────────────────────────────────

    def run(self, ctx: SkillContext) -> SkillResult:
        """
        Wires the full lifecycle:
          before_execute → execute → after_execute
        Auto-times the call and catches exceptions so callers never crash.
        """
        start = time.perf_counter()
        result = SkillResult()
        try:
            self.before_execute(ctx)
            result = self.execute(ctx)
            result = self.after_execute(ctx, result)
        except Exception as exc:
            result = SkillResult(success=False, error=str(exc))
        finally:
            result.elapsed_ms = round((time.perf_counter() - start) * 1000, 2)
        return result
