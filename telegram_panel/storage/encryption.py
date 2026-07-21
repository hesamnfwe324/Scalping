"""
Encryption service — AES-128 via Fernet (symmetric encryption).
Used to store broker credentials securely in SQLite.
Never stores raw passwords anywhere.
"""

import os
import base64
import logging
from typing import Optional

logger = logging.getLogger(__name__)


class EncryptionService:
    """
    Symmetric encryption for sensitive storage using Fernet.
    Key must be a 32-byte URL-safe base64-encoded string.
    """

    def __init__(self, key: str = "") -> None:
        self._fernet = None
        if key:
            self._init_fernet(key)

    def _init_fernet(self, key: str) -> None:
        try:
            from cryptography.fernet import Fernet, InvalidToken
            self._InvalidToken = InvalidToken
            # Validate key is correct format
            key_bytes = key.encode() if isinstance(key, str) else key
            self._fernet = Fernet(key_bytes)
            logger.info("Encryption service initialized successfully")
        except ImportError:
            logger.warning(
                "cryptography package not installed — credentials will be stored with "
                "base64 obfuscation only. Install: pip install cryptography"
            )
            self._fernet = None
        except Exception as e:
            logger.error(f"Failed to initialize encryption: {e}")
            self._fernet = None

    @staticmethod
    def generate_key() -> str:
        """Generate a new 32-byte Fernet key. Store in PANEL_ENCRYPTION_KEY env var."""
        from cryptography.fernet import Fernet
        return Fernet.generate_key().decode()

    def encrypt(self, plaintext: str) -> str:
        """Encrypt a string. Returns encrypted base64 string."""
        if not plaintext:
            return ""
        if self._fernet:
            try:
                encrypted = self._fernet.encrypt(plaintext.encode("utf-8"))
                return encrypted.decode("utf-8")
            except Exception as e:
                logger.error(f"Encryption failed: {e}")
                # Fall through to obfuscation
        # Fallback: base64 obfuscation (not secure, but prevents casual reading)
        return "b64:" + base64.b64encode(plaintext.encode("utf-8")).decode("utf-8")

    def decrypt(self, ciphertext: str) -> Optional[str]:
        """Decrypt a string. Returns plaintext or None on failure."""
        if not ciphertext:
            return None
        # Handle legacy base64 obfuscation
        if ciphertext.startswith("b64:"):
            try:
                return base64.b64decode(ciphertext[4:]).decode("utf-8")
            except Exception as e:
                logger.error(f"Base64 decode failed: {e}")
                return None
        if self._fernet:
            try:
                decrypted = self._fernet.decrypt(ciphertext.encode("utf-8"))
                return decrypted.decode("utf-8")
            except Exception as e:
                logger.error(f"Decryption failed: {e}")
                return None
        logger.warning("No decryption key available")
        return None

    @property
    def is_secure(self) -> bool:
        """True if real encryption (Fernet) is active."""
        return self._fernet is not None
