"""Tests for the retrieval router.

The worked examples in the architecture documents are the specification, so
most of these are those questions and the route each is supposed to take.
The one the whole module exists for: a lexical question must not touch the
graph.
"""

from v2 import router


def sources(question: str) -> list[str]:
    return router.route(question).sources


class TestTheDivisionOfLabour:
    def test_an_exact_lookup_goes_to_search_not_the_graph(self):
        """The failure this module was written against: using graph
        proximity for a question that needed lexical precision."""
        route = router.route("Where is the API key handling?")
        assert route.label == "S"
        assert "G" not in route.sources

    def test_a_filename_lookup_stays_lexical(self):
        assert "G" not in sources("Which file defines settings_manager.py?")

    def test_callers_go_to_the_graph(self):
        assert router.route("What calls authenticate()?").label == "G"

    def test_dependents_go_to_the_graph(self):
        assert router.route("What depends on vault.py?").label == "G"

    def test_impact_pulls_in_search_and_history_as_well(self):
        route = router.route("If I change this function, what could break?")
        assert route.label == "C"
        assert route.sources[0] == "G"
        assert {"S", "H"} <= set(route.sources)

    def test_a_diagnosis_is_a_compound_question(self):
        route = router.route("Why is authentication failing?")
        assert route.label == "C"
        assert {"G", "S", "H", "T"} <= set(route.sources)


class TestTemporalAndMemory:
    def test_yesterday_goes_to_history(self):
        assert router.route("What was I doing yesterday?").label == "H"

    def test_what_changed_goes_to_history(self):
        assert router.route("What changed yesterday?").label == "H"

    def test_where_did_i_leave_off_needs_state_and_history(self):
        route = router.route("What was I working on before I stopped?")
        assert route.sources[0] == "T"
        assert "H" in route.sources

    def test_continue_resumes_from_state(self):
        route = router.route("Continue what I was doing.")
        assert route.sources[0] == "T"
        assert "H" in route.sources

    def test_what_have_you_tried_is_task_state(self):
        assert router.route("What have you already tried?").label == "T"

    def test_what_do_you_remember_combines_facts_and_episodes(self):
        route = router.route("What do you remember about this project?")
        assert route.sources[0] == "M"
        assert "H" in route.sources

    def test_provenance_questions_go_to_memory(self):
        assert "M" in sources("Why do you remember that?")


class TestArtifacts:
    def test_a_document_reference_goes_to_read(self):
        assert router.route("According to that PDF, what is the retention policy?").label == "R"

    def test_a_generated_file_goes_to_read(self):
        assert router.route("Where is the report you made?").label == "R"

    def test_an_explicit_file_read_goes_to_read(self):
        assert router.route("Open the file backend/router.py").sources[0] == "R"


class TestIntent:
    def test_an_instruction_to_remember_is_a_write(self):
        route = router.route("Remember that this project uses pnpm.")
        assert route.intent == "remember"
        assert route.label == "M"

    def test_a_correction_is_a_forget(self):
        assert router.route("Forget that; we switched to npm.").intent == "forget"

    def test_asking_why_something_is_remembered_is_not_an_instruction(self):
        """`remember that` appears in both; only one of them is a command."""
        assert router.route("Why do you remember that?").intent == "retrieve"

    def test_an_imperative_is_an_action(self):
        assert router.route("Handle this.").intent == "act"
        assert router.route("Run the test suite").intent == "act"

    def test_a_question_is_not_an_action(self):
        assert router.route("What is this function?").intent == "retrieve"


class TestSecrets:
    def test_credential_questions_are_flagged(self):
        assert router.route("What's my API key?").requires_secret is True

    def test_ordinary_questions_are_not_flagged(self):
        assert router.route("What calls authenticate()?").requires_secret is False


class TestRobustness:
    def test_sources_are_always_populated(self):
        for question in ["", "   ", "asdfgh", "What calls x()?", "Why is login failing?"]:
            assert router.route(question).sources

    def test_an_empty_question_does_not_raise(self):
        assert router.route("").label in router.LABELS

    def test_an_unrecognised_question_falls_back_cheaply(self):
        route = router.route("qwertyuiop")
        assert route.label == router.DEFAULT_LABEL
        assert route.confidence < router.LOW_CONFIDENCE

    def test_a_bare_remember_with_no_other_signal_still_reaches_memory(self):
        assert router.route("Remember that.").label == "M"

    def test_combining_can_be_switched_off(self):
        route = router.route("Why is authentication failing?", allow_combined=False)
        assert route.label != "C"
        assert len(route.sources) == 1

    def test_the_decision_is_explainable(self):
        explanation = router.route("What calls authenticate()?").explain()
        assert "graphify" in explanation
        assert "callers" in explanation

    def test_source_names_are_readable(self):
        assert router.route("What was I doing yesterday?").names == ["history"]


class TestClassifierHook:
    def test_a_model_label_is_used_when_valid(self):
        route = router.route("anything at all", classifier=lambda q: "G")
        assert route.label == "G"
        assert route.classifier == "model"

    def test_an_invalid_label_falls_back_to_the_heuristic(self):
        route = router.route("What calls authenticate()?", classifier=lambda q: "banana")
        assert route.label == "G"
        assert route.classifier == "heuristic"

    def test_a_raising_classifier_does_not_break_routing(self):
        def broken(question):
            raise RuntimeError("model unavailable")

        assert router.route("What calls authenticate()?", classifier=broken).label == "G"

    def test_the_classifier_prompt_covers_every_label(self):
        prompt = router.label_prompt()
        for label in router.LABELS:
            if label == "C":
                continue
            assert f"{label} =" in prompt
