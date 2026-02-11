"""Firebase authentication module for auto_marketing."""

from .firebase import verify_firebase_token, get_provider_from_token
from .firestore import get_firestore, FirestoreService
from .dependencies import User, get_current_user, require_auth, require_approved

__all__ = [
    "verify_firebase_token",
    "get_provider_from_token",
    "get_firestore",
    "FirestoreService",
    "User",
    "get_current_user",
    "require_auth",
    "require_approved",
]
