import os
import base64
from cryptography.fernet import Fernet
import logging

logger = logging.getLogger("agra.crypto")

# Fetch key or generate one for dev
_ENCRYPTION_KEY = os.environ.get("AGRA_ENCRYPTION_KEY")
if not _ENCRYPTION_KEY:
    _ENCRYPTION_KEY = Fernet.generate_key().decode('utf-8')
    os.environ["AGRA_ENCRYPTION_KEY"] = _ENCRYPTION_KEY
    logger.warning("No AGRA_ENCRYPTION_KEY found. Generated an ephemeral key for this session.")

_fernet = Fernet(_ENCRYPTION_KEY.encode('utf-8'))

def encrypt_text(plaintext: str) -> str:
    """Encrypt sensitive text data before storing in Qdrant/Postgres."""
    try:
        return _fernet.encrypt(plaintext.encode('utf-8')).decode('utf-8')
    except Exception as e:
        logger.error(f"Encryption failed: {e}")
        return plaintext

def decrypt_text(ciphertext: str) -> str:
    """Decrypt text data retrieved from storage."""
    try:
        # Check if it looks like a fernet token (starts with gAAAA...)
        if ciphertext.startswith("gAAAA"):
            return _fernet.decrypt(ciphertext.encode('utf-8')).decode('utf-8')
        return ciphertext
    except Exception as e:
        logger.error(f"Decryption failed: {e}")
        return ciphertext
