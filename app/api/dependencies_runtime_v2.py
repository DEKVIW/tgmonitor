from __future__ import annotations

from typing import Optional

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.models.models import engine
from app.services.account_auth_service import resolve_current_user_from_token

security = HTTPBearer()


def get_db():
    db = Session(engine)
    try:
        yield db
    finally:
        db.close()


def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: Session = Depends(get_db),
) -> dict:
    current_user = resolve_current_user_from_token(credentials.credentials, touch=True, session=db)
    if current_user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return current_user


def get_optional_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(HTTPBearer(auto_error=False)),
    db: Session = Depends(get_db),
) -> Optional[dict]:
    if credentials is None:
        return None
    return resolve_current_user_from_token(credentials.credentials, touch=True, session=db)


def get_admin_user(
    current_user: dict = Depends(get_current_user),
) -> dict:
    if current_user.get("role", "").lower() != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Administrator access is required",
        )
    return current_user
