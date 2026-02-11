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
    approved: bool = False
    generation_limit: Optional[int] = None
    is_admin: bool = False


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


def require_approved(request: Request) -> User:
    """Require approved user (raises 403 if not approved)."""
    user = require_auth(request)
    if not user.approved and not user.is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access not approved. Please request access first."
        )
    return user
