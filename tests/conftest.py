from datetime import datetime, timezone

import jwt
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from app.core.config import settings
from main import app


@pytest_asyncio.fixture()
async def client() -> AsyncClient:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac


@pytest_asyncio.fixture()
async def auth_token() -> str:
    now = datetime.now(tz=timezone.utc)
    payload = {
        "sub": "testuser",
        "username": "testuser",
        "company": "testcorp",
        "role": "admin",
        "sid": "session-1",
        "iat": int(now.timestamp()),
        "exp": int(now.timestamp() + 3600),
        "type": "access",
    }
    return jwt.encode(payload, settings.secret_key, algorithm=settings.algorithm)


@pytest_asyncio.fixture()
async def auth_headers(auth_token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {auth_token}"}
