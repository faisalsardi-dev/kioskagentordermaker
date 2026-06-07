"""Auth crypto: password hashing (argon2) and JWT minting/verification.

Crypto only — this module must not import sqlmanager or touch the database.
The JWT secret is loaded from the same env file as the LLM key.
"""

import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError
from dotenv import load_dotenv

ROOT = Path(__file__).parent
load_dotenv(ROOT / "kisoskagentapi.env")

_JWT_SECRET = os.getenv("jwt_secret_key")
_ALGORITHM = "HS256"
TOKEN_TTL_SECONDS = 3600

_hasher = PasswordHasher()


def hash_password(plain: str) -> str:
    """Return an argon2 hash of the plaintext password."""
    return _hasher.hash(plain)


def verify_password(plain: str, hashed: str) -> bool:
    """Check a plaintext password against an argon2 hash.

    Returns False on any verification failure rather than raising.
    """
    try:
        return _hasher.verify(hashed, plain)
    except VerifyMismatchError:
        return False
    except Exception:
        return False


def create_token(email: str) -> str:
    """Mint an HS256 JWT for this email, expiring in TOKEN_TTL_SECONDS."""
    now = datetime.now(timezone.utc)
    payload = {
        "sub": email,
        "exp": now + timedelta(seconds=TOKEN_TTL_SECONDS),
    }
    return jwt.encode(payload, _JWT_SECRET, algorithm=_ALGORITHM)


def verify_token(token: str) -> str | None:
    """Decode/validate a JWT. Returns the sub (email), or None if invalid/expired."""
    try:
        payload = jwt.decode(token, _JWT_SECRET, algorithms=[_ALGORITHM])
        return payload.get("sub")
    except jwt.PyJWTError:
        return None
