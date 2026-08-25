"""Tests for runtime_capabilities.py — the probe that tells skills which
runtimes actually work inside the sandbox, so they choose an implementation
up front instead of failing halfway through generating a document.

Every probe is mocked: a real one executes code as the sandbox account,
which is slow and would make results depend on whether Node happens to work
on the machine running the suite.
"""
import pytest

import code_exec
import runtime_capabilities
from runtime_capabilities import Capabilities


@pytest.fixture(autouse=True)
def _clear_cache():
    runtime_capabilities.invalidate()
    yield
    runtime_capabilities.invalidate()


@pytest.fixture(autouse=True)
def _sandbox_provisioned(monkeypatch):
    """Assume the sandbox account exists unless a test says otherwise.

    _probe() short-circuits on an unprovisioned sandbox, and provisioning is
    a real Windows account that only exists on a machine someone set it up
    on — so without this stub these tests pass on a provisioned Windows dev
    box and fail everywhere else, including two of CI's three runners. The
    test that actually cares about the unprovisioned path overrides this
    with its own monkeypatch."""
    monkeypatch.setattr("sandbox_account.sandbox_account_configured", lambda: True)


def _probe_result(stdout, success=True):
    return {"success": success, "stdout": stdout, "stderr": "", "return_code": 0 if success else 1}


class TestDetect:
    def test_reports_both_runtimes_when_both_probes_succeed(self, monkeypatch):
        def fake(language, code, timeout=0):
            if language == "python":
                return _probe_result('CAPS:{"openpyxl": true, "pillow": false}')
            return _probe_result('CAPS:{"pptxgenjs": true}')

        monkeypatch.setattr(code_exec, "run_probe", fake)
        caps = runtime_capabilities.detect()

        assert caps.sandbox is True
        assert caps.python is True
        assert caps.node is True
        assert caps.libraries == {"openpyxl": True, "pillow": False}
        assert caps.node_modules == {"pptxgenjs": True}

    def test_a_failed_node_probe_is_a_normal_outcome_not_an_error(self, monkeypatch):
        # Node genuinely does not start under the sandbox account on this
        # machine; that must degrade the capability set, not raise.
        def fake(language, code, timeout=0):
            if language == "python":
                return _probe_result('CAPS:{"openpyxl": true}')
            return _probe_result("", success=False)

        monkeypatch.setattr(code_exec, "run_probe", fake)
        caps = runtime_capabilities.detect()

        assert caps.python is True
        assert caps.node is False
        assert any("Node.js" in n for n in caps.notes)

    def test_a_raising_probe_does_not_propagate(self, monkeypatch):
        def boom(language, code, timeout=0):
            raise RuntimeError("sandbox exploded")

        monkeypatch.setattr(code_exec, "run_probe", boom)
        caps = runtime_capabilities.detect()

        assert caps.python is False
        assert caps.node is False

    def test_unparsable_probe_output_is_treated_as_unavailable(self, monkeypatch):
        monkeypatch.setattr(code_exec, "run_probe",
                            lambda language, code, timeout=0: _probe_result("CAPS:not-json"))
        assert runtime_capabilities.detect().python is False

    def test_pillow_failure_is_called_out_in_the_notes(self, monkeypatch):
        # python-pptx and reportlab both depend on it, so this one missing
        # library explains several downstream failures at once.
        monkeypatch.setattr(
            code_exec, "run_probe",
            lambda language, code, timeout=0: _probe_result('CAPS:{"pillow": false}')
            if language == "python" else _probe_result("", success=False),
        )
        caps = runtime_capabilities.detect()

        assert any("Pillow" in n for n in caps.notes)

    def test_unprovisioned_sandbox_reports_nothing_available(self, monkeypatch):
        monkeypatch.setattr("sandbox_account.sandbox_account_configured", lambda: False)
        caps = runtime_capabilities.detect()

        assert caps.sandbox is False
        assert caps.python is False
        assert caps.node is False

    def test_probes_run_once_and_are_cached(self, monkeypatch):
        calls = []

        def counting(language, code, timeout=0):
            calls.append(language)
            return _probe_result('CAPS:{}')

        monkeypatch.setattr(code_exec, "run_probe", counting)
        runtime_capabilities.detect()
        runtime_capabilities.detect()

        assert calls == ["python", "node"]

    def test_force_re_probes(self, monkeypatch):
        calls = []

        def counting(language, code, timeout=0):
            calls.append(language)
            return _probe_result('CAPS:{}')

        monkeypatch.setattr(code_exec, "run_probe", counting)
        runtime_capabilities.detect()
        runtime_capabilities.detect(force=True)

        assert len(calls) == 4


class TestProbeTargets:
    def test_pillow_is_probed_via_its_native_extension(self):
        # `import PIL` succeeds in the sandbox and proves nothing — the
        # package __init__ is pure Python while the extension that does the
        # work fails. Probing the shallow name reported Pillow as available
        # and would have routed work into a runtime crash (confirmed live).
        assert runtime_capabilities._PROBED_LIBRARIES["pillow"] == "PIL._imaging"

    def test_reportlab_is_probed_via_a_module_that_pulls_the_render_path(self):
        assert runtime_capabilities._PROBED_LIBRARIES["reportlab"].startswith("reportlab.")


class TestSummary:
    def test_summary_marks_missing_runtimes(self):
        caps = Capabilities(sandbox=True, python=True, node=False,
                            libraries={"openpyxl": True, "pillow": False})
        text = caps.summary()

        assert "Node.js      UNAVAILABLE" in text
        assert "openpyxl     available" in text
        assert "pillow       UNAVAILABLE" in text

    def test_summary_is_explicit_when_the_sandbox_is_off(self):
        assert "unavailable" in Capabilities().summary().lower()

    def test_has_checks_both_python_and_node_sides(self):
        caps = Capabilities(sandbox=True, libraries={"openpyxl": True},
                            node_modules={"pptxgenjs": True})

        assert caps.has("openpyxl") is True
        assert caps.has("pptxgenjs") is True
        assert caps.has("nonexistent") is False
