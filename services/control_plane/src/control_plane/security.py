import secrets
from datetime import UTC, datetime, timedelta
from typing import Any

import bcrypt
import jwt

API_KEY_TAG = "mcpk_"
API_KEY_RANDOM_BYTES = 24  # → 32 chars base64url
PREFIX_LEN = 8


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def verify_password(password: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode(), hashed.encode())
    except ValueError:
        return False


def encode_jwt(claims: dict[str, Any], *, secret: str, expires_minutes: int) -> str:
    now = datetime.now(UTC)
    payload = {**claims, "iat": now, "exp": now + timedelta(minutes=expires_minutes)}
    return jwt.encode(payload, secret, algorithm="HS256")


def decode_jwt(token: str, *, secret: str) -> dict[str, Any]:
    return jwt.decode(
        token,
        secret,
        algorithms=["HS256"],
        options={"require": ["exp", "iat"]},
    )


def generate_api_key() -> tuple[str, str, str]:
    """Return (plaintext, prefix_for_display, bcrypt_hash).

    plaintext format: "mcpk_<32-char base64url random>"
    prefix is the first PREFIX_LEN chars of the random portion (after the tag).
    """
    rand = secrets.token_urlsafe(API_KEY_RANDOM_BYTES)
    plaintext = f"{API_KEY_TAG}{rand}"
    prefix = rand[:PREFIX_LEN]
    hashed = bcrypt.hashpw(plaintext.encode(), bcrypt.gensalt()).decode()
    return plaintext, prefix, hashed


def verify_api_key(plaintext: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(plaintext.encode(), hashed.encode())
    except ValueError:
        return False
