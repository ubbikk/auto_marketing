"""Firestore service for user persistence."""

import os
from typing import Optional, Dict, Any
from google.cloud import firestore

USERS_COLLECTION = 'auto_marketing_users'


class FirestoreService:
    """Firestore operations for user management."""

    def __init__(self):
        project = os.getenv('GOOGLE_CLOUD_PROJECT') or os.getenv('FIREBASE_PROJECT_ID')
        self.db = firestore.Client(project=project) if project else firestore.Client()
        self.users = self.db.collection(USERS_COLLECTION)

    def get_user_by_firebase_uid(self, firebase_uid: str) -> Optional[Dict[str, Any]]:
        """Get user by Firebase UID."""
        docs = self.users.where('firebase_uid', '==', firebase_uid).limit(1).stream()
        for doc in docs:
            data = doc.to_dict()
            data['id'] = doc.id
            return data
        return None

    def get_user_by_id(self, user_id: str) -> Optional[Dict[str, Any]]:
        """Get user by document ID."""
        doc = self.users.document(user_id).get()
        if doc.exists:
            data = doc.to_dict()
            data['id'] = doc.id
            return data
        return None

    def create_user(
        self,
        firebase_uid: str,
        email: str,
        display_name: Optional[str] = None,
        photo_url: Optional[str] = None,
        auth_provider: str = 'unknown'
    ) -> Dict[str, Any]:
        """Create a new user from Firebase authentication."""
        doc_ref = self.users.document()
        user_data = {
            'firebase_uid': firebase_uid,
            'email': email.lower(),
            'display_name': display_name or email.split('@')[0],
            'photo_url': photo_url,
            'auth_provider': auth_provider,
            'created_at': firestore.SERVER_TIMESTAMP,
            'last_login_at': firestore.SERVER_TIMESTAMP,
        }
        doc_ref.set(user_data)
        user_data['id'] = doc_ref.id
        return user_data

    def update_user_login(self, user_id: str, photo_url: Optional[str] = None) -> bool:
        """Update last login timestamp."""
        doc_ref = self.users.document(user_id)
        if not doc_ref.get().exists:
            return False
        update_data = {'last_login_at': firestore.SERVER_TIMESTAMP}
        if photo_url:
            update_data['photo_url'] = photo_url
        doc_ref.update(update_data)
        return True


# Singleton
_firestore_instance: Optional[FirestoreService] = None


def get_firestore() -> Optional[FirestoreService]:
    """Get or create Firestore service singleton."""
    global _firestore_instance
    if _firestore_instance is None:
        try:
            _firestore_instance = FirestoreService()
        except Exception as e:
            print(f"Failed to initialize Firestore: {e}")
            return None
    return _firestore_instance
