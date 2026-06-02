from dataclasses import dataclass

import jwt
from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.core.config import settings
from app.core.exceptions import InvalidTokenError, MissingTokenError


security = HTTPBearer(auto_error=False)


@dataclass
class CurrentUser:
    username: str
    company: str
    role: str
    token: str


async def get_current_user(credentials: HTTPAuthorizationCredentials | None = Depends(security)) -> CurrentUser:
    if credentials is None:
        raise MissingTokenError()

    token = credentials.credentials
    try:
        payload = jwt.decode(token, settings.secret_key, algorithms=[settings.algorithm])
    except jwt.InvalidTokenError as exc:
        raise InvalidTokenError() from exc

    username = payload.get("username") or payload.get("sub")
    company = payload.get("company", "")
    role = payload.get("role", "user")
    if not isinstance(username, str) or not username:
        raise InvalidTokenError()
    if not isinstance(company, str):
        raise InvalidTokenError()
    if not isinstance(role, str):
        raise InvalidTokenError()
    return CurrentUser(username=username, company=company, role=role, token=token)
