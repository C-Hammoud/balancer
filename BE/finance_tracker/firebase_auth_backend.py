from django.contrib.auth import get_user_model
from firebase_admin import auth as fb_auth

class FirebaseAuthBackend:
    """
    Authenticate using a Firebase ID token. Usage: call authenticate(request, token=...)
    """
    def authenticate(self, request, token=None):
        if not token:
            return None
        try:
            decoded = fb_auth.verify_id_token(token)
        except Exception:
            return None
        uid = decoded.get("uid")
        email = decoded.get("email") or ""
        User = get_user_model()
        user, _ = User.objects.get_or_create(username=uid, defaults={"email": email})
        return user

    def get_user(self, user_id):
        User = get_user_model()
        try:
            return User.objects.get(pk=user_id)
        except User.DoesNotExist:
            return None