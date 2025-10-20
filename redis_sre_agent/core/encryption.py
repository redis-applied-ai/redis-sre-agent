"""Encryption utilities for sensitive data.

Uses envelope encryption with a master key from environment variables:
- Each secret gets a unique data encryption key (DEK)
- DEK encrypts the secret using AES-GCM (AEAD cipher)
- Master key encrypts the DEK
- Store: ciphertext, nonce, wrapped_DEK, algorithm version

This provides defense in depth - a database leak alone isn't enough to decrypt secrets.
"""

import base64
import json
import logging
import os

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

logger = logging.getLogger(__name__)

# Algorithm version for future migration support
CURRENT_VERSION = "v1"


class EncryptionError(Exception):
    """Raised when encryption/decryption fails."""

    pass


def _get_master_key() -> bytes:
    """Get master key from environment variable.

    Returns:
        32-byte master key

    Raises:
        EncryptionError: If master key is not configured or invalid
    """
    master_key_b64 = os.getenv("REDIS_SRE_MASTER_KEY")

    if not master_key_b64:
        raise EncryptionError(
            "REDIS_SRE_MASTER_KEY environment variable not set. "
            "Generate one with: python -c 'import os, base64; print(base64.b64encode(os.urandom(32)).decode())'"
        )

    try:
        master_key = base64.b64decode(master_key_b64)
        if len(master_key) != 32:
            raise EncryptionError(f"Master key must be 32 bytes, got {len(master_key)} bytes")
        return master_key
    except Exception as e:
        raise EncryptionError(f"Invalid master key format: {e}") from e


def encrypt_secret(plaintext: str) -> str:
    """Encrypt a secret using envelope encryption.

    Process:
    1. Generate random DEK (data encryption key)
    2. Encrypt plaintext with DEK using AES-GCM
    3. Encrypt DEK with master key
    4. Return JSON with ciphertext, nonce, wrapped_DEK, version

    Args:
        plaintext: Secret to encrypt

    Returns:
        Base64-encoded JSON string containing encrypted data

    Raises:
        EncryptionError: If encryption fails
    """
    try:
        # Get master key
        master_key = _get_master_key()

        # Generate random DEK (32 bytes for AES-256)
        dek = AESGCM.generate_key(bit_length=256)

        # Encrypt plaintext with DEK
        aesgcm_dek = AESGCM(dek)
        nonce = os.urandom(12)  # 96-bit nonce for GCM
        ciphertext = aesgcm_dek.encrypt(nonce, plaintext.encode("utf-8"), None)

        # Encrypt (wrap) DEK with master key
        aesgcm_master = AESGCM(master_key)
        dek_nonce = os.urandom(12)
        wrapped_dek = aesgcm_master.encrypt(dek_nonce, dek, None)

        # Package everything together
        envelope = {
            "version": CURRENT_VERSION,
            "ciphertext": base64.b64encode(ciphertext).decode("ascii"),
            "nonce": base64.b64encode(nonce).decode("ascii"),
            "wrapped_dek": base64.b64encode(wrapped_dek).decode("ascii"),
            "dek_nonce": base64.b64encode(dek_nonce).decode("ascii"),
        }

        # Return as base64-encoded JSON
        envelope_json = json.dumps(envelope)
        return base64.b64encode(envelope_json.encode("utf-8")).decode("ascii")

    except EncryptionError:
        raise
    except Exception as e:
        logger.error(f"Failed to encrypt secret: {e}")
        raise EncryptionError(f"Encryption failed: {e}") from e


def decrypt_secret(encrypted_data: str) -> str:
    """Decrypt a secret using envelope encryption.

    Process:
    1. Parse encrypted envelope
    2. Decrypt DEK using master key
    3. Decrypt ciphertext using DEK
    4. Return plaintext

    Args:
        encrypted_data: Base64-encoded JSON string from encrypt_secret()

    Returns:
        Decrypted plaintext

    Raises:
        EncryptionError: If decryption fails
    """
    try:
        # Get master key
        master_key = _get_master_key()

        # Parse envelope
        envelope_json = base64.b64decode(encrypted_data).decode("utf-8")
        envelope = json.loads(envelope_json)

        # Check version
        version = envelope.get("version")
        if version != CURRENT_VERSION:
            raise EncryptionError(
                f"Unsupported encryption version: {version} (expected {CURRENT_VERSION})"
            )

        # Decode components
        ciphertext = base64.b64decode(envelope["ciphertext"])
        nonce = base64.b64decode(envelope["nonce"])
        wrapped_dek = base64.b64decode(envelope["wrapped_dek"])
        dek_nonce = base64.b64decode(envelope["dek_nonce"])

        # Unwrap DEK using master key
        aesgcm_master = AESGCM(master_key)
        dek = aesgcm_master.decrypt(dek_nonce, wrapped_dek, None)

        # Decrypt ciphertext using DEK
        aesgcm_dek = AESGCM(dek)
        plaintext_bytes = aesgcm_dek.decrypt(nonce, ciphertext, None)

        return plaintext_bytes.decode("utf-8")

    except EncryptionError:
        raise
    except Exception as e:
        logger.error(f"Failed to decrypt secret: {e}")
        raise EncryptionError(f"Decryption failed: {e}") from e


def is_encrypted(data: str) -> bool:
    """Check if data appears to be encrypted by this module.

    Args:
        data: String to check

    Returns:
        True if data looks like encrypted envelope, False otherwise
    """
    try:
        envelope_json = base64.b64decode(data).decode("utf-8")
        envelope = json.loads(envelope_json)
        return "version" in envelope and "ciphertext" in envelope and "wrapped_dek" in envelope
    except Exception:
        return False


def migrate_plaintext_to_encrypted(plaintext: str) -> str:
    """Migrate a plaintext secret to encrypted format.

    This is a helper for migrating existing plaintext secrets.

    Args:
        plaintext: Plaintext secret

    Returns:
        Encrypted secret
    """
    if is_encrypted(plaintext):
        logger.warning("Secret is already encrypted, returning as-is")
        return plaintext

    return encrypt_secret(plaintext)


def get_secret_value(data: str) -> str:
    """Get the plaintext value of a secret, handling both encrypted and plaintext.

    This is a convenience function that:
    - Decrypts if data is encrypted
    - Returns as-is if data is plaintext (for backward compatibility)

    Args:
        data: Secret data (encrypted or plaintext)

    Returns:
        Plaintext secret value

    Raises:
        EncryptionError: If decryption fails
    """
    if not data:
        return data

    if is_encrypted(data):
        logger.debug(f"Decrypting secret (length: {len(data)})")
        try:
            decrypted = decrypt_secret(data)
            logger.debug("Successfully decrypted secret")
            return decrypted
        except EncryptionError:
            logger.error("Failed to decrypt secret - re-raising exception")
            raise
    else:
        # Backward compatibility: return plaintext as-is
        logger.warning(
            f"Secret is stored in plaintext (length: {len(data)}), consider migrating to encrypted"
        )
        return data
