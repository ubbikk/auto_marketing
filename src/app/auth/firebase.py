"""Firebase Authentication service for token verification."""

import os
from typing import Optional, Dict, Any
import firebase_admin
from firebase_admin import auth

# Lazy-loaded Firebase app
_firebase_app = None


def get_firebase_app():
    """Initialize Firebase Admin SDK (singleton)."""
    global _firebase_app
    if _firebase_app is None:
        # Use Firebase project ID if set, otherwise fall back to GCP project
        project_id = os.getenv('FIREBASE_PROJECT_ID') or os.getenv('GOOGLE_CLOUD_PROJECT')
        if project_id:
            _firebase_app = firebase_admin.initialize_app(
                options={'projectId': project_id}
            )
        else:
            _firebase_app = firebase_admin.initialize_app()
    return _firebase_app


def verify_firebase_token(id_token: str) -> Optional[Dict[str, Any]]:
    """
    Verify Firebase ID token and return decoded claims.

    Args:
        id_token: Firebase ID token from client

    Returns:
        Dict with uid, email, name, picture, provider info, etc.
        None if verification fails.
    """
    try:
        get_firebase_app()
        decoded = auth.verify_id_token(id_token)
        return decoded
    except auth.InvalidIdTokenError as e:
        print(f"Invalid Firebase ID token: {e}")
        return None
    except auth.ExpiredIdTokenError as e:
        print(f"Expired Firebase ID token: {e}")
        return None
    except Exception as e:
        print(f"Firebase token verification failed: {e}")
        return None


def get_provider_from_token(decoded: Dict[str, Any]) -> str:
    """
    Extract auth provider from Firebase token.

    Args:
        decoded: Decoded Firebase token claims

    Returns:
        Provider name: 'google', 'microsoft', 'email', 'magic_link', or 'unknown'
    """
    firebase_info = decoded.get('firebase', {})
    sign_in_provider = firebase_info.get('sign_in_provider', 'unknown')

    # Map Firebase provider IDs to friendly names
    provider_map = {
        'google.com': 'google',
        'microsoft.com': 'microsoft',
        'password': 'email',
        'emailLink': 'magic_link'
    }
    return provider_map.get(sign_in_provider, sign_in_provider)
