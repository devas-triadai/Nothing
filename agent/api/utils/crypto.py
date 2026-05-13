import os
import base64
from cryptography.fernet import Fernet
import logging

logger = logging.getLogger("agra.crypto")

from pathlib import Path

# Data directory for persistent key storage
_DATA_DIR = Path(os.environ.get("AGRA_DATA_DIR", "/workspace/agra_data"))
if not _DATA_DIR.exists():
    _DATA_DIR = Path(__file__).resolve().parent.parent.parent / "agra_data"
_DATA_DIR.mkdir(parents=True, exist_ok=True)
_KEY_FILE = _DATA_DIR / ".agra_key"

# Fetch key: Env Var > Key File > Generate New
_ENCRYPTION_KEY = os.environ.get("AGRA_ENCRYPTION_KEY")

if not _ENCRYPTION_KEY:
    if _KEY_FILE.exists():
        _ENCRYPTION_KEY = _KEY_FILE.read_text().strip()
        logger.info("Loaded persistent AGRA_ENCRYPTION_KEY from %s", _KEY_FILE)
    else:
        _ENCRYPTION_KEY = Fernet.generate_key().decode('utf-8')
        try:
            _KEY_FILE.write_text(_ENCRYPTION_KEY)
            logger.info("Generated and saved new persistent AGRA_ENCRYPTION_KEY to %s", _KEY_FILE)
        except Exception as e:
            logger.warning("Could not save AGRA_ENCRYPTION_KEY to file: %s. Key will be ephemeral.", e)

if not _ENCRYPTION_KEY:
    _ENCRYPTION_KEY = Fernet.generate_key().decode('utf-8')
    logger.warning("Using ephemeral encryption key.")

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
