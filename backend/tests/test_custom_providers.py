"""Tests for the named custom-endpoint profile system in settings_manager.py:
the migration from the old single flat custom_* slot into custom_providers[],
and per-profile keyring mirroring (each profile's api_key is stored under its
own keyring entry, not a single fixed key like the *_api_key fields use).

Real OS keyring access is never exercised here — keyring.set_password/
get_password/delete_password are monkeypatched to an in-memory dict so tests
can't write to the actual Windows Credential Manager / macOS Keychain.
"""
import json

import pytest

import settings_manager as sm


@pytest.fixture
def fake_keyring(monkeypatch):
    """In-memory stand-in for the OS keyring, keyed like the real one:
    (service, username) -> password."""
    store: dict[tuple[str, str], str] = {}

    class FakeKeyring:
        @staticmethod
        def set_password(service, username, password):
            store[(service, username)] = password

        @staticmethod
        def get_password(service, username):
            return store.get((service, username))

        @staticmethod
        def delete_password(service, username):
            if (service, username) not in store:
                raise Exception("not found")
            del store[(service, username)]

    import sys
    monkeypatch.setitem(sys.modules, "keyring", FakeKeyring)
    return store


@pytest.fixture
def settings_path(tmp_path, monkeypatch):
    path = tmp_path / "settings.json"
    monkeypatch.setattr(sm, "SETTINGS_PATH", path)
    return path


class TestDefaultSettingsSchema:
    def test_new_model_keys_present(self):
        assert sm.DEFAULT_SETTINGS["openai_model"] == ""
        assert sm.DEFAULT_SETTINGS["anthropic_model"] == ""
        assert sm.DEFAULT_SETTINGS["groq_model"] == ""
        assert sm.DEFAULT_SETTINGS["gemini_model"] == "gemini-2.0-flash"

    def test_custom_providers_defaults_empty(self):
        assert sm.DEFAULT_SETTINGS["custom_providers"] == []
        assert sm.DEFAULT_SETTINGS["active_custom_provider_id"] == ""

    def test_flat_custom_fields_removed(self):
        assert "custom_api_type" not in sm.DEFAULT_SETTINGS
        assert "custom_base_url" not in sm.DEFAULT_SETTINGS
        assert "custom_api_key" not in sm.DEFAULT_SETTINGS
        assert "custom_model" not in sm.DEFAULT_SETTINGS

    def test_code_execution_defaults_off(self):
        # Sandboxed run_python/run_shell must be opt-in: a fresh install (or
        # anyone who never visits Settings) should never have the account
        # provisioned or the tools exposed to the model.
        assert sm.DEFAULT_SETTINGS["code_execution_enabled"] is False
        assert sm.DEFAULT_SETTINGS["sandbox_account_ready"] is False


class TestMigration:
    def test_legacy_flat_fields_become_a_profile(self, settings_path, fake_keyring):
        settings_path.write_text(json.dumps({
            "custom_api_type": "anthropic",
            "custom_base_url": "http://localhost:8000",
            "custom_api_key": "sk-legacy",
            "custom_model": "legacy-model",
        }), encoding="utf-8")

        loaded = sm.load_settings()

        assert len(loaded["custom_providers"]) == 1
        profile = loaded["custom_providers"][0]
        assert profile["name"] == "Custom"
        assert profile["api_type"] == "anthropic"
        assert profile["base_url"] == "http://localhost:8000"
        assert profile["api_key"] == "sk-legacy"
        assert profile["model"] == "legacy-model"
        assert loaded["active_custom_provider_id"] == profile["id"]

    def test_no_migration_when_no_legacy_url(self, settings_path, fake_keyring):
        settings_path.write_text(json.dumps({"nickname": "test"}), encoding="utf-8")
        loaded = sm.load_settings()
        assert loaded["custom_providers"] == []
        assert loaded["active_custom_provider_id"] == ""

    def test_no_migration_when_providers_already_exist(self, settings_path, fake_keyring):
        settings_path.write_text(json.dumps({
            "custom_base_url": "http://localhost:8000",
            "custom_providers": [{"id": "existing", "name": "Existing", "api_type": "openai",
                                   "base_url": "http://x", "api_key": "", "model": ""}],
        }), encoding="utf-8")
        loaded = sm.load_settings()
        assert len(loaded["custom_providers"]) == 1
        assert loaded["custom_providers"][0]["id"] == "existing"


class TestPerProfileKeyring:
    def test_save_scrubs_plaintext_key_from_disk(self, settings_path, fake_keyring):
        settings = {**sm.DEFAULT_SETTINGS, "custom_providers": [
            {"id": "abc123", "name": "Test", "api_type": "openai", "base_url": "http://x", "api_key": "sk-real", "model": ""}
        ]}
        sm.save_settings(settings)

        on_disk = json.loads(settings_path.read_text(encoding="utf-8"))
        assert on_disk["custom_providers"][0]["api_key"] == ""
        assert fake_keyring[("primnox", "custom_provider_abc123")] == "sk-real"

    def test_load_restores_key_from_keyring(self, settings_path, fake_keyring):
        fake_keyring[("primnox", "custom_provider_abc123")] = "sk-restored"
        settings_path.write_text(json.dumps({
            "custom_providers": [{"id": "abc123", "name": "Test", "api_type": "openai",
                                   "base_url": "http://x", "api_key": "", "model": ""}],
        }), encoding="utf-8")

        loaded = sm.load_settings()
        assert loaded["custom_providers"][0]["api_key"] == "sk-restored"

    def test_round_trip_preserves_key_across_save_and_load(self, settings_path, fake_keyring):
        settings = {**sm.DEFAULT_SETTINGS, "custom_providers": [
            {"id": "p1", "name": "Test", "api_type": "openai", "base_url": "http://x", "api_key": "sk-roundtrip", "model": "m"}
        ]}
        sm.save_settings(settings)
        reloaded = sm.load_settings()
        assert reloaded["custom_providers"][0]["api_key"] == "sk-roundtrip"

    def test_delete_custom_provider_key_wipes_keyring_entry(self, fake_keyring):
        fake_keyring[("primnox", "custom_provider_xyz")] = "sk-to-delete"
        sm.delete_custom_provider_key("xyz")
        assert ("primnox", "custom_provider_xyz") not in fake_keyring

    def test_empty_api_key_is_not_mirrored(self, settings_path, fake_keyring):
        settings = {**sm.DEFAULT_SETTINGS, "custom_providers": [
            {"id": "p1", "name": "Test", "api_type": "openai", "base_url": "http://x", "api_key": "", "model": ""}
        ]}
        sm.save_settings(settings)
        assert not fake_keyring.get(("primnox", "custom_provider_p1"))
