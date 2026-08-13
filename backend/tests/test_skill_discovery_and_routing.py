"""End-to-end skill DISCOVERY and ROUTING behaviour — "does the right skill
fire for the way a person actually phrases things, and does nothing fire when
it shouldn't".

This sits one level above test_semantic_router.py (which unit-tests reply
validation) and test_skill_router_semantic_resolution.py (which unit-tests the
semantic→trigger fallback). What's covered here is the *whole* resolution
path for realistic messages, plus the routing outcomes the architecture
genuinely does NOT support — chained/multi-skill turns and dependency
pipelines. Those are documented as limitations rather than dressed up as
passing features; a test that asserts a capability the code doesn't have is
worse than no test.

Two tiers, per pytest.ini:
  - default: brain.think is always mocked. Deterministic, free, fast.
  - `live`: the same phrasings against the REAL provider, to catch the case
    where the wiring is perfect and the model still picks wrong. Run with
    `pytest -m live`.
"""
import pytest

import brain
from skills import semantic_router, skill_router
from skills.skill_router import (
    CLAUDE_SKILLS_REGISTRY, TRIGGER_MAP,
    get_skill_by_name, get_skill_for_extension, list_skills,
    resolve_skill_for_message, route_skill,
)


# ── helpers ───────────────────────────────────────────────────────────────────

def _reply(text: str) -> dict:
    """A think()-shaped success response, matching test_semantic_router.py."""
    return {"choices": [{"message": {"content": text}}]}


@pytest.fixture
def model_says(monkeypatch):
    """Drive the REAL semantic_router.classify() with a scripted model reply.

    Preferred over stubbing classify() outright: it exercises catalog
    building and reply validation, so a test that says "this phrasing routes
    to pptx" is actually asserting the catalog contains a routable `pptx`
    entry, not just that a lambda was called.
    """
    def _set(reply_text: str):
        monkeypatch.setattr(brain, "think", lambda prompt, **kw: _reply(reply_text))
    return _set


@pytest.fixture
def offline(monkeypatch):
    """No provider at all — think() raises, as it does with no network."""
    def _boom(*a, **kw):
        raise ConnectionError("provider unreachable")
    monkeypatch.setattr(brain, "think", _boom)


@pytest.fixture
def never_executes(monkeypatch):
    """Fails loudly if anything actually tries to run a skill's body.

    Routing tests must never reach think()-driven execution or the sandbox;
    if one does, that's a test bug worth a hard failure rather than a slow,
    mysterious pass.
    """
    def _boom(*a, **kw):
        raise AssertionError("a routing test must not execute a skill")
    monkeypatch.setattr("skills.adapted_skill.AdaptedClaudeSkill.execute", _boom)


# ── 1. Basic discovery ────────────────────────────────────────────────────────

class TestExplicitProductNameDiscovery:
    """"Create a PowerPoint presentation about renewable energy" — the
    easiest possible case, and the one that must never regress."""

    def test_powerpoint_request_resolves_to_the_pptx_claude_skill(self, model_says):
        model_says("pptx")
        entry = resolve_skill_for_message(
            "Create a PowerPoint presentation about renewable energy"
        )
        assert entry is not None
        assert entry.name.lower() == "pptx"
        # Not just any class with the right name — the real SKILL.md package.
        assert entry is CLAUDE_SKILLS_REGISTRY["pptx"]

    def test_the_catalog_the_model_sees_actually_describes_pptx(self, monkeypatch):
        # If pptx's description never reaches the routing prompt, the model
        # cannot pick it however good it is — the failure would look like a
        # model problem and be a plumbing problem.
        captured = {}

        def _capture(prompt, **kw):
            captured["prompt"] = prompt
            return _reply("NONE")

        monkeypatch.setattr(brain, "think", _capture)
        resolve_skill_for_message("Create a PowerPoint presentation about renewable energy")

        assert "pptx" in captured["prompt"]
        assert "renewable energy" in captured["prompt"]

    def test_no_unrelated_skill_claims_a_powerpoint_request(self, offline):
        # With the model unreachable the trigger-word path is all that's
        # left. It must decline rather than hand the turn to Calendar or
        # Code Analyst because of an incidental word.
        assert resolve_skill_for_message(
            "Create a PowerPoint presentation about renewable energy"
        ) is None

    def test_a_hallucinated_deck_skill_does_not_resolve(self, model_says):
        # "powerpoint" is not a registered skill name; inventing one must
        # not create a route.
        model_says("powerpoint")
        assert resolve_skill_for_message(
            "Create a PowerPoint presentation about renewable energy"
        ) is None


# ── 2. Implicit discovery ─────────────────────────────────────────────────────

class TestImplicitDiscovery:
    """"Turn this information into 10 professional slides" — no product name,
    no file extension, no trigger phrase. This is exactly the case the
    substring matcher could never serve, and the reason semantic routing
    exists at all."""

    IMPLICIT = "Turn this information into 10 professional slides"

    def test_implicit_slide_request_resolves_to_pptx(self, model_says):
        model_says("pptx")
        entry = resolve_skill_for_message(self.IMPLICIT)
        assert entry is not None and entry.name.lower() == "pptx"

    def test_implicit_phrasing_matches_no_trigger_word_at_all(self):
        # The honest statement of what semantic routing is buying: without a
        # model this message is unroutable. Documented so a future "let's
        # just add more trigger phrases" instinct sees the cost.
        assert skill_router.get_skill_for_trigger(self.IMPLICIT) is None

    def test_pptx_carries_no_trigger_words_to_match_against(self):
        assert tuple(CLAUDE_SKILLS_REGISTRY["pptx"].trigger_words) == ()

    def test_the_word_slides_appears_in_the_routing_catalog(self):
        # Anthropic's pptx description names "slides"/"deck"/"presentation"
        # explicitly — that wording is what makes implicit routing possible,
        # so truncating it away would silently break this case.
        entry = next(c for c in semantic_router._catalog() if c["name"] == "pptx")
        assert "slide" in entry["description"].lower() or "deck" in entry["description"].lower()


# ── 3. Multi-skill workflow ───────────────────────────────────────────────────

class TestMultiSkillWorkflowIsNotSupported:
    """"Read this PDF, extract the important information, and turn it into a
    presentation" needs two skills. Primnox routes exactly ONE skill per turn.

    LIMITATION, asserted deliberately: `route_skill()` resolves a single
    entry and returns a single SkillResult; `semantic_router.classify()` is
    specified to answer with one name and treats a reply naming two skills as
    ambiguous → no match at all. There is no chaining, no hand-off, and no
    "remaining work" field in the result for a caller to act on. These tests
    pin that down so the day chaining is added, they fail and get updated —
    rather than the gap being rediscovered from a user complaint.
    """

    CHAINED = ("Read this PDF, extract the important information, "
               "and turn it into a presentation")

    def test_one_skill_wins_the_turn_and_the_other_is_simply_dropped(self, model_says):
        model_says("pptx")
        entry = resolve_skill_for_message(self.CHAINED)
        assert entry is not None
        assert entry.name.lower() == "pptx"  # the pdf half is not scheduled anywhere

    def test_a_model_that_names_both_skills_routes_to_neither(self, model_says):
        # classify() treats "pdf and pptx" as ambiguous. That's the right
        # call for a single-skill executor — picking whichever was mentioned
        # first would be a coin flip — but the user-visible effect is that
        # the most accurate possible answer produces NO skill at all.
        model_says("pdf and pptx")
        assert resolve_skill_for_message(self.CHAINED) is None

    def test_route_skill_result_carries_no_follow_up_or_chain_field(self, monkeypatch):
        # Nothing in the result dict lets a caller discover that a second
        # skill was needed.
        monkeypatch.setattr("skills.semantic_router.classify", lambda t: None)
        result = route_skill(user_message=self.CHAINED)
        assert result["success"] is False
        assert not any(k in result for k in ("next_skill", "chain", "remaining", "follow_up"))


# ── 8. Skill dependency chain ─────────────────────────────────────────────────

class TestDependencyChainIsNotSupported:
    """CSV -> analysis -> chart -> PPTX is four steps across two skills.

    What actually happens today: an attached .csv resolves to the `xlsx`
    Claude Skill by exact extension lookup and the turn ends there. Whatever
    that skill's own bounded loop manages inside its 10 sandbox steps is all
    the "chaining" that exists — there is no router-level pipeline, and the
    xlsx skill has no way to hand a finished chart to the pptx skill.
    """

    def test_a_csv_attachment_routes_to_xlsx_and_stops(self):
        entry = get_skill_for_extension("csv")
        assert entry is not None
        assert entry.name.lower() == "xlsx"

    def test_an_attached_file_never_falls_through_to_a_second_skill(self, monkeypatch):
        # Deliberate behaviour in route_skill(): an unknown extension is a
        # no-match, NOT an excuse to fire a trigger-word skill off the
        # message text. Otherwise "…and turn it into a presentation" attached
        # to a .parquet would run something arbitrary.
        def _boom(text):
            raise AssertionError("attachment routing must not consult trigger words")

        monkeypatch.setattr(skill_router, "get_skill_for_trigger", _boom)
        result = route_skill(file_path="data.parquet",
                             user_message="chart this and put it in a deck")
        assert result["success"] is False
        assert "parquet" in result["error"]

    def test_the_pipeline_phrasing_resolves_to_exactly_one_skill(self, model_says):
        model_says("xlsx")
        entry = resolve_skill_for_message(
            "Load this CSV, analyse the trends, chart them, and build a deck"
        )
        assert entry is not None and entry.name.lower() == "xlsx"


# ── 9. Missing skill ──────────────────────────────────────────────────────────

class TestMissingSkillName:
    """`use_skill` lets the model name a skill directly. A name that doesn't
    exist must produce a clean, actionable error — never a fabricated load,
    never a crash, never a silently-substituted "closest" skill."""

    MISSING = "quantum-financial-analysis"

    def test_returns_a_clean_error_not_an_exception(self):
        result = route_skill(skill_name=self.MISSING)
        assert result["success"] is False
        assert self.MISSING in result["error"]

    def test_the_error_tells_the_caller_how_to_recover(self):
        # The model is the caller here — it needs to know list_skills exists,
        # or it will just retry the same invented name.
        assert "list_skills" in route_skill(skill_name=self.MISSING)["error"]

    def test_nothing_is_loaded_or_instantiated_for_an_unknown_name(self, monkeypatch):
        def _boom(entry):
            raise AssertionError("no skill class should be resolved for an unknown name")

        monkeypatch.setattr(skill_router, "_resolve_skill_class", _boom)
        assert route_skill(skill_name=self.MISSING)["success"] is False

    def test_a_near_miss_name_is_not_fuzzily_substituted(self):
        # "pdfs" is one character off a real skill. Guessing would be worse
        # than failing: the model can correct itself, a wrong skill can't.
        assert route_skill(skill_name="pdfs")["success"] is False

    def test_an_empty_skill_name_falls_through_to_message_routing(self, monkeypatch):
        # skill_name="" is falsy, so route_skill treats it as "not supplied"
        # rather than "look up the empty name" — worth pinning since
        # get_skill_by_name("") also returns None and the two paths report
        # different errors.
        monkeypatch.setattr("skills.semantic_router.classify", lambda t: None)
        result = route_skill(skill_name="", user_message="nothing in particular")
        assert result["error"] == "No matching skill found."


# ── 30. Casual chat must cost nothing ─────────────────────────────────────────

class TestCasualChatResolvesToNoSkill:
    """A false positive here is expensive in a way a missed route isn't: it
    spins up a skill, a multi-step think() loop and an AppContainer sandbox
    to answer "thanks". The router's system prompt explicitly biases toward
    NONE for conversation; these assert that bias survives."""

    CASUAL = ["hi", "hey", "thanks!", "how was your weekend",
              "what's the capital of Japan?", "lol that's great",
              "good morning", "no worries, appreciate it"]

    @pytest.mark.parametrize("message", CASUAL)
    def test_small_talk_resolves_to_no_skill(self, message, model_says):
        model_says("NONE")
        assert resolve_skill_for_message(message) is None

    @pytest.mark.parametrize("message", CASUAL)
    def test_small_talk_matches_no_trigger_word_either(self, message):
        # Belt and braces: even if the model misfires, the fallback path
        # mustn't be the thing that turns "hi" into a skill run.
        assert skill_router.get_skill_for_trigger(message) is None

    def test_the_router_system_prompt_still_biases_toward_no_match(self):
        assert "NONE" in semantic_router._SYSTEM
        assert "greeting" in semantic_router._SYSTEM.lower()

    def test_a_greeting_never_reaches_a_skill_execution(self, model_says, never_executes):
        model_says("NONE")
        result = route_skill(user_message="hey, how was your weekend")
        assert result["success"] is False

    @pytest.mark.live
    @pytest.mark.parametrize("message", ["hi", "thanks!", "how was your weekend"])
    def test_live_model_declines_small_talk(self, message):
        """Real provider. The mocked twin above proves the wiring; only this
        proves the actual model doesn't reach for a skill on a greeting."""
        assert semantic_router.classify(message) is None


# ── 31. Provider unreachable ──────────────────────────────────────────────────

class TestOfflineStillRoutes:
    """Offline must not mean "no skills". Semantic routing is an upgrade
    layered on top of trigger words, not a replacement that becomes a single
    point of failure — every provider failure mode has to degrade to the
    keyword path rather than losing the turn."""

    def test_trigger_words_still_route_when_think_raises(self, offline):
        entry = resolve_skill_for_message("explain this code")
        assert entry is not None and entry.name == "Code Analyst"

    def test_a_provider_error_dict_also_degrades_to_trigger_words(self, monkeypatch):
        # think() reports a missing key as a 200 whose content is an apology.
        monkeypatch.setattr(brain, "think", lambda p, **kw: {
            "error": "no api key",
            "choices": [{"message": {"content": "I can't — add a key in Settings."}}],
        })
        entry = resolve_skill_for_message("take screenshot")
        assert entry is not None and entry.name == "Screenshot"

    def test_a_timeout_mid_classification_does_not_raise_to_the_caller(self, monkeypatch):
        monkeypatch.setattr(brain, "think", lambda p, **kw: (_ for _ in ()).throw(TimeoutError("slow")))
        assert resolve_skill_for_message("summarize my day") is not None

    def test_garbage_from_a_local_model_degrades_to_trigger_words(self, model_says):
        # Small local models emit chain-of-thought instead of a bare token.
        model_says("<think>Hmm, the user seems to want…</think>")
        entry = resolve_skill_for_message("what did i do today")
        assert entry is not None and entry.name == "Daily Brief"

    def test_offline_still_routes_an_attached_file_by_extension(self, offline):
        # Extension lookup never consulted the model in the first place, so
        # document skills stay fully reachable with no provider at all.
        assert get_skill_for_extension("pdf").name.lower() == "pdf"


# ── Catalog integrity ─────────────────────────────────────────────────────────

class TestCatalogIsRoutable:
    """Every advertised skill must be resolvable. A catalog entry with no
    matching registry entry is a name the model will confidently return and
    the router will then refuse — the worst of both worlds, and invisible
    without a test like this."""

    def test_every_listed_skill_resolves_by_name(self):
        for entry in list_skills():
            assert get_skill_by_name(entry["name"]) is not None, entry["name"]

    def test_every_listed_skill_has_a_description_to_route_on(self):
        # semantic_router shows the model `- name: description`. A blank
        # description makes that skill effectively unroutable.
        for entry in list_skills():
            assert entry["description"].strip(), f"{entry['name']} has no description"

    def test_the_four_document_skills_are_present(self):
        names = {e["name"] for e in list_skills()}
        assert {"pdf", "pptx", "docx", "xlsx"} <= names

    def test_no_two_registered_skills_share_a_routing_name(self):
        # get_skill_by_name() returns the FIRST match while scanning
        # SKILL_REGISTRY, then TRIGGER_MAP, then CLAUDE_SKILLS_REGISTRY — so
        # a duplicate name silently resolves to whichever the scan reaches
        # first. See test_skill_conflicts.py for what that means when two
        # packages genuinely collide.
        names = [e["name"] for e in list_skills()]
        assert len(names) == len(set(names))


# ── Live routing ──────────────────────────────────────────────────────────────

@pytest.mark.live
class TestLiveRouting:
    """The real model against the real catalog. Excluded from the default run
    (tokens + latency + non-determinism); these are what catch "the plumbing
    is perfect and the model still picks calendar"."""

    def test_live_explicit_powerpoint_request(self):
        assert semantic_router.classify(
            "Create a PowerPoint presentation about renewable energy"
        ) == "pptx"

    def test_live_implicit_slide_request(self):
        assert semantic_router.classify(
            "Turn this information into 10 professional slides"
        ) == "pptx"

    def test_live_chained_request_picks_one_skill_or_none(self):
        # Asserting the CONTRACT, not a specific answer: whatever the model
        # says, the router must hand back a single valid skill or nothing.
        result = semantic_router.classify(
            "Read this PDF, extract the important information, "
            "and turn it into a presentation"
        )
        assert result is None or result in {c["name"] for c in semantic_router._catalog()}

    def test_live_factual_question_routes_nowhere(self):
        assert semantic_router.classify("What's the capital of Japan?") is None
