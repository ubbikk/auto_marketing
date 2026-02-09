"""FastAPI authentication dependencies."""

from typing import Optional
from fastapi import Request, HTTPException, status
from pydantic import BaseModel


class User(BaseModel):
    """Authenticated user model."""
    id: str
    firebase_uid: str
    email: str
    display_name: str
    photo_url: Optional[str] = None
    auth_provider: str


def get_current_user(request: Request) -> Optional[User]:
    """Get current user from session (optional - returns None if not logged in)."""
    user_data = request.session.get('user')
    if not user_data:
        return None
    return User(**user_data)


def require_auth(request: Request) -> User:
    """Require authenticated user (raises 401 if not logged in)."""
    user = get_current_user(request)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required"
        )
    return user
