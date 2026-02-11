"""Firestore service for user persistence."""

import os
from datetime import datetime, timedelta, timezone
from typing import Optional, Dict, Any, Set
from google.cloud import firestore

USERS_COLLECTION = 'auto_marketing_users'
ACCESS_REQUESTS_COLLECTION = 'auto_marketing_access_requests'
GENERATIONS_COLLECTION = 'auto_marketing_generations'

ADMIN_EMAIL = 'dd.petrovskiy@gmail.com'


class FirestoreService:
    """Firestore operations for user management."""

    def __init__(self):
        project = os.getenv('GOOGLE_CLOUD_PROJECT') or os.getenv('FIREBASE_PROJECT_ID')
        self.db = firestore.Client(project=project) if project else firestore.Client()
        self.users = self.db.collection(USERS_COLLECTION)
        self.access_requests = self.db.collection(ACCESS_REQUESTS_COLLECTION)
        self.generations = self.db.collection(GENERATIONS_COLLECTION)

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
        is_admin = email.lower() == ADMIN_EMAIL
        doc_ref = self.users.document()
        user_data = {
            'firebase_uid': firebase_uid,
            'email': email.lower(),
            'display_name': display_name or email.split('@')[0],
            'photo_url': photo_url,
            'auth_provider': auth_provider,
            'approved': is_admin,
            'generation_limit': None,
            'is_admin': is_admin,
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

    # --- Approval ---

    def set_user_approved(self, user_id: str, approved: bool, generation_limit: Optional[int] = None) -> bool:
        """Set user approval status and optionally generation limit."""
        doc_ref = self.users.document(user_id)
        if not doc_ref.get().exists:
            return False
        update_data: Dict[str, Any] = {'approved': approved}
        if generation_limit is not None:
            update_data['generation_limit'] = generation_limit
        doc_ref.update(update_data)
        return True

    def is_user_approved(self, user_id: str) -> bool:
        """Check if user is approved."""
        user = self.get_user_by_id(user_id)
        if not user:
            return False
        return user.get('approved', False) or user.get('is_admin', False)

    # --- Access Requests ---

    def create_access_request(self, user_id: str, email: str, display_name: str) -> Dict[str, Any]:
        """Create an access request."""
        doc_ref = self.access_requests.document()
        request_data = {
            'user_id': user_id,
            'email': email,
            'display_name': display_name,
            'status': 'pending',
            'created_at': firestore.SERVER_TIMESTAMP,
            'resolved_at': None,
        }
        doc_ref.set(request_data)
        request_data['id'] = doc_ref.id
        return request_data

    def get_user_access_request(self, user_id: str) -> Optional[Dict[str, Any]]:
        """Get the most recent access request for a user."""
        docs = self.access_requests.where('user_id', '==', user_id).stream()
        requests = []
        for doc in docs:
            data = doc.to_dict()
            data['id'] = doc.id
            requests.append(data)
        if not requests:
            return None
        # Sort in Python to avoid requiring a Firestore composite index
        requests.sort(key=lambda x: x.get('created_at') or datetime.min.replace(tzinfo=timezone.utc), reverse=True)
        return requests[0]

    def approve_access_request(self, request_id: str, generation_limit: int = 3) -> bool:
        """Approve an access request and update the user."""
        doc_ref = self.access_requests.document(request_id)
        doc = doc_ref.get()
        if not doc.exists:
            return False
        data = doc.to_dict()
        doc_ref.update({
            'status': 'approved',
            'resolved_at': firestore.SERVER_TIMESTAMP,
        })
        self.set_user_approved(data['user_id'], True, generation_limit)
        return True

    def reject_access_request(self, request_id: str) -> bool:
        """Reject an access request."""
        doc_ref = self.access_requests.document(request_id)
        if not doc_ref.get().exists:
            return False
        doc_ref.update({
            'status': 'rejected',
            'resolved_at': firestore.SERVER_TIMESTAMP,
        })
        return True

    # --- Generation Tracking ---

    def record_generation(self, user_id: str, email: str, source_url: Optional[str] = None) -> str:
        """Record a generation event. Returns document ID."""
        doc_ref = self.generations.document()
        data = {
            'user_id': user_id,
            'email': email,
            'created_at': firestore.SERVER_TIMESTAMP,
        }
        if source_url:
            data['source_url'] = source_url
        doc_ref.set(data)
        return doc_ref.id

    def get_used_article_urls(self, days_back: int = 30) -> Set[str]:
        """Get all source article URLs used in generations within the last N days."""
        cutoff = datetime.now(timezone.utc) - timedelta(days=days_back)
        docs = (
            self.generations
            .where('created_at', '>=', cutoff)
            .stream()
        )
        urls = set()
        for doc in docs:
            data = doc.to_dict()
            url = data.get('source_url')
            if url:
                urls.add(url)
        return urls

    def get_user_generation_count(self, user_id: str) -> int:
        """Get total generation count for a user."""
        docs = self.generations.where('user_id', '==', user_id).stream()
        return sum(1 for _ in docs)

    def get_generations_remaining(self, user_id: str) -> Optional[int]:
        """Get remaining generations. None means unlimited."""
        user = self.get_user_by_id(user_id)
        if not user:
            return 0
        if user.get('is_admin', False):
            return None  # unlimited
        limit = user.get('generation_limit')
        if limit is None:
            return None  # unlimited
        used = self.get_user_generation_count(user_id)
        return max(0, limit - used)


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
