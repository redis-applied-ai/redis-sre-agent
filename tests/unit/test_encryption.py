"""Tests for encryption utilities."""

import base64
import os
from unittest.mock import patch

import pytest

from redis_sre_agent.core.encryption import (
    EncryptionError,
    decrypt_secret,
    encrypt_secret,
    get_secret_value,
    is_encrypted,
    migrate_plaintext_to_encrypted,
)


@pytest.fixture
def master_key():
    """Generate a test master key."""
    key = base64.b64encode(os.urandom(32)).decode()
    with patch.dict(os.environ, {"REDIS_SRE_MASTER_KEY": key}):
        yield key


class TestEncryption:
    """Test encryption/decryption functionality."""

    def test_encrypt_decrypt_roundtrip(self, master_key):
        """Test that encryption and decryption work correctly."""
        plaintext = "my-secret-password-123"

        encrypted = encrypt_secret(plaintext)
        decrypted = decrypt_secret(encrypted)

        assert decrypted == plaintext
        assert encrypted != plaintext
        assert len(encrypted) > len(plaintext)

    def test_encrypt_different_each_time(self, master_key):
        """Test that encrypting the same plaintext produces different ciphertext."""
        plaintext = "my-secret-password"

        encrypted1 = encrypt_secret(plaintext)
        encrypted2 = encrypt_secret(plaintext)

        # Different ciphertext due to random nonces
        assert encrypted1 != encrypted2

        # But both decrypt to same plaintext
        assert decrypt_secret(encrypted1) == plaintext
        assert decrypt_secret(encrypted2) == plaintext

    def test_encrypt_empty_string(self, master_key):
        """Test encrypting empty string."""
        plaintext = ""

        encrypted = encrypt_secret(plaintext)
        decrypted = decrypt_secret(encrypted)

        assert decrypted == plaintext

    def test_encrypt_unicode(self, master_key):
        """Test encrypting unicode characters."""
        plaintext = "🔐 Secret with émojis and spëcial çhars 中文"

        encrypted = encrypt_secret(plaintext)
        decrypted = decrypt_secret(encrypted)

        assert decrypted == plaintext

    def test_encrypt_long_string(self, master_key):
        """Test encrypting long string."""
        plaintext = "x" * 10000

        encrypted = encrypt_secret(plaintext)
        decrypted = decrypt_secret(encrypted)

        assert decrypted == plaintext

    def test_decrypt_invalid_data(self, master_key):
        """Test that decrypting invalid data raises error."""
        with pytest.raises(EncryptionError):
            decrypt_secret("invalid-base64-data")

    def test_decrypt_corrupted_ciphertext(self, master_key):
        """Test that corrupted ciphertext fails to decrypt."""
        plaintext = "my-secret"
        encrypted = encrypt_secret(plaintext)

        # Corrupt the encrypted data
        corrupted = encrypted[:-10] + "XXXXXXXXXX"

        with pytest.raises(EncryptionError):
            decrypt_secret(corrupted)

    def test_decrypt_wrong_master_key(self, master_key):
        """Test that decryption fails with wrong master key."""
        plaintext = "my-secret"
        encrypted = encrypt_secret(plaintext)

        # Change master key
        wrong_key = base64.b64encode(os.urandom(32)).decode()
        with patch.dict(os.environ, {"REDIS_SRE_MASTER_KEY": wrong_key}):
            with pytest.raises(EncryptionError):
                decrypt_secret(encrypted)

    def test_missing_master_key(self):
        """Test that missing master key raises error."""
        with patch.dict(os.environ, {}, clear=True):
            with pytest.raises(EncryptionError, match="REDIS_SRE_MASTER_KEY"):
                encrypt_secret("test")

    def test_invalid_master_key_length(self):
        """Test that invalid master key length raises error."""
        # Too short
        short_key = base64.b64encode(b"short").decode()
        with patch.dict(os.environ, {"REDIS_SRE_MASTER_KEY": short_key}):
            with pytest.raises(EncryptionError, match="32 bytes"):
                encrypt_secret("test")

    def test_is_encrypted(self, master_key):
        """Test is_encrypted detection."""
        plaintext = "my-secret"
        encrypted = encrypt_secret(plaintext)

        assert is_encrypted(encrypted) is True
        assert is_encrypted(plaintext) is False
        assert is_encrypted("") is False
        assert is_encrypted("random-string") is False

    def test_migrate_plaintext_to_encrypted(self, master_key):
        """Test migrating plaintext to encrypted."""
        plaintext = "my-secret"

        encrypted = migrate_plaintext_to_encrypted(plaintext)

        assert is_encrypted(encrypted) is True
        assert decrypt_secret(encrypted) == plaintext

    def test_migrate_already_encrypted(self, master_key):
        """Test that migrating already encrypted data returns as-is."""
        plaintext = "my-secret"
        encrypted = encrypt_secret(plaintext)

        result = migrate_plaintext_to_encrypted(encrypted)

        assert result == encrypted

    def test_get_secret_value_encrypted(self, master_key):
        """Test get_secret_value with encrypted data."""
        plaintext = "my-secret"
        encrypted = encrypt_secret(plaintext)

        result = get_secret_value(encrypted)

        assert result == plaintext

    def test_get_secret_value_plaintext(self, master_key):
        """Test get_secret_value with plaintext (backward compatibility)."""
        plaintext = "my-secret"

        result = get_secret_value(plaintext)

        assert result == plaintext

    def test_envelope_structure(self, master_key):
        """Test that encrypted envelope has expected structure."""
        plaintext = "my-secret"
        encrypted = encrypt_secret(plaintext)

        # Decode envelope
        import json

        envelope_json = base64.b64decode(encrypted).decode("utf-8")
        envelope = json.loads(envelope_json)

        # Check structure
        assert "version" in envelope
        assert "ciphertext" in envelope
        assert "nonce" in envelope
        assert "wrapped_dek" in envelope
        assert "dek_nonce" in envelope
        assert envelope["version"] == "v1"

        # Check all fields are base64-encoded
        for field in ["ciphertext", "nonce", "wrapped_dek", "dek_nonce"]:
            assert isinstance(envelope[field], str)
            # Should be valid base64
            base64.b64decode(envelope[field])
