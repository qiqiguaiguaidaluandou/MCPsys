import pytest

from mcpsys_shared.models import User, UserRole, UserStatus

from control_plane.security import hash_password


@pytest.fixture
async def alice(session_factory):
    async with session_factory() as s:
        u = User(
            username="alice",
            password_hash=hash_password("hunter2"),
            role=UserRole.admin,
            status=UserStatus.active,
        )
        s.add(u)
        await s.commit()
        await s.refresh(u)
        return u


async def test_login_success(client, alice):
    resp = await client.post(
        "/api/v1/auth/login",
        data={"username": "alice", "password": "hunter2"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["token_type"] == "bearer"
    assert isinstance(body["access_token"], str) and body["access_token"]


async def test_login_wrong_password(client, alice):
    resp = await client.post(
        "/api/v1/auth/login",
        data={"username": "alice", "password": "wrong"},
    )
    assert resp.status_code == 401


async def test_login_unknown_user(client):
    resp = await client.post(
        "/api/v1/auth/login",
        data={"username": "nobody", "password": "x"},
    )
    assert resp.status_code == 401
