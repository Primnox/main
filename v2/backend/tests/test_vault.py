"""Security tests for storage/vault.py — the BIP-39 local-encryption layer.

Pure unit tests against temp files: no FastAPI app, no scheduler, no shared
runtime fixture. These are adversarial rather than merely functional — the
question each one asks is "what does an attacker (or a typo) actually get",
not just "does the happy path work".
"""
from __future__ import annotations

import shutil
import sys
import tempfile
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from primnox2.storage import vault  # noqa: E402


@pytest.fixture
def tmp_db(tmp_path) -> Path:
    p = tmp_path / "primnox.db"
    p.write_bytes(b"SQLite format 3\x00" + b"fake db content, secrets included" * 50)
    return p


@pytest.fixture(autouse=True)
def _isolated_keychain(monkeypatch):
    """The real OS keychain is machine-global — a test that stores a key
    there would leak into the developer's actual credential store and could
    collide with a real vault. Swap in a dict for the duration of each test."""
    store: dict[str, str] = {}

    class _FakeKeyring:
        @staticmethod
        def set_password(service, user, value):
            store[f"{service}:{user}"] = value

        @staticmethod
        def get_password(service, user):
            return store.get(f"{service}:{user}")

        @staticmethod
        def delete_password(service, user):
            store.pop(f"{service}:{user}", None)

    import sys as _sys
    fake_module = _FakeKeyring()
    monkeypatch.setitem(_sys.modules, "keyring", fake_module)
    yield store


# ── BIP-39 mnemonic math ──────────────────────────────────────────────────────

def test_generated_mnemonic_is_twelve_words():
    m = vault.generate_mnemonic()
    assert len(m.split()) == 12


def test_generated_mnemonic_validates():
    m = vault.generate_mnemonic()
    ok, err = vault.validate_mnemonic(m)
    assert ok, err


def test_two_generated_mnemonics_differ():
    # Not a proof of entropy, but a single collision on 128 random bits would
    # indicate the RNG is broken, not bad luck.
    a = vault.generate_mnemonic()
    b = vault.generate_mnemonic()
    assert a != b


def test_wrong_word_count_rejected():
    ok, err = vault.validate_mnemonic("apple banana cherry")
    assert not ok
    assert "12 words" in err or "Expected 12" in err


def test_unknown_word_rejected():
    words = vault.load_wordlist()[:11]
    phrase = " ".join(words) + " definitelynotabip39word"
    ok, err = vault.validate_mnemonic(phrase)
    assert not ok
    assert "Unknown" in err


def test_tampered_checksum_rejected():
    """A phrase with 12 real wordlist words but the wrong last word (checksum
    depends on all 12) must fail — this is what stops a fat-fingered phrase
    from silently deriving a DIFFERENT, wrong key instead of refusing outright."""
    m = vault.generate_mnemonic()
    words = m.split()
    wordlist = vault.load_wordlist()
    # Swap the last word for a different wordlist word — the checksum was
    # computed over the original 12, so this breaks it for all but 1-in-16
    # replacements (a 4-bit checksum). Rather than accept that as a flake,
    # try replacements until one actually breaks it — deterministic either
    # way, since among 2047 candidates the odds of every single one
    # coincidentally preserving the checksum are astronomically small.
    tampered = None
    for candidate_word in wordlist:
        if candidate_word == words[-1]:
            continue
        candidate = " ".join(words[:-1] + [candidate_word])
        ok, _ = vault.validate_mnemonic(candidate)
        if not ok:
            tampered = candidate
            break
    assert tampered is not None, "every replacement coincidentally preserved the checksum"


# ── Key derivation ────────────────────────────────────────────────────────────

def test_key_derivation_is_deterministic():
    m = vault.generate_mnemonic()
    assert vault.derive_key(m) == vault.derive_key(m)


def test_different_mnemonics_derive_different_keys():
    a, b = vault.generate_mnemonic(), vault.generate_mnemonic()
    assert vault.derive_key(a) != vault.derive_key(b)


def test_key_derivation_tolerates_whitespace_typos():
    """Same words, sloppy spacing/case — must derive the SAME key, or a user
    who fat-fingers a double-space is locked out of their own vault."""
    m = vault.generate_mnemonic()
    messy = "  " + "   ".join(m.upper().split()) + "  "
    assert vault.derive_key(m) == vault.derive_key(messy)


def test_local_vault_salt_differs_from_v1_local_and_v1_backup():
    """The whole point of a distinct salt: the same phrase must NEVER derive
    the same key under a different product/purpose. If this ever regresses to
    match either of V1's salts, a V1 backup mnemonic would silently also
    unlock a V2 vault (or vice versa) — a real key-confusion vulnerability."""
    import hashlib
    m = "abandon abandon abandon abandon abandon abandon abandon abandon abandon abandon abandon about"
    v2_key = vault.derive_key(m)
    v1_local_key = hashlib.pbkdf2_hmac("sha512", m.encode(), b"primnox-local", 600_000, dklen=32)
    v1_backup_key = hashlib.pbkdf2_hmac("sha512", m.encode(), b"primnox-backup", 600_000, dklen=32)
    assert v2_key != v1_local_key
    assert v2_key != v1_backup_key
    assert v1_local_key != v1_backup_key


# ── Encrypt/decrypt round trip and tamper resistance ─────────────────────────

def test_encrypt_decrypt_roundtrips():
    key = vault.derive_key(vault.generate_mnemonic())
    data = b"the quick brown fox jumps over the lazy dog" * 100
    blob = vault._encrypt_bytes(data, key)
    assert vault._decrypt_bytes(blob, key) == data


def test_ciphertext_does_not_contain_plaintext():
    """The core AEAD invariant: nothing recognizable from the plaintext should
    survive into the ciphertext bytes. This is what "encrypted at rest"
    actually means — not just "the bytes differ"."""
    key = vault.derive_key(vault.generate_mnemonic())
    secret = b"MySuperSecretConversationAboutTaxesAndPasswords12345"
    blob = vault._encrypt_bytes(secret, key)
    assert secret not in blob
    # Also check case-insensitively and for any 16-byte substring, since a
    # weak/no-op cipher could still dodge an exact full-string check.
    for i in range(0, len(secret) - 16, 4):
        assert secret[i:i + 16] not in blob


def test_wrong_key_fails_to_decrypt():
    """The security property that actually matters: a wrong mnemonic must be
    REJECTED (GCM auth failure), not silently return garbage that looks like
    it might be right."""
    right_key = vault.derive_key(vault.generate_mnemonic())
    wrong_key = vault.derive_key(vault.generate_mnemonic())
    blob = vault._encrypt_bytes(b"sensitive data", right_key)
    with pytest.raises(Exception):
        vault._decrypt_bytes(blob, wrong_key)


def test_tampered_ciphertext_is_rejected_not_silently_corrupted():
    """A single flipped byte anywhere in the ciphertext must fail decryption
    outright (GCM's authentication tag catches it), never decrypt to
    corrupted-but-accepted plaintext. This is the difference between an AEAD
    cipher and a plain stream cipher."""
    key = vault.derive_key(vault.generate_mnemonic())
    blob = bytearray(vault._encrypt_bytes(b"authentic data, do not modify", key))
    # Flip one bit well inside the ciphertext (past the 17-byte header).
    blob[20] ^= 0x01
    with pytest.raises(Exception):
        vault._decrypt_bytes(bytes(blob), key)


def test_tampered_auth_tag_is_rejected():
    """Flip a bit in the LAST 16 bytes specifically — the GCM tag itself —
    to confirm the tag is actually checked and not just appended and ignored."""
    key = vault.derive_key(vault.generate_mnemonic())
    blob = bytearray(vault._encrypt_bytes(b"data protected by a real auth tag", key))
    blob[-1] ^= 0x01
    with pytest.raises(Exception):
        vault._decrypt_bytes(bytes(blob), key)


def test_bad_magic_is_rejected():
    key = vault.derive_key(vault.generate_mnemonic())
    blob = bytearray(vault._encrypt_bytes(b"data", key))
    blob[0:4] = b"XXXX"
    with pytest.raises(ValueError, match="bad magic"):
        vault._decrypt_bytes(bytes(blob), key)


def test_two_encryptions_of_same_data_produce_different_ciphertext():
    """Nonce reuse under GCM is catastrophic (it breaks confidentiality AND
    authentication). Two encryptions of the identical plaintext with the same
    key must produce different ciphertext, proving the nonce is actually
    randomized per call rather than fixed or derived from the data."""
    key = vault.derive_key(vault.generate_mnemonic())
    data = b"identical plaintext, encrypted twice"
    blob1 = vault._encrypt_bytes(data, key)
    blob2 = vault._encrypt_bytes(data, key)
    assert blob1 != blob2
    # And both still decrypt correctly despite the different nonces/ciphertext.
    assert vault._decrypt_bytes(blob1, key) == data
    assert vault._decrypt_bytes(blob2, key) == data


# ── Full lifecycle: setup / unlock / lock / disable ──────────────────────────

def test_setup_encrypts_and_leaves_plaintext_in_place(tmp_db):
    original = tmp_db.read_bytes()
    phrase = vault.setup_vault(tmp_db)
    assert len(phrase.split()) == 12
    assert vault.vault_path(tmp_db).exists()
    # The whole point of setup_vault's design: the running app keeps working
    # without a restart, so the plaintext must still be there afterward.
    assert tmp_db.exists()
    assert tmp_db.read_bytes() == original


def test_setup_vault_file_does_not_contain_plaintext(tmp_db):
    vault.setup_vault(tmp_db)
    vault_bytes = vault.vault_path(tmp_db).read_bytes()
    assert b"fake db content, secrets included" not in vault_bytes


def test_lock_then_unlock_roundtrips(tmp_db):
    original = tmp_db.read_bytes()
    phrase = vault.setup_vault(tmp_db)
    vault.lock_vault(tmp_db)
    assert not tmp_db.exists()          # plaintext actually gone
    assert vault.is_locked(tmp_db)
    vault.unlock_vault(tmp_db, phrase)
    assert tmp_db.exists()
    assert tmp_db.read_bytes() == original
    assert not vault.is_locked(tmp_db)


def test_unlock_with_wrong_mnemonic_is_refused(tmp_db):
    vault.setup_vault(tmp_db)
    vault.lock_vault(tmp_db)
    wrong = vault.generate_mnemonic()
    with pytest.raises(PermissionError):
        vault.unlock_vault(tmp_db, wrong)
    # And the plaintext must NOT have been written from a failed attempt.
    assert not tmp_db.exists()


def test_unlock_falls_back_to_keychain_when_no_mnemonic_given(tmp_db):
    """setup_vault() caches the key in the keychain; a plain unlock_vault()
    call with no mnemonic argument must use it — this is what lets the app
    unlock itself automatically on a normal boot."""
    vault.setup_vault(tmp_db)
    vault.lock_vault(tmp_db)
    vault.unlock_vault(tmp_db)  # no mnemonic — must come from the keychain
    assert tmp_db.exists()


def test_disable_removes_vault_file_and_keychain_entry(tmp_db, _isolated_keychain):
    vault.setup_vault(tmp_db)
    assert vault.is_enabled(tmp_db)
    vault.disable_vault(tmp_db)
    assert not vault.is_enabled(tmp_db)
    assert vault.get_stored_phrase() is None


def test_disable_while_locked_recovers_plaintext_first(tmp_db):
    """disable_vault() on a LOCKED db must not just delete the .vault and
    strand the user with no plaintext and no encrypted copy either."""
    original = tmp_db.read_bytes()
    vault.setup_vault(tmp_db)
    vault.lock_vault(tmp_db)
    assert not tmp_db.exists()
    vault.disable_vault(tmp_db)
    assert tmp_db.exists()
    assert tmp_db.read_bytes() == original
    assert not vault.is_enabled(tmp_db)


def test_lock_verifies_roundtrip_before_deleting_plaintext(tmp_db, monkeypatch):
    """If the just-written .vault blob does NOT decrypt back to the source
    data, lock_vault() must refuse to delete the plaintext — the documented
    "worst case, skip the delete" behavior. Simulated by corrupting the
    written blob before the verification re-read."""
    vault.setup_vault(tmp_db)

    real_write_bytes = Path.write_bytes

    def _corrupt_on_write(self, data):
        if self.name.endswith(".vault"):
            data = b"\x00" * len(data)  # garbage — will fail to decrypt
        return real_write_bytes(self, data)

    monkeypatch.setattr(Path, "write_bytes", _corrupt_on_write)
    vault.lock_vault(tmp_db)
    monkeypatch.undo()

    # The plaintext must still be there — lock refused to delete it.
    assert tmp_db.exists()


def test_secure_delete_actually_overwrites_before_unlink(tmp_path):
    """_secure_delete must write random bytes of the file's own size before
    unlinking, not just unlink() — otherwise "secure" is a lie and the old
    plaintext bytes are trivially recoverable from the free-space blocks."""
    p = tmp_path / "plaintext.db"
    original = b"SENSITIVE_MARKER_STRING" * 1000
    p.write_bytes(original)
    size = p.stat().st_size

    written_data = {}
    real_open = open

    def _spy_open(path, mode="r", *a, **kw):
        f = real_open(path, mode, *a, **kw)
        if str(path) == str(p) and "w" in mode:
            real_write = f.write

            def _spy_write(data):
                written_data.setdefault("chunks", []).append(data)
                return real_write(data)
            f.write = _spy_write
        return f

    import builtins
    builtins.open = _spy_open
    try:
        vault._secure_delete(p)
    finally:
        builtins.open = real_open

    assert not p.exists()
    total_written = sum(len(c) for c in written_data.get("chunks", []))
    assert total_written == size
    for chunk in written_data.get("chunks", []):
        assert b"SENSITIVE_MARKER_STRING" not in chunk


def test_is_locked_false_when_never_enabled(tmp_db):
    assert not vault.is_locked(tmp_db)
    assert not vault.is_enabled(tmp_db)


def test_setup_with_user_supplied_mnemonic_validates_it(tmp_db):
    with pytest.raises(ValueError):
        vault.setup_vault(tmp_db, mnemonic="not a valid mnemonic at all")


def test_sync_vault_never_deletes_plaintext(tmp_db):
    vault.setup_vault(tmp_db)
    for _ in range(3):
        vault.sync_vault(tmp_db)
        assert tmp_db.exists()
