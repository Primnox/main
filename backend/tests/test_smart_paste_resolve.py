"""Regression test for a real bug found live: Smart Paste's cloud fallback
used to extract choices[].message.content without checking for an "error"
key alongside it. On the shipped default config (Groq active, no API key
set), think() returns a well-formed choices[] whose content is the apology
"Sorry, cannot process this request without AI. Please add your Groq API
key in Settings." — Smart Paste blindly wrote that into the user's OS
clipboard and reported success. brain.resolve_think_text() is the shared
fix: it must return the caller's fallback (the original clipboard content)
whenever an "error" key is present, regardless of what choices[] says.
"""
import brain


def test_returns_fallback_when_error_present_even_with_wellformed_choices():
    response = {
        "error": "Groq API key not set",
        "choices": [{"message": {"content": "Sorry, cannot process this request without AI. Please add your Groq API key in Settings."}}],
    }
    assert brain.resolve_think_text(response, "original clipboard text") == "original clipboard text"


def test_returns_fallback_when_error_present_with_no_choices_key():
    response = {"error": "OpenAI API key not set"}
    assert brain.resolve_think_text(response, "original clipboard text") == "original clipboard text"


def test_returns_transformed_text_on_success():
    response = {"choices": [{"message": {"content": "  Hey team, see you at 3pm.  "}}]}
    assert brain.resolve_think_text(response, "fallback") == "Hey team, see you at 3pm."


def test_returns_fallback_when_choices_empty_or_blank():
    assert brain.resolve_think_text({"choices": []}, "fallback") == "fallback"
    assert brain.resolve_think_text({"choices": [{"message": {"content": "   "}}]}, "fallback") == "fallback"
