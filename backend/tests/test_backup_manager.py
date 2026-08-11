"""Tests for backup_manager.py's crypto core: BIP-39-style mnemonic
generate/validate, wordlist shape validation, key derivation, and the .prx
encrypt/decrypt round trip. No existing test coverage existed for this
module before — it's the key-derivation/encryption backbone for cloud
backups (and, via local_vault.py, for local-vault encryption too), so it's
worth covering thoroughly."""
import pytest
from cryptography.exceptions import InvalidTag

import backup_manager as bm


def _wordlist(n=2048):
    return [f"word{i:04d}" for i in range(n)]


class TestWordlistShapeError:
    def test_valid_wordlist_has_no_error(self):
        assert bm._wordlist_shape_error(_wordlist()) is None

    def test_wrong_length_is_rejected(self):
        assert bm._wordlist_shape_error(_wordlist(100)) is not None

    def test_duplicate_entry_is_rejected(self):
        words = _wordlist()
        words[5] = words[10]
        err = bm._wordlist_shape_error(words)
        assert err is not None
        assert "duplicate" in err.lower()

    def test_blank_entry_is_rejected(self):
        words = _wordlist()
        words[3] = ""
        err = bm._wordlist_shape_error(words)
        assert err is not None

    def test_entry_with_internal_whitespace_is_rejected(self):
        words = _wordlist()
        words[3] = "two words"
        err = bm._wordlist_shape_error(words)
        assert err is not None

    def test_entry_with_leading_trailing_whitespace_is_rejected(self):
        words = _wordlist()
        words[3] = "  padded  "
        err = bm._wordlist_shape_error(words)
        assert err is not None


class TestGenerateMnemonic:
    def test_generates_twelve_words(self):
        phrase = bm.generate_mnemonic(_wordlist())
        assert len(phrase.split()) == 12

    def test_generated_phrase_passes_its_own_validation(self):
        wordlist = _wordlist()
        phrase = bm.generate_mnemonic(wordlist)
        valid, err = bm.validate_mnemonic(phrase, wordlist)
        assert valid is True, err

    def test_generated_words_all_come_from_the_wordlist(self):
        wordlist = _wordlist()
        phrase = bm.generate_mnemonic(wordlist)
        assert all(w in wordlist for w in phrase.split())

    def test_two_calls_produce_different_phrases(self):
        # Not a strict guarantee (astronomically unlikely collision), but a
        # sanity check that generation isn't accidentally deterministic.
        wordlist = _wordlist()
        assert bm.generate_mnemonic(wordlist) != bm.generate_mnemonic(wordlist)

    def test_rejects_malformed_wordlist_wrong_length(self):
        with pytest.raises(ValueError, match="2048"):
            bm.generate_mnemonic(_wordlist(50))

    def test_rejects_malformed_wordlist_with_duplicates(self):
        words = _wordlist()
        words[1] = words[0]
        with pytest.raises(ValueError, match="duplicate"):
            bm.generate_mnemonic(words)


class TestValidateMnemonic:
    def test_wrong_word_count_is_rejected(self):
        valid, err = bm.validate_mnemonic("only two words", _wordlist())
        assert valid is False
        assert "12" in err or "Expected" in err

    def test_unknown_word_is_rejected(self):
        wordlist = _wordlist()
        phrase = bm.generate_mnemonic(wordlist)
        words = phrase.split()
        words[0] = "not_in_the_wordlist_at_all"
        valid, err = bm.validate_mnemonic(" ".join(words), wordlist)
        assert valid is False
        assert "unknown" in err.lower()

    def test_bad_checksum_is_rejected(self):
        wordlist = _wordlist()
        phrase = bm.generate_mnemonic(wordlist)
        words = phrase.split()
        word_to_idx = {w: i for i, w in enumerate(wordlist)}
        last_idx = word_to_idx[words[-1]]
        # The last word's low 4 bits are the checksum; its high 7 bits are
        # still entropy. Flip only the checksum bits (XOR with a nonzero
        # mask) so entropy — and therefore the *expected* checksum — is
        # unchanged, while the *embedded* checksum now deterministically
        # differs. A plain word swap only breaks the checksum by chance
        # (~15/16), which made this test flaky.
        corrupted_idx = last_idx ^ 0b1111
        words[-1] = wordlist[corrupted_idx]
        valid, err = bm.validate_mnemonic(" ".join(words), wordlist)
        assert valid is False

    def test_malformed_wordlist_is_rejected_before_checksum_math(self):
        words = _wordlist()
        words[1] = words[0]  # duplicate
        phrase = " ".join(words[:12])
        valid, err = bm.validate_mnemonic(phrase, words)
        assert valid is False
        assert "duplicate" in err.lower()

    def test_extra_whitespace_is_tolerated(self):
        wordlist = _wordlist()
        phrase = bm.generate_mnemonic(wordlist)
        messy = "  " + "   ".join(phrase.split()) + "  "
        valid, err = bm.validate_mnemonic(messy, wordlist)
        assert valid is True, err

    def test_case_is_tolerated(self):
        wordlist = _wordlist()
        phrase = bm.generate_mnemonic(wordlist)
        valid, err = bm.validate_mnemonic(phrase.upper(), wordlist)
        assert valid is True, err


class TestDeriveKey:
    def test_deterministic(self):
        assert bm.derive_key("abandon ability able") == bm.derive_key("abandon ability able")

    def test_different_phrases_give_different_keys(self):
        assert bm.derive_key("phrase one") != bm.derive_key("phrase two")

    def test_key_is_32_bytes(self):
        assert len(bm.derive_key("any phrase")) == 32

    def test_whitespace_normalization_matches_the_clean_phrase(self):
        assert bm.derive_key("  abandon   ability  able  ") == bm.derive_key("abandon ability able")

    def test_case_normalization(self):
        assert bm.derive_key("ABANDON Ability ABLE") == bm.derive_key("abandon ability able")


class TestEncryptDecryptRoundTrip:
    def test_roundtrip_recovers_original_data(self):
        key = bm.derive_key("test phrase")
        data = b"some plaintext payload" * 100
        blob = bm.encrypt_backup(key, data)
        assert bm.decrypt_backup(key, blob) == data

    def test_wrong_key_raises_invalid_tag(self):
        key = bm.derive_key("correct phrase")
        wrong_key = bm.derive_key("wrong phrase")
        blob = bm.encrypt_backup(key, b"secret data")
        with pytest.raises(InvalidTag):
            bm.decrypt_backup(wrong_key, blob)

    def test_tampered_ciphertext_raises_invalid_tag(self):
        key = bm.derive_key("test phrase")
        blob = bytearray(bm.encrypt_backup(key, b"secret data"))
        blob[-1] ^= 0xFF  # flip a bit in the ciphertext/auth tag
        with pytest.raises(InvalidTag):
            bm.decrypt_backup(key, bytes(blob))

    def test_bad_magic_raises_value_error(self):
        key = bm.derive_key("test phrase")
        blob = bm.encrypt_backup(key, b"data")
        corrupted = b"XXXX" + blob[4:]
        with pytest.raises(ValueError, match="Not a Primnox backup file"):
            bm.decrypt_backup(key, corrupted)

    def test_unsupported_version_raises_value_error(self):
        key = bm.derive_key("test phrase")
        blob = bm.encrypt_backup(key, b"data")
        corrupted = blob[:4] + bytes([0x99]) + blob[5:]
        with pytest.raises(ValueError, match="version"):
            bm.decrypt_backup(key, corrupted)

    def test_too_short_raises_value_error(self):
        with pytest.raises(ValueError, match="too small"):
            bm.decrypt_backup(bm.derive_key("x"), b"short")

    def test_nonces_differ_between_encryptions(self):
        key = bm.derive_key("test phrase")
        blob_a = bm.encrypt_backup(key, b"data")
        blob_b = bm.encrypt_backup(key, b"data")
        assert blob_a[5:17] != blob_b[5:17]
