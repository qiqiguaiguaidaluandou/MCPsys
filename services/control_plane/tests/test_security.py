import jwt
import pytest

from control_plane.security import (
    decode_jwt,
    encode_jwt,
    generate_api_key,
    hash_password,
    verify_password,
)


def test_password_round_trip():
    h = hash_password("hunter2")
    assert verify_password("hunter2", h) is True
    assert verify_password("wrong", h) is False


def test_jwt_round_trip():
    token = encode_jwt({"sub": "alice", "role": "admin"}, secret="s", expires_minutes=5)
    payload = decode_jwt(token, secret="s")
    assert payload["sub"] == "alice"
    assert payload["role"] == "admin"


def test_jwt_expired_raises():
    token = encode_jwt({"sub": "alice"}, secret="s", expires_minutes=-1)
    with pytest.raises(jwt.ExpiredSignatureError):
        decode_jwt(token, secret="s")


def test_generate_api_key_format():
    plaintext, prefix, hashed = generate_api_key()
    assert plaintext.startswith("mcpk_")
    assert len(prefix) == 8
    # prefix corresponds to the random portion after the tag
    assert plaintext[len("mcpk_"):].startswith(prefix)
    assert hashed != plaintext
    assert len(plaintext) >= 32
