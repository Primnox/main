"""Tests for the new tools added to tools.py: delete_memory/delete_note
(gated by permission_manager), list_skills/use_skill (dynamic skill
discovery for the LLM, fallback to the existing keyword-trigger fast path),
and run_python/run_shell (dispatch to code_exec, which owns the actual
permission gate and sandboxing — see test_code_exec.py for that)."""
import tools
import memory
import notes_manager
import permission_manager
import code_exec
from skills import skill_router


class TestDeleteMemoryTool:
    def test_no_match_returns_not_found_without_prompting(self, monkeypatch):
        monkeypatch.setattr(memory, "search_memories", lambda query, limit=1: [])
        prompted = []
        monkeypatch.setattr(permission_manager, "request_permission", lambda **kw: prompted.append(kw) or True)

        result = tools.execute_tool("delete_memory", {"query": "nonexistent"}, session_id="s1")

        assert "Couldn't find" in result
        assert prompted == []  # never asked — nothing to delete

    def test_allowed_deletes_and_confirms(self, monkeypatch):
        monkeypatch.setattr(memory, "search_memories", lambda query, limit=1: [{"key": "k1", "text": "likes pizza"}])
        deleted = []
        monkeypatch.setattr(memory, "delete_memory", lambda key: deleted.append(key))
        monkeypatch.setattr(permission_manager, "request_permission", lambda **kw: True)

        result = tools.execute_tool("delete_memory", {"query": "pizza"}, session_id="s1")

        assert deleted == ["k1"]
        assert "Deleted memory" in result
        assert "likes pizza" in result

    def test_denied_does_not_delete(self, monkeypatch):
        monkeypatch.setattr(memory, "search_memories", lambda query, limit=1: [{"key": "k1", "text": "likes pizza"}])
        deleted = []
        monkeypatch.setattr(memory, "delete_memory", lambda key: deleted.append(key))
        monkeypatch.setattr(permission_manager, "request_permission", lambda **kw: False)

        result = tools.execute_tool("delete_memory", {"query": "pizza"}, session_id="s1")

        assert deleted == []
        assert "cancelled" in result.lower()

    def test_permission_request_carries_session_id(self, monkeypatch):
        monkeypatch.setattr(memory, "search_memories", lambda query, limit=1: [{"key": "k1", "text": "x"}])
        monkeypatch.setattr(memory, "delete_memory", lambda key: None)
        captured = {}

        def fake_request(**kw):
            captured.update(kw)
            return True

        monkeypatch.setattr(permission_manager, "request_permission", fake_request)
        tools.execute_tool("delete_memory", {"query": "x"}, session_id="session-42")

        assert captured["session_id"] == "session-42"
        assert captured["action"] == "delete_memory"


class TestDeleteNoteTool:
    def test_no_match_returns_not_found(self, monkeypatch):
        monkeypatch.setattr(notes_manager, "search_notes", lambda query, limit=1: [])
        result = tools.execute_tool("delete_note", {"query": "nonexistent"}, session_id="s1")
        assert "Couldn't find" in result

    def test_allowed_deletes(self, monkeypatch):
        monkeypatch.setattr(notes_manager, "search_notes", lambda query, limit=1: [{"id": 7, "title": "Shopping list"}])
        deleted = []
        monkeypatch.setattr(notes_manager, "delete_note", lambda note_id: deleted.append(note_id))
        monkeypatch.setattr(permission_manager, "request_permission", lambda **kw: True)

        result = tools.execute_tool("delete_note", {"query": "shopping"}, session_id="s1")

        assert deleted == [7]
        assert "Shopping list" in result

    def test_denied_does_not_delete(self, monkeypatch):
        monkeypatch.setattr(notes_manager, "search_notes", lambda query, limit=1: [{"id": 7, "title": "Shopping list"}])
        deleted = []
        monkeypatch.setattr(notes_manager, "delete_note", lambda note_id: deleted.append(note_id))
        monkeypatch.setattr(permission_manager, "request_permission", lambda **kw: False)

        result = tools.execute_tool("delete_note", {"query": "shopping"}, session_id="s1")

        assert deleted == []
        assert "cancelled" in result.lower()


class TestListSkillsTool:
    def test_no_skills_registered(self, monkeypatch):
        monkeypatch.setattr(skill_router, "list_skills", lambda: [])
        result = tools.execute_tool("list_skills", {})
        assert "No skills" in result

    def test_lists_registered_skills(self, monkeypatch):
        monkeypatch.setattr(skill_router, "list_skills", lambda: [
            {"name": "pdf_analysis", "description": "Analyze PDFs."},
            {"name": "calendar", "description": "Manage calendar events."},
        ])
        result = tools.execute_tool("list_skills", {})
        assert "pdf_analysis" in result
        assert "Analyze PDFs." in result
        assert "calendar" in result


class TestUseSkillTool:
    def test_successful_invocation_returns_output_text(self, monkeypatch):
        monkeypatch.setattr(skill_router, "route_skill", lambda **kw: {
            "success": True, "output_text": "Generated a 3-slide deck.",
        })
        result = tools.execute_tool("use_skill", {"skill_name": "ppt", "query": "make a deck"}, session_id="s1")
        assert result == "Generated a 3-slide deck."

    def test_unknown_skill_returns_error(self, monkeypatch):
        monkeypatch.setattr(skill_router, "route_skill", lambda **kw: {
            "success": False, "error": "No skill named 'bogus'. Use list_skills to see available names.",
        })
        result = tools.execute_tool("use_skill", {"skill_name": "bogus", "query": "do something"}, session_id="s1")
        assert "No skill named" in result

    def test_passes_skill_name_and_session_id_through(self, monkeypatch):
        captured = {}

        def fake_route_skill(**kw):
            captured.update(kw)
            return {"success": True, "output_text": "ok"}

        monkeypatch.setattr(skill_router, "route_skill", fake_route_skill)
        tools.execute_tool("use_skill", {"skill_name": "pdf_analysis", "query": "extract tables"}, session_id="session-9")

        assert captured["skill_name"] == "pdf_analysis"
        assert captured["user_message"] == "extract tables"
        assert captured["session_id"] == "session-9"


class TestRunPythonRunShellDispatch:
    def test_run_python_delegates_to_code_exec(self, monkeypatch):
        captured = {}

        def fake_run_python(code, session_id=""):
            captured.update(code=code, session_id=session_id)
            return {"success": True, "return_code": 0, "stdout": "hi\n", "stderr": "",
                    "timed_out": False, "files_created": []}

        monkeypatch.setattr(code_exec, "run_python", fake_run_python)
        result = tools.execute_tool("run_python", {"code": "print('hi')"}, session_id="s1")

        assert captured == {"code": "print('hi')", "session_id": "s1"}
        assert "exit code: 0" in result
        assert "hi" in result

    def test_run_shell_delegates_to_code_exec(self, monkeypatch):
        captured = {}

        def fake_run_shell(code, session_id=""):
            captured.update(code=code, session_id=session_id)
            return {"success": True, "return_code": 0, "stdout": "", "stderr": "",
                    "timed_out": False, "files_created": []}

        monkeypatch.setattr(code_exec, "run_shell", fake_run_shell)
        tools.execute_tool("run_shell", {"code": "dir"}, session_id="s2")

        assert captured == {"code": "dir", "session_id": "s2"}

    def test_error_result_returns_error_string_not_formatted_output(self, monkeypatch):
        monkeypatch.setattr(code_exec, "run_python", lambda code, session_id="": {
            "success": False, "error": "Sandboxed execution isn't set up. Enable it in Settings.",
        })
        result = tools.execute_tool("run_python", {"code": "print(1)"}, session_id="s1")
        assert result == "Sandboxed execution isn't set up. Enable it in Settings."

    def test_timed_out_result_is_noted_in_output(self, monkeypatch):
        monkeypatch.setattr(code_exec, "run_python", lambda code, session_id="": {
            "success": True, "return_code": -1, "stdout": "", "stderr": "",
            "timed_out": True, "files_created": [],
        })
        result = tools.execute_tool("run_python", {"code": "while True: pass"}, session_id="s1")
        assert "timed out" in result.lower()

    def test_files_created_are_listed(self, monkeypatch):
        monkeypatch.setattr(code_exec, "run_python", lambda code, session_id="": {
            "success": True, "return_code": 0, "stdout": "", "stderr": "",
            "timed_out": False, "files_created": ["out.csv", "plot.png"],
        })
        result = tools.execute_tool("run_python", {"code": "..."}, session_id="s1")
        assert "out.csv" in result and "plot.png" in result

    def test_missing_code_argument_defaults_to_empty_string(self, monkeypatch):
        captured = {}
        monkeypatch.setattr(code_exec, "run_python", lambda code, session_id="": captured.update(code=code) or {
            "success": True, "return_code": 0, "stdout": "", "stderr": "", "timed_out": False, "files_created": [],
        })
        tools.execute_tool("run_python", {}, session_id="s1")
        assert captured["code"] == ""


class TestGetSkillByName:
    def test_resolves_by_describe_style_name(self):
        # Uses the real registry populated at import time by discover_skills().
        registry_names = {cls.name.lower().replace(" ", "_") for cls in
                           list(skill_router.SKILL_REGISTRY.values()) + list(skill_router.TRIGGER_MAP.values())}
        if not registry_names:
            return  # nothing registered in this environment (missing optional deps) — nothing to assert
        any_name = next(iter(registry_names))
        assert skill_router.get_skill_by_name(any_name) is not None

    def test_unknown_name_returns_none(self):
        assert skill_router.get_skill_by_name("definitely_not_a_real_skill_xyz") is None

    def test_empty_name_returns_none(self):
        assert skill_router.get_skill_by_name("") is None
